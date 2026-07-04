"""
FlareSolverr client.

FlareSolverr (https://github.com/FlareSolverr/FlareSolverr) is a proxy server
that drives an undetected headless browser to solve Cloudflare / DDoS-Guard /
JavaScript challenges and returns the resulting HTML and cookies.

This service is used as a *fallback* in the content-fetch path: normal httpx
requests are attempted first (fast, cheap), and only when a response looks like
a bot-block / challenge do we escalate to FlareSolverr (slow, browser-backed).
"""
import logging
from typing import Optional

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)

# Markers that indicate a challenge / bot-block interstitial rather than the
# real page. Matched case-insensitively against the response body.
_CHALLENGE_MARKERS = (
    "just a moment",  # Cloudflare interstitial title
    "attention required",  # Cloudflare 1020 block
    "cf-browser-verification",
    "cf_chl_opt",
    "_cf_chl_",
    "checking your browser",
    "ddos-guard",
    "please enable javascript and cookies",
    "verifying you are human",
)

# HTTP statuses that commonly indicate a bot-block worth retrying via browser.
_BLOCK_STATUS_CODES = {403, 429, 503}


# Markers of a browser-generated network/HTTP error interstitial (Chromium's
# neterror page). FlareSolverr reports solution.status=200 for these because the
# *navigation* succeeded, so we must inspect the body to reject them.
_BROWSER_ERROR_MARKERS = (
    "reload-button",
    "neterror",
    "errorcode",
    "err_",
    "this site can",  # "This site can't be reached"
    "took too long to respond",
    "err_timed_out",
    "err_connection",
)


def is_browser_error_page(body: Optional[str]) -> bool:
    """True if the rendered body is a browser error page rather than real content."""
    if not body:
        return False
    head = body[:6000].lower()
    return any(marker in head for marker in _BROWSER_ERROR_MARKERS)


def looks_like_challenge(status_code: Optional[int], body: Optional[str]) -> bool:
    """Heuristically decide whether a response is a bot-block/challenge page."""
    if status_code in _BLOCK_STATUS_CODES:
        return True
    if not body:
        return False
    # Only inspect the head of the document; challenge pages are small and put
    # their markers near the top.
    head = body[:4000].lower()
    return any(marker in head for marker in _CHALLENGE_MARKERS)


class FlareSolverrService:
    """Thin async client for the FlareSolverr v1 API."""

    def __init__(self, base_url: Optional[str] = None, timeout_ms: Optional[int] = None):
        self.base_url = (base_url or settings.FLARESOLVERR_URL).rstrip("/")
        self.timeout_ms = timeout_ms or settings.FLARESOLVERR_TIMEOUT_MS

    @property
    def enabled(self) -> bool:
        return bool(getattr(settings, "FLARESOLVERR_ENABLED", False))

    async def fetch(
        self, url: str, proxy_url: Optional[str] = None, max_timeout_ms: Optional[int] = None
    ) -> Optional[str]:
        """
        Fetch a URL through FlareSolverr, returning the solved HTML or None.

        Args:
            url: The target URL to fetch.
            proxy_url: Optional upstream proxy (e.g. the Decodo gateway or the
                Mullvad WireGuard gateway) for FlareSolverr's browser to use, so
                the challenge is solved from the same egress IP as normal fetches.
            max_timeout_ms: Per-call browser budget override (defaults to the
                service-wide FLARESOLVERR_TIMEOUT_MS). Callers with their own
                deadline (e.g. an archive router strategy timeout) pass a smaller
                value so the whole fallback fits inside their budget.
        """
        if not self.enabled:
            return None

        budget_ms = max_timeout_ms or self.timeout_ms
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": budget_ms,
        }
        if proxy_url:
            payload["proxy"] = {"url": proxy_url}

        # The browser budget plus overhead; give httpx a little more than the
        # FlareSolverr maxTimeout so the server, not the client, times out first.
        client_timeout = (budget_ms / 1000.0) + 30.0

        try:
            async with httpx.AsyncClient(timeout=client_timeout) as client:
                resp = await client.post(f"{self.base_url}/v1", json=payload)
        except Exception as exc:
            logger.warning(f"FlareSolverr request failed for {url}: {exc}")
            return None

        if resp.status_code != 200:
            logger.warning(
                f"FlareSolverr returned HTTP {resp.status_code} for {url}: {resp.text[:300]}"
            )
            return None

        try:
            data = resp.json()
        except Exception:
            logger.warning(f"FlareSolverr returned non-JSON for {url}")
            return None

        if data.get("status") != "ok":
            logger.warning(
                f"FlareSolverr could not solve {url}: {data.get('message', 'unknown error')}"
            )
            return None

        solution = data.get("solution") or {}
        html = solution.get("response")
        solved_status = solution.get("status")

        # FlareSolverr reports status "ok"/200 whenever the browser *navigated*,
        # even if the target returned a rate-limit/block that Chromium rendered as
        # an error page. Reject those so we don't treat a block as real content.
        if html and is_browser_error_page(html):
            logger.warning(f"FlareSolverr got a browser error page for {url} (upstream block/rate-limit)")
            return None

        # Even a "solved" response can still be a challenge page if the browser
        # was itself blocked; guard against handing that back to extraction.
        if html and looks_like_challenge(solved_status, html):
            logger.warning(f"FlareSolverr solution for {url} still looks like a challenge")
            return None

        if html:
            logger.info(f"FlareSolverr solved {url} ({len(html)} chars, status {solved_status})")
        return html or None

    async def fetch_rotating(
        self, url: str, max_tries: int = 4, max_timeout_ms: Optional[int] = None
    ) -> Optional[str]:
        """
        Fetch a URL through FlareSolverr, rotating the egress exit on each block.

        Pulls a shuffled set of proxy candidates for the current egress provider
        (the Mullvad replica pool when EGRESS_PROVIDER=mullvad) and tries them in
        turn. `fetch` returns None on a block/error page, so any None result
        rotates to the next exit. Returns the first real response, or None if all
        tried exits were blocked.
        """
        if not self.enabled:
            return None
        from app.services.egress_rotation import egress_proxy_candidates

        candidates = await egress_proxy_candidates(max_candidates=max_tries)
        if not candidates:
            candidates = [None]

        for attempt, proxy in enumerate(candidates[:max_tries], start=1):
            html = await self.fetch(url, proxy_url=proxy, max_timeout_ms=max_timeout_ms)
            if html is not None:
                if attempt > 1:
                    logger.info(f"FlareSolverr succeeded on exit {attempt}/{len(candidates)} for {url}")
                return html
            logger.info(
                f"FlareSolverr exit {attempt}/{min(max_tries, len(candidates))} blocked for {url}; rotating"
            )
        return None


# Module-level singleton — the client holds no per-request state.
_flaresolverr_service: Optional[FlareSolverrService] = None


def get_flaresolverr_service() -> FlareSolverrService:
    global _flaresolverr_service
    if _flaresolverr_service is None:
        _flaresolverr_service = FlareSolverrService()
    return _flaresolverr_service
