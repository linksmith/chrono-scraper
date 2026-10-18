"""Corpus collection from the Wayback Machine and Common Crawl.

Deliberately self-contained (plain httpx, no ``app.*`` imports): collection
builds the corpus the pipeline is judged *against*, so it must not depend on
the code under test. Two consequences of that independence:

* Wayback fetches use the ``id_`` URL modifier, which returns the archived
  payload byte-for-byte (no toolbar, no URL rewriting). The production
  pipeline uses ``if_`` — comparing extraction over both is itself an eval
  question.
* Common Crawl fetches are HTTP Range requests against the public
  ``data.commoncrawl.org`` CDN using the index's WARC filename/offset/length,
  with proper WARC-record parsing (header blocks stripped, chunked bodies
  de-chunked) rather than substring slicing.

Politeness: a shared client enforces a per-host delay and honors 429/503
with backoff. Failures are recorded per snapshot in the catalog and never
abort a run.
"""

from __future__ import annotations

import gzip
import json
import logging
import re
import time
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from evals.config import CollectConfig, EvalConfig
from evals.manifest import SiteEntry
from evals.storage import BlobStore, Catalog, SnapshotRef
from evals.urls import canonicalize_url

logger = logging.getLogger(__name__)

# Cap any backoff so a bogus/hostile Retry-After can't wedge the run for hours.
MAX_RETRY_AFTER_SECONDS = 300.0


def parse_retry_after(value: str | None) -> float:
    """Parse an HTTP ``Retry-After`` header to seconds.

    RFC 7231 allows either a delta-seconds integer OR an HTTP-date. The old
    ``float(value)`` blew up with ValueError on the date form — and since that
    ran inside the 429/503 branch, the exception escaped every handler and
    killed the whole multi-site run exactly when archives were rate-limiting.
    Returns 0.0 for missing/unparseable values; clamps to a sane ceiling.
    """
    if not value:
        return 0.0
    text = value.strip()
    try:
        return min(max(0.0, float(text)), MAX_RETRY_AFTER_SECONDS)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return 0.0
    if when is None:
        return 0.0
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = (when - datetime.now(timezone.utc)).total_seconds()
    return min(max(0.0, delta), MAX_RETRY_AFTER_SECONDS)

WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
WAYBACK_RAW_TEMPLATE = "https://web.archive.org/web/{timestamp}id_/{url}"
CC_COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"
CC_DATA_URL = "https://data.commoncrawl.org"

_CC_YEAR_RE = re.compile(r"CC-MAIN-(\d{4})-")


class CollectError(RuntimeError):
    pass


@dataclass(frozen=True)
class CdxRow:
    """One capture as reported by a CDX index (either archive).

    ``url`` is canonical (used for grouping, storage keys and dedup);
    ``original_url`` is the exact string the archive knows, used for fetching
    so we never ask for a normalized URL the archive can't resolve.
    """

    url: str
    timestamp: str
    digest: str
    mime: str
    status: int
    source: str  # 'wayback' | 'commoncrawl'
    original_url: str = ""
    warc_filename: str | None = None
    warc_offset: int | None = None
    warc_length: int | None = None

    @property
    def fetch_url(self) -> str:
        if self.source == "wayback":
            return WAYBACK_RAW_TEMPLATE.format(
                timestamp=self.timestamp, url=self.original_url or self.url
            )
        return f"{CC_DATA_URL}/{self.warc_filename}#{self.warc_offset}-{self.warc_length}"


class PoliteClient:
    """httpx wrapper: fixed inter-request delay, backoff on 429/5xx."""

    def __init__(self, delay_seconds: float, cfg: CollectConfig) -> None:
        self.delay = delay_seconds
        self.max_bytes = cfg.max_html_bytes
        self._client = httpx.Client(
            timeout=cfg.timeout_seconds,
            headers={"User-Agent": cfg.user_agent},
            follow_redirects=True,
        )
        self._last_request = 0.0

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        wait = self.delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def get(self, url: str, *, params=None, headers=None, attempts: int = 3) -> httpx.Response:
        """Buffered GET for CDX/JSON responses that must arrive complete."""
        last_error: Exception | None = None
        for attempt in range(attempts):
            self._throttle()
            try:
                response = self._client.get(url, params=params, headers=headers)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("collect: transport error on %s (attempt %d): %s", url, attempt + 1, exc)
                time.sleep(2.0 * (attempt + 1))
                continue
            if response.status_code in (429, 503):
                backoff = max(parse_retry_after(response.headers.get("Retry-After")), 5.0 * (attempt + 1))
                logger.warning(
                    "collect: HTTP %d from %s — backing off %.0fs", response.status_code, url, backoff
                )
                last_error = CollectError(f"HTTP {response.status_code}")
                time.sleep(backoff)
                continue
            return response
        raise CollectError(f"giving up on {url}: {last_error}")

    def get_bytes(
        self, url: str, *, headers=None, attempts: int = 3, tolerate_incomplete: bool = False
    ) -> tuple[int, bytes]:
        """Streamed GET returning (status_code, body).

        The Wayback ``id_`` endpoint routinely closes chunked responses early
        ("incomplete chunked read"). Streaming lets us keep the partial body —
        usually the whole article, minus a truncated footer — instead of
        losing the snapshot entirely. ``tolerate_incomplete`` gates that
        behavior so callers who need byte-exact payloads (WARC members) don't
        accept truncation.
        """
        last_error: Exception | None = None
        for attempt in range(attempts):
            self._throttle()
            sleep_for = 2.0 * (attempt + 1)
            try:
                with self._client.stream("GET", url, headers=headers) as response:
                    status = response.status_code
                    if status in (429, 503):
                        sleep_for = max(parse_retry_after(response.headers.get("Retry-After")), 5.0 * (attempt + 1))
                        last_error = CollectError(f"HTTP {status}")
                        logger.warning("collect: HTTP %d from %s — backing off %.0fs", status, url, sleep_for)
                    elif status not in (200, 206):
                        return status, b""
                    else:
                        chunks: list[bytes] = []
                        total = 0
                        incomplete = False
                        try:
                            for chunk in response.iter_bytes():
                                chunks.append(chunk)
                                total += len(chunk)
                                if total > self.max_bytes:
                                    break
                        except httpx.RemoteProtocolError as exc:
                            incomplete, last_error = True, exc
                        if not incomplete or (tolerate_incomplete and total > 0):
                            if incomplete:
                                logger.warning("collect: incomplete read on %s; kept %d partial bytes", url, total)
                            return status, b"".join(chunks)
                        logger.warning("collect: incomplete read on %s (attempt %d)", url, attempt + 1)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("collect: transport error on %s (attempt %d): %s", url, attempt + 1, exc)
            time.sleep(sleep_for)
        raise CollectError(f"giving up on {url}: {last_error}")


# --------------------------------------------------------------------------
# CDX queries
# --------------------------------------------------------------------------

def wayback_query(
    client: PoliteClient,
    target: str,
    match_type: str,
    from_year: int,
    to_year: int,
    limit: int,
    collapse: str | None = "digest",
) -> list[CdxRow]:
    """Query the Wayback CDX server.

    ``collapse`` controls server-side de-duplication of the row stream:

    * ``"digest"`` (default) — drop *adjacent* byte-identical captures. Real
      dedup still happens on our side (near-identical captures with a changed
      footer keep distinct digests and survive — that is the dedup eval's job).
    * ``"urlkey"`` — one row per distinct URL. Used for the *discovery* pass so
      a prefix query surfaces many distinct pages instead of hundreds of
      captures of whichever URL sorts first.
    * ``None`` — no collapsing (every capture), used for per-URL snapshot
      queries where we want the full time series.
    """
    params = [
        ("url", target),
        ("matchType", match_type),
        ("output", "json"),
        ("from", str(from_year)),
        ("to", str(to_year)),
        ("filter", "statuscode:200"),
        ("filter", "mimetype:text/html"),
        ("fl", "timestamp,original,mimetype,statuscode,digest,length"),
        ("limit", str(limit)),
    ]
    if collapse:
        params.append(("collapse", collapse))
    response = client.get(WAYBACK_CDX_URL, params=params)
    if response.status_code != 200:
        raise CollectError(f"wayback CDX HTTP {response.status_code} for {target}")
    try:
        data = response.json()
    except ValueError as exc:
        raise CollectError(f"wayback CDX returned non-JSON for {target}") from exc
    rows: list[CdxRow] = []
    for raw in data[1:]:  # first row is the header
        try:
            rows.append(
                CdxRow(
                    timestamp=raw[0],
                    url=canonicalize_url(raw[1]),
                    original_url=raw[1],
                    mime=raw[2],
                    status=int(raw[3]),
                    digest=raw[4],
                    source="wayback",
                )
            )
        except (IndexError, ValueError):
            logger.debug("collect: skipping malformed wayback CDX row %r", raw)
    return rows


def cc_collections(client: PoliteClient, from_year: int, to_year: int, cap: int) -> list[dict]:
    """Common Crawl collections overlapping the year range, evenly sampled."""
    response = client.get(CC_COLLINFO_URL)
    if response.status_code != 200:
        raise CollectError(f"collinfo.json HTTP {response.status_code}")
    matching = []
    for coll in response.json():
        match = _CC_YEAR_RE.search(coll.get("id", ""))
        if match and from_year <= int(match.group(1)) <= to_year:
            matching.append(coll)
    matching.sort(key=lambda c: c["id"])
    if len(matching) <= cap:
        return matching
    step = (len(matching) - 1) / (cap - 1) if cap > 1 else 1
    return [matching[round(i * step)] for i in range(cap)]


def cc_query(
    client: PoliteClient, cdx_api: str, target: str, match_type: str, limit: int
) -> list[CdxRow]:
    params = [
        ("url", target),
        ("matchType", match_type),
        ("output", "json"),
        ("filter", "=status:200"),
        ("filter", "mime:text/html"),
        ("limit", str(limit)),
    ]
    response = client.get(cdx_api, params=params)
    if response.status_code == 404:  # pywb's "no captures found"
        return []
    if response.status_code != 200:
        raise CollectError(f"CC index HTTP {response.status_code} for {target} at {cdx_api}")
    rows: list[CdxRow] = []
    for line in response.text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            rows.append(
                CdxRow(
                    url=canonicalize_url(record["url"]),
                    original_url=record["url"],
                    timestamp=record["timestamp"],
                    digest=record.get("digest", ""),
                    mime=record.get("mime", ""),
                    status=int(record.get("status", 0)),
                    source="commoncrawl",
                    warc_filename=record["filename"],
                    warc_offset=int(record["offset"]),
                    warc_length=int(record["length"]),
                )
            )
        except (KeyError, ValueError):
            logger.debug("collect: skipping malformed CC index line %r", line[:120])
    return rows


# ------------------------------------------------------------------------------
# Raw payload fetching
# ------------------------------------------------------------------------------

def fetch_wayback_raw(client: PoliteClient, row: CdxRow) -> bytes:
    status, content = client.get_bytes(row.fetch_url, tolerate_incomplete=True)
    if status != 200:
        raise CollectError(f"wayback raw fetch HTTP {status}")
    if not content:
        raise CollectError("wayback raw fetch returned empty body")
    return content  # streaming already capped at max_bytes


def _dechunk(body: bytes) -> bytes:
    """Decode an HTTP/1.1 chunked transfer-encoded body."""
    out = bytearray()
    pos = 0
    while True:
        line_end = body.find(b"\r\n", pos)
        if line_end < 0:
            break
        size_token = body[pos:line_end].split(b";")[0].strip()
        try:
            size = int(size_token, 16)
        except ValueError:
            break
        if size == 0:
            break
        chunk_start = line_end + 2
        out += body[chunk_start : chunk_start + size]
        pos = chunk_start + size + 2  # skip trailing CRLF
    return bytes(out)


def parse_warc_record(record: bytes) -> bytes:
    """Extract the HTTP payload from one decompressed WARC response record.

    Layout: WARC header block CRLFCRLF, HTTP status+headers CRLFCRLF, body.
    Handles chunked transfer encoding and inner gzip content encoding.

    Only ``WARC-Type: response`` records carry a real payload. ``revisit``
    records (Common Crawl emits them for content identical to an earlier
    capture) have no body — parsing one yields near-empty text that would be
    stored as a bogus page, so reject anything that isn't a response.
    """
    if not record.startswith(b"WARC/"):
        raise CollectError("not a WARC record")
    warc_end = record.find(b"\r\n\r\n")
    if warc_end < 0:
        raise CollectError("malformed WARC record (no header terminator)")
    warc_headers = record[:warc_end].lower()
    if b"warc-type:" in warc_headers and b"warc-type: response" not in warc_headers:
        kind = warc_headers.split(b"warc-type:", 1)[1].split(b"\r\n", 1)[0].strip().decode("ascii", "ignore")
        raise CollectError(f"WARC record is '{kind}', not a response (no payload)")
    http_part = record[warc_end + 4 :]
    http_end = http_part.find(b"\r\n\r\n")
    if http_end < 0:
        raise CollectError("malformed WARC record (no HTTP header terminator)")
    headers = http_part[:http_end].lower()
    body = http_part[http_end + 4 :].rstrip(b"\r\n")
    if b"transfer-encoding: chunked" in headers:
        body = _dechunk(body)
    if b"content-encoding: gzip" in headers or body[:2] == b"\x1f\x8b":
        try:
            body = zlib.decompress(body, wbits=47)  # tolerate gzip or zlib wrappers
        except zlib.error:
            logger.debug("collect: inner gzip decode failed, keeping body as-is")
    return body


def fetch_cc_raw(client: PoliteClient, row: CdxRow) -> bytes:
    if not row.warc_filename or row.warc_offset is None or row.warc_length is None:
        raise CollectError("CC row lacks WARC coordinates")
    end = row.warc_offset + row.warc_length - 1
    response = client.get(
        f"{CC_DATA_URL}/{row.warc_filename}",
        headers={"Range": f"bytes={row.warc_offset}-{end}"},
    )
    if response.status_code not in (200, 206):
        raise CollectError(f"CC WARC range fetch HTTP {response.status_code}")
    try:
        record = gzip.decompress(response.content)
    except OSError as exc:
        raise CollectError(f"CC WARC record gunzip failed: {exc}") from exc
    payload = parse_warc_record(record)
    if len(payload) > client.max_bytes:
        raise CollectError(f"payload too large ({len(payload)} bytes)")
    return payload


# --------------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------------

def _spread(items: list, n: int) -> list:
    """Evenly-spaced sample of up to n items, preserving order and endpoints."""
    if n <= 0 or not items:
        return []
    if len(items) <= n:
        return items
    step = (len(items) - 1) / (n - 1) if n > 1 else 1
    seen: set[int] = set()
    out = []
    for i in range(n):
        idx = round(i * step)
        if idx not in seen:
            seen.add(idx)
            out.append(items[idx])
    return out


def pick_spread(rows: list[CdxRow], n: int) -> list[CdxRow]:
    """Pick up to n captures evenly spaced over time, one per distinct digest.

    Collapsing to distinct digests first means byte-identical re-crawls don't
    crowd out genuinely different captures, so the sample maximizes the
    near-duplicate signal the dedup eval feeds on.
    """
    unique: dict[str, CdxRow] = {}
    for row in sorted(rows, key=lambda r: r.timestamp):
        unique.setdefault(row.digest or row.timestamp, row)
    return _spread(list(unique.values()), n)


def sample_entry_rows(entry: SiteEntry, rows: list[CdxRow]) -> list[CdxRow]:
    """Apply url_include, group by URL, cap distinct URLs, spread snapshots.

    Used for Common Crawl, whose index returns each URL roughly once per
    crawl, so grouping a flat prefix result already yields distinct pages.
    """
    include = entry.url_include_re()
    by_url: dict[str, list[CdxRow]] = {}
    for row in rows:
        if include and not include.search(row.url):
            continue
        by_url.setdefault(row.url, []).append(row)
    if not by_url:
        return []
    if entry.urls:
        chosen_urls = list(by_url)
    else:
        # Spread across the sorted distinct URLs so we sample many sections,
        # not just whichever sorts first under the row limit.
        chosen_urls = _spread(sorted(by_url), entry.max_urls_per_prefix)
    selected: list[CdxRow] = []
    for url in chosen_urls:
        selected.extend(pick_spread(by_url[url], entry.snapshots_per_url))
    return selected


def _select_detail_urls(entry: SiteEntry, rows: list[CdxRow]) -> list[str]:
    """From discovery rows pick distinct URLs matching url_include, spread
    evenly across the sorted set for section diversity."""
    include = entry.url_include_re()
    urls: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if row.url in seen:
            continue
        seen.add(row.url)
        if include and not include.search(row.url):
            continue
        urls.append(row.url)
    urls.sort()
    return _spread(urls, entry.max_urls_per_prefix)


def wayback_entry_rows(
    entry: SiteEntry, cfg: EvalConfig, client: PoliteClient, stats: dict
) -> list[CdxRow]:
    """Two-phase Wayback collection: discover distinct detail URLs, then pull
    a time-spread of captures for each so near-duplicates are represented."""
    if entry.urls:
        urls = list(entry.urls)
    else:
        discovered = wayback_query(
            client, entry.prefix, "prefix", entry.from_year, entry.to_year,
            cfg.collect.cdx_discovery_limit, collapse="urlkey",
        )
        stats["cdx_rows"] += len(discovered)
        urls = _select_detail_urls(entry, discovered)
        logger.info("collect[%s]: wayback discovery -> %d distinct URLs, %d selected",
                    entry.key, len({r.url for r in discovered}), len(urls))
    selected: list[CdxRow] = []
    for url in urls:
        # Isolate each per-URL query: a 503 on one URL must not discard the
        # captures already gathered for its siblings.
        try:
            captures = wayback_query(
                client, url, "exact", entry.from_year, entry.to_year,
                cfg.collect.cdx_row_limit, collapse="digest",
            )
        except CollectError as exc:
            stats["query_errors"] = stats.get("query_errors", 0) + 1
            logger.warning("collect[%s]: snapshot query failed for %s: %s", entry.key, url, exc)
            continue
        stats["cdx_rows"] += len(captures)
        selected.extend(pick_spread(captures, entry.snapshots_per_url))
    return selected


def cc_entry_rows(
    entry: SiteEntry, cfg: EvalConfig, client: PoliteClient, stats: dict
) -> list[CdxRow]:
    """Common Crawl collection: flat prefix/exact query across the collections
    overlapping the date range, then client-side URL grouping."""
    targets = list(entry.urls) if entry.urls else [entry.prefix]
    match_type = "exact" if entry.urls else "prefix"
    rows: list[CdxRow] = []
    for coll in cc_collections(client, entry.from_year, entry.to_year, cfg.collect.max_cc_collections):
        for target in targets:
            # Isolate each collection×target query so one bad index shard
            # doesn't drop the rows gathered from the others.
            try:
                rows.extend(cc_query(client, coll["cdx-api"], target, match_type, cfg.collect.cdx_discovery_limit))
            except CollectError as exc:
                stats["query_errors"] = stats.get("query_errors", 0) + 1
                logger.warning("collect[%s]: CC query failed (%s / %s): %s", entry.key, coll.get("id"), target, exc)
    stats["cdx_rows"] += len(rows)
    return sample_entry_rows(entry, rows)


# --------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------

def _seed_labels(catalog: Catalog, entry: SiteEntry, snapshot_id: int) -> None:
    catalog.set_label(snapshot_id, "category", entry.category, "manifest")
    if entry.expected_page_type != "mixed":
        catalog.set_label(snapshot_id, "page_type", entry.expected_page_type, "manifest")
    if entry.era_hint:
        catalog.set_label(snapshot_id, "era_hint", entry.era_hint, "manifest")
    if entry.dedup_group:
        catalog.set_label(snapshot_id, "dup_group", entry.dedup_group, "manifest")


def collect_entry(
    entry: SiteEntry,
    catalog: Catalog,
    store: BlobStore,
    cfg: EvalConfig,
    wayback: PoliteClient,
    commoncrawl: PoliteClient,
) -> dict:
    stats = {
        "site": entry.key, "cdx_rows": 0, "selected": 0,
        "fetched": 0, "cached": 0, "errors": 0, "query_errors": 0,
    }

    selected: list[CdxRow] = []
    for source in entry.sources:
        try:
            if source == "wayback":
                selected.extend(wayback_entry_rows(entry, cfg, wayback, stats))
            else:
                selected.extend(cc_entry_rows(entry, cfg, commoncrawl, stats))
        except CollectError as exc:
            logger.error("collect[%s]: %s query failed: %s", entry.key, source, exc)
            stats["errors"] += 1

    stats["selected"] = len(selected)
    if not selected:
        logger.warning(
            "collect[%s]: 0 snapshots selected (%d CDX rows) — check availability/url_include",
            entry.key, stats["cdx_rows"],
        )
        return stats

    for row in selected:
        ref = SnapshotRef(
            site_key=entry.key,
            url=row.url,
            source=row.source,
            timestamp=row.timestamp,
            cdx_digest=row.digest,
            status_code=row.status,
            mime=row.mime,
            fetch_url=row.fetch_url,
        )
        snapshot_id = catalog.upsert_snapshot(ref)
        _seed_labels(catalog, entry, snapshot_id)
        existing = catalog.snapshot_by_id(snapshot_id)
        if existing and existing["raw_sha256"]:
            stats["cached"] += 1
            continue
        try:
            payload = (
                fetch_wayback_raw(wayback, row)
                if row.source == "wayback"
                else fetch_cc_raw(commoncrawl, row)
            )
            sha, _ = store.put(payload)
            catalog.mark_fetched(
                snapshot_id, sha, len(payload),
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            stats["fetched"] += 1
            logger.info(
                "collect[%s]: fetched %s @%s (%d bytes, %s)",
                entry.key, row.url, row.timestamp, len(payload), row.source,
            )
        except CollectError as exc:
            catalog.mark_fetch_error(snapshot_id, str(exc))
            stats["errors"] += 1
            logger.error("collect[%s]: fetch failed %s @%s: %s", entry.key, row.url, row.timestamp, exc)
    return stats


def collect_all(
    entries: list[SiteEntry],
    catalog: Catalog,
    store: BlobStore,
    cfg: EvalConfig,
    site_filter: str | None = None,
) -> list[dict]:
    wayback = PoliteClient(cfg.collect.wayback_delay_seconds, cfg.collect)
    commoncrawl = PoliteClient(cfg.collect.commoncrawl_delay_seconds, cfg.collect)
    results = []
    try:
        for entry in entries:
            if site_filter and entry.key != site_filter:
                continue
            logger.info("collect: === %s (%s, %s) ===", entry.key, entry.category, entry.source)
            results.append(collect_entry(entry, catalog, store, cfg, wayback, commoncrawl))
    finally:
        wayback.close()
        commoncrawl.close()
    return results
