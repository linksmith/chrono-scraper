import uuid
from typing import List, Optional

import httpx

from app.core.config import settings


class FirecrawlV2Client:
    """Thin client for Firecrawl v2 Batch Scrape with v1 fallback.

    In test environment (settings.ENVIRONMENT == "test"), network calls are stubbed.
    """

    def __init__(self):
        # Prefer local URL when available
        base_url = getattr(settings, "FIRECRAWL_LOCAL_URL", None) or getattr(settings, "FIRECRAWL_BASE_URL", None)
        self.base_url = (base_url or "http://localhost:3002").rstrip("/")
        self.version = (getattr(settings, "FIRECRAWL_API_VERSION", "v2") or "v2").lower().strip()
        self.api_key = getattr(settings, "FIRECRAWL_API_KEY", None)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def start_batch(self, urls: List[str], formats: Optional[List[str]] = None, timeout_ms: Optional[int] = None) -> str:
        """Start a batch scrape job and return the batch id/crawl id.

        For v2: POST /v2/scrape/batch
        For v1 fallback: POST /v1/batch/scrape
        """
        if getattr(settings, "ENVIRONMENT", "development") == "test":
            # Avoid network in tests
            return f"test-batch-{uuid.uuid4().hex[:8]}"

        formats = formats or ["markdown", "html"]
        timeout_ms = timeout_ms or 60_000

        if self.version == "v2":
            path = "/v2/scrape/batch"
            payload = {
                "urls": urls,
                "formats": formats,
                "timeout": timeout_ms,
            }
            with httpx.Client(timeout=30) as client:
                resp = client.post(self.base_url + path, json=payload, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                return data.get("id") or data.get("crawl_id") or ""
        else:
            # Fallback to embedded v1 server if configured
            path = "/v1/batch/scrape"
            payload = {
                "urls": urls,
                "formats": formats,
                "timeout": timeout_ms,
                "ignoreInvalidURLs": True,
                "zeroDataRetention": False,
            }
            with httpx.Client(timeout=30) as client:
                resp = client.post(self.base_url + path, json=payload, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                return data.get("id") or ""

    def cancel_batch(self, batch_id: str) -> bool:
        """Cancel a batch scrape.

        For v2: DELETE /v2/scrape/batch/:id
        For v1 fallback: POST /v1/crawl/:id/cancel
        """
        if not batch_id:
            return False

        if getattr(settings, "ENVIRONMENT", "development") == "test":
            # Pretend success in tests
            return True

        try:
            if self.version == "v2":
                path = f"/v2/scrape/batch/{batch_id}"
                with httpx.Client(timeout=15) as client:
                    resp = client.delete(self.base_url + path, headers=self._headers())
                    return 200 <= resp.status_code < 300
            else:
                path = f"/v1/crawl/{batch_id}/cancel"
                with httpx.Client(timeout=15) as client:
                    resp = client.post(self.base_url + path, headers=self._headers())
                    return 200 <= resp.status_code < 300
        except Exception:
            return False


