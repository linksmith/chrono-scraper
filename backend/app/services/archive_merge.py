"""
Merging of Common Crawl and Wayback Machine CDX records for hybrid discovery.

Common Crawl is queried first (its content comes straight from WARC files on a
public CDN). Wayback records are only kept when they add coverage: a Wayback
capture that Common Crawl already has is dropped according to HYBRID_DEDUP_MODE.
"""
import logging
from typing import Any, Dict, Iterable, List, Set, Tuple
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

DEDUP_MODES = ("digest", "url_period")
DEDUP_PERIODS = {"day": 8, "month": 6, "year": 4}  # prefix length of the 14-digit timestamp
_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_url(url: str) -> str:
    """
    Collapse trivially different spellings of one URL into a single key.

    Scheme, a leading ``www.``, default ports, fragments, host case and a
    trailing slash on the path are ignored; the query string is kept as-is
    because it usually selects different content.
    """
    if not url:
        return ""
    raw = url.strip()
    if "://" not in raw:
        raw = "http://" + raw
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return raw.lower()
    if host.startswith("www."):
        host = host[4:]
    scheme = (parts.scheme or "http").lower()
    if port is not None and port != _DEFAULT_PORTS.get(scheme):
        host = f"{host}:{port}"
    path = parts.path.rstrip("/")
    key = f"{host}{path}"
    if parts.query:
        key = f"{key}?{parts.query}"
    return key


def period_key(timestamp: str, period: str = "month") -> str:
    """Prefix of a CDX timestamp identifying the dedup period (day/month/year)."""
    length = DEDUP_PERIODS.get(period)
    if length is None:
        raise ValueError(f"Unknown HYBRID_DEDUP_PERIOD {period!r}; expected one of {sorted(DEDUP_PERIODS)}")
    return (timestamp or "")[:length]


def merge_hybrid_records(
    cc_records: Iterable[Any],
    wayback_records: Iterable[Any],
    mode: str = "url_period",
    period: str = "month",
) -> Tuple[List[Any], Dict[str, int]]:
    """
    Return Common Crawl records plus the Wayback records CC does not cover.

    Common Crawl records are returned untouched (they carry the WARC
    filename/offset/length the content fetch needs).
    """
    if mode not in DEDUP_MODES:
        raise ValueError(f"Unknown HYBRID_DEDUP_MODE {mode!r}; expected one of {DEDUP_MODES}")
    cc_list = list(cc_records)
    wb_list = list(wayback_records)

    covered: Set[Any]
    if mode == "digest":
        covered = {r.digest for r in cc_list if getattr(r, "digest", None)}

        def is_covered(rec: Any) -> bool:
            return bool(rec.digest) and rec.digest in covered
    else:
        covered = {(normalize_url(r.original_url), period_key(r.timestamp, period)) for r in cc_list}

        def is_covered(rec: Any) -> bool:
            return (normalize_url(rec.original_url), period_key(rec.timestamp, period)) in covered

    kept_wayback = [r for r in wb_list if not is_covered(r)]
    stats = {
        "cc": len(cc_list),
        "wayback": len(wb_list),
        "wayback_dropped": len(wb_list) - len(kept_wayback),
        "final": len(cc_list) + len(kept_wayback),
    }
    logger.info(
        "Hybrid merge (%s%s): cc=%d wayback=%d wayback_dropped=%d final=%d",
        mode, f"/{period}" if mode == "url_period" else "",
        stats["cc"], stats["wayback"], stats["wayback_dropped"], stats["final"],
    )
    return cc_list + kept_wayback, stats
