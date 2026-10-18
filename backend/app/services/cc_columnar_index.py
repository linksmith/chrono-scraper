"""
Common Crawl columnar-index discovery (Parquet on data.commoncrawl.org).

Each crawl publishes its index as ~300 Parquet files (``cc-index-table.paths.gz``).
Files are range-partitioned by ``url_surtkey`` (the SURT key: reversed host + path), but
the ranges of neighbouring files overlap and the row groups inside a file are several
interleaved sorted runs, not one sorted sequence. There is no Parquet page index, so a
row group can only be read whole, column chunk by column chunk.

Lookup therefore works in three steps, all over plain HTTP range requests that this
module paces and retries itself (never through a proxy):

1. *Footer map* (built once per crawl, cached on disk): the ``url_surtkey`` min/max and
   row count of every row group of every file. Costs one request per file.
2. *Candidate row groups*: those whose min/max range can contain the wanted key range.
3. *Two-phase read*: fetch only the tiny host/status/mime column chunks of the candidates,
   then the key and record columns only of row groups that actually contain the host.

The result is converted to the same ``CDXRecord`` shape the CDX index API path yields.
"""
import asyncio
import gzip
import io
import json
import logging
import os
import random
import struct
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import aiohttp
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .wayback_machine import CDXRecord

logger = logging.getLogger(__name__)

USER_AGENT = "Chrono-Scraper/2.0 Research Platform (+academic-research)"
FOOTER_TAIL_BYTES = 192 * 1024  # one suffix request normally covers the whole footer
MERGE_GAP_BYTES = 256 * 1024  # column chunks closer than this are fetched in one request
MAP_SAVE_EVERY = 25  # persist the footer map after this many new footers

SURTKEY_COL = "url_surtkey"
# Phase 1 columns are tiny (dictionary/RLE encoded, ~0.5 MB per row group), unlike url_surtkey
# (~15-19 MB), so row groups without the wanted host are dismissed almost for free.
FILTER_COLS = ("url_host_name", "fetch_status", "content_mime_type")
RECORD_COLS = ("url", "fetch_time", "content_digest", "warc_filename",
               "warc_record_offset", "warc_record_length")
HTML_MIME = "text/html"
PDF_MIME = "application/pdf"


class ColumnarIndexError(Exception):
    """The columnar index could not be read (HTTP failure, missing crawl, bad file)."""


# --------------------------------------------------------------------------
# SURT keys and key ranges
# --------------------------------------------------------------------------

def host_to_surt(host: str) -> str:
    """``www.Example.co.uk`` -> ``uk,co,example`` (lowercase, no www, no port, reversed)."""
    host = host.strip().lower().rsplit("@", 1)[-1].split(":", 1)[0].strip(".")
    if host.startswith("www."):
        host = host[4:]
    return ",".join(reversed(host.split(".")))


def url_to_surt_prefix(url: str, default_host: str = "") -> str:
    """SURT key of a URL (``host)/path?sorted=query``), lowercased, used as a prefix/exact key."""
    if url.startswith("/"):
        url = f"{default_host}{url}"
    if "://" not in url:
        url = f"http://{url}"
    parts = urlsplit(url)
    path = (parts.path or "/").lower()
    key = f"{host_to_surt(parts.hostname or '')})" + path
    if parts.query:
        key += "?" + "&".join(sorted(parts.query.lower().split("&")))
    return key


@dataclass(frozen=True)
class KeyMatcher:
    """What rows of the index a query wants, as a SURT key range plus a row predicate."""
    mode: str  # "domain" | "prefix" | "exact"
    key: str

    @property
    def lo(self) -> str:
        return self.key

    @property
    def hi(self) -> str:
        return self.key if self.mode == "exact" else self.key + "\U0010ffff"

    @property
    def host(self) -> str:
        """Host (without www) the key range lives on, e.g. ``nl,linksmith,coderood`` -> its dotted name."""
        return ".".join(reversed(self.key.split(")", 1)[0].split(",")))

    def overlaps(self, rg_min: str, rg_max: str) -> bool:
        return rg_min <= self.hi and rg_max >= self.lo

    def host_mask(self, hosts: pa.ChunkedArray) -> pa.ChunkedArray:
        """Coarse row filter on ``url_host_name``: a superset of ``mask`` (exact for hosts)."""
        wanted = pc.or_(pc.equal(hosts, self.host), pc.equal(hosts, f"www.{self.host}"))
        return pc.or_(wanted, pc.ends_with(hosts, f".{self.host}")) if self.mode == "domain" else wanted

    def mask(self, keys: pa.ChunkedArray) -> pa.ChunkedArray:
        """Boolean mask of the rows of ``keys`` (url_surtkey values) this query wants."""
        if self.mode == "exact":
            return pc.equal(keys, self.key)
        starts = pc.starts_with(keys, self.key)
        if self.mode == "prefix":
            return starts
        # domain: the host itself or any subdomain, never a longer sibling host name
        nxt = pc.utf8_slice_codeunits(keys, len(self.key), len(self.key) + 1)
        return pc.and_(starts, pc.is_in(nxt, value_set=pa.array([")", ","])))


def build_key_matcher(domain_name: str, match_type: str, url_path: Optional[str]) -> KeyMatcher:
    """Translate the scrape task's (domain, match_type, url_path) into a SURT key query."""
    if match_type in ("prefix", "exact") and url_path:
        return KeyMatcher(match_type, url_to_surt_prefix(url_path, default_host=domain_name))
    return KeyMatcher("domain", host_to_surt(urlsplit(domain_name if "://" in domain_name
                                                      else f"http://{domain_name}").hostname or domain_name))


def _timestamp_bounds(from_date: str, to_date: str) -> Tuple[str, str]:
    """YYYYMMDD[hhmmss] bounds as 14-digit inclusive strings (like the index API's from/to)."""
    return (from_date or "").ljust(14, "0")[:14] or "0" * 14, (to_date or "").ljust(14, "9")[:14] or "9" * 14


# --------------------------------------------------------------------------
# HTTP range access
# --------------------------------------------------------------------------

class _SparseFile(io.RawIOBase):
    """Read-only file made of byte ranges fetched up front; touching anything else is an error
    (so pyarrow can never trigger a hidden, unpaced network request)."""

    def __init__(self, size: int):
        self._size = size
        self._pos = 0
        self._segments: List[Tuple[int, bytes]] = []

    def add(self, start: int, data: bytes) -> None:
        self._segments.append((start, data))

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        self._pos = offset if whence == io.SEEK_SET else (
            self._pos + offset if whence == io.SEEK_CUR else self._size + offset)
        return self._pos

    def readinto(self, buf) -> int:
        n = min(len(buf), max(0, self._size - self._pos))
        if n == 0:
            return 0
        for start, data in self._segments:
            if start <= self._pos and self._pos + n <= start + len(data):
                buf[:n] = data[self._pos - start:self._pos - start + n]
                self._pos += n
                return n
        raise ColumnarIndexError(f"read of bytes {self._pos}-{self._pos + n} was not prefetched")


class RangeFetcher:
    """Paced, retrying HTTP GETs against data.commoncrawl.org, shared by all lookups of a client."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, min_interval: float,
                 max_retries: int, backoff_base: float):
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._min_interval = min_interval
        self._max_retries = max(1, max_retries)
        self._backoff_base = backoff_base
        self._lock = asyncio.Lock()
        self._next_at = 0.0
        self.requests = 0
        self.bytes = 0

    async def _pace(self) -> None:
        async with self._lock:
            wait = self._next_at - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._next_at = time.monotonic() + self._min_interval

    def _cooldown(self, seconds: float) -> None:
        self._next_at = max(self._next_at, time.monotonic() + seconds)

    async def get(self, path: str, byte_range: Optional[str] = None) -> Tuple[bytes, Optional[int]]:
        """GET ``path`` (optionally with a Range header). Returns (body, total object size or None).

        429/5xx (CC answers 503 'Slow Down' to heavy users) and connection errors are retried
        with exponential backoff + jitter, honouring Retry-After, and pause every request of
        this fetcher meanwhile. 404 raises immediately."""
        url = f"{self._base_url}/{path.lstrip('/')}"
        headers = {"User-Agent": USER_AGENT}
        if byte_range:
            headers["Range"] = byte_range
        last_error = "unknown error"
        for attempt in range(1, self._max_retries + 1):
            await self._pace()
            delay = self._backoff_base * 2 ** (attempt - 1) * random.uniform(0.75, 1.25)
            try:
                async with self._session.get(url, headers=headers,
                                             timeout=aiohttp.ClientTimeout(total=900)) as resp:
                    self.requests += 1
                    if resp.status in (200, 206):
                        body = await resp.read()
                        self.bytes += len(body)
                        total = None
                        content_range = resp.headers.get("Content-Range", "")
                        if "/" in content_range and content_range.rsplit("/", 1)[1].isdigit():
                            total = int(content_range.rsplit("/", 1)[1])
                        return body, total
                    if resp.status == 404:
                        raise ColumnarIndexError(f"HTTP 404 for {url}")
                    last_error = f"HTTP {resp.status}"
                    if resp.status not in (429, 500, 502, 503, 504):
                        raise ColumnarIndexError(f"HTTP {resp.status} for {url}")
                    retry_after = resp.headers.get("Retry-After", "")
                    if retry_after.isdigit():
                        delay = min(300.0, max(delay, float(retry_after)))
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            self._cooldown(delay)
            if attempt < self._max_retries:
                logger.warning(f"CC columnar {path[-60:]} {last_error}; retry {attempt}/{self._max_retries - 1} "
                               f"after {delay:.0f}s pause")
        raise ColumnarIndexError(f"{url} failed after {self._max_retries} tries: {last_error}")


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------

def _chunk_range(col_meta) -> Tuple[int, int]:
    """(start, size) of a column chunk including its dictionary page."""
    offsets = [o for o in (col_meta.dictionary_page_offset, col_meta.data_page_offset) if o]
    return min(offsets), col_meta.total_compressed_size


def _merge_ranges(ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Merge (start, size) ranges whose gap is under MERGE_GAP_BYTES into fewer requests."""
    merged: List[List[int]] = []
    for start, size in sorted(ranges):
        if merged and start - (merged[-1][0] + merged[-1][1]) <= MERGE_GAP_BYTES:
            merged[-1][1] = max(merged[-1][1], start + size - merged[-1][0])
        else:
            merged.append([start, size])
    return [(s, n) for s, n in merged]


@dataclass
class _OpenFile:
    """A remote Parquet file whose footer is loaded; column chunks are added by ``_prefetch``."""
    pf: pq.ParquetFile
    sparse: _SparseFile


class ColumnarIndexClient:
    """Looks up one domain/prefix in the columnar index of a crawl."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, cache_dir: str,
                 min_interval: float, max_retries: int, backoff_base: float, concurrency: int = 4):
        self.fetcher = RangeFetcher(session, base_url, min_interval, max_retries, backoff_base)
        self._concurrency = max(1, concurrency)
        self._cache_dir = self._usable_cache_dir(Path(cache_dir))

    @staticmethod
    def _usable_cache_dir(wanted: Path) -> Path:
        try:
            wanted.mkdir(parents=True, exist_ok=True)
            probe = wanted / ".write-test"
            probe.touch()
            probe.unlink()
            return wanted
        except OSError as exc:
            fallback = Path(tempfile.gettempdir()) / "cc_columnar_index"
            fallback.mkdir(parents=True, exist_ok=True)
            logger.warning(f"CC columnar cache dir {wanted} not writable ({exc}); using {fallback}, "
                           "which does not survive a restart")
            return fallback

    # -- crawl file list and footer map (cached on disk) -----------------

    def _cache_file(self, crawl_id: str, name: str) -> Path:
        return self._cache_dir / crawl_id / name

    @staticmethod
    def _write_json(path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data))
        os.replace(tmp, path)

    async def list_files(self, crawl_id: str) -> List[str]:
        """Parquet files of the crawl's ``subset=warc`` index table, in listed order."""
        cached = self._cache_file(crawl_id, "paths.json")
        if cached.exists():
            return json.loads(cached.read_text())
        body, _ = await self.fetcher.get(f"crawl-data/{crawl_id}/cc-index-table.paths.gz")
        paths = [p for p in gzip.decompress(body).decode().split()
                 if "subset=warc" in p and p.endswith(".parquet")]
        if not paths:
            raise ColumnarIndexError(f"{crawl_id}: no warc parquet files listed")
        self._write_json(cached, paths)
        return paths

    async def _read_footer(self, path: str) -> "_OpenFile":
        """Fetch a file's footer (one suffix request, a second only if the footer is larger)
        and return a ParquetFile that can only read what is prefetched into it."""
        tail, total = await self.fetcher.get(path, f"bytes=-{FOOTER_TAIL_BYTES}")
        if total is None:
            raise ColumnarIndexError(f"{path}: server did not report the object size")
        footer_len = struct.unpack("<I", tail[-8:-4])[0]
        if tail[-4:] != b"PAR1":
            raise ColumnarIndexError(f"{path}: not a parquet file")
        sparse = _SparseFile(total)
        sparse.add(total - len(tail), tail)
        if footer_len + 8 > len(tail):
            start = total - footer_len - 8
            extra, _ = await self.fetcher.get(path, f"bytes={start}-{total - len(tail) - 1}")
            sparse.add(start, extra)
        return _OpenFile(pq.ParquetFile(pa.PythonFile(sparse, mode="r")), sparse)

    @staticmethod
    def _rg_stats(pf: pq.ParquetFile) -> List[List]:
        names = pf.schema_arrow.names
        k = names.index(SURTKEY_COL)
        out = []
        for g in range(pf.metadata.num_row_groups):
            rg = pf.metadata.row_group(g)
            st = rg.column(k).statistics
            try:
                bounds = [st.min, st.max] if st is not None and st.has_min_max else None
            except UnicodeDecodeError:  # a truncated bound cut inside a multi-byte character
                bounds = None
            # Without usable statistics the row group is simply always a candidate.
            out.append((bounds or ["", "\U0010ffff"]) + [rg.num_rows])
        return out

    async def footer_map(self, crawl_id: str) -> Dict[str, dict]:
        """``{file path: {"rgs": [[surtkey min, max, rows], ...]}}`` for the whole crawl.
        Built incrementally (resumable after a crash) and cached under the cache dir."""
        paths = await self.list_files(crawl_id)
        cache = self._cache_file(crawl_id, "footer_map.json")
        fmap: Dict[str, dict] = json.loads(cache.read_text()) if cache.exists() else {}
        missing = [p for p in paths if p not in fmap]
        if not missing:
            return fmap
        logger.info(f"CC columnar {crawl_id}: building footer map, {len(missing)}/{len(paths)} footers to fetch")
        started = time.monotonic()
        sem = asyncio.Semaphore(self._concurrency)

        async def add_footer(path: str) -> None:
            async with sem:
                fmap[path] = {"rgs": self._rg_stats((await self._read_footer(path)).pf)}
                if len(fmap) % MAP_SAVE_EVERY == 0:
                    self._write_json(cache, fmap)
                    logger.info(f"CC columnar {crawl_id}: footer map {len(fmap)}/{len(paths)} "
                                f"({time.monotonic() - started:.0f}s)")

        tasks = [asyncio.ensure_future(add_footer(p)) for p in missing]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._write_json(cache, fmap)  # keep progress; the next call resumes
            raise
        self._write_json(cache, fmap)
        logger.info(f"CC columnar {crawl_id}: footer map complete ({len(paths)} files, "
                    f"{time.monotonic() - started:.0f}s)")
        return fmap

    # -- query ------------------------------------------------------------

    async def _prefetch(self, of: "_OpenFile", path: str, group: int, columns) -> None:
        names = of.pf.schema_arrow.names
        rg = of.pf.metadata.row_group(group)
        wanted = [_chunk_range(rg.column(names.index(c))) for c in columns]
        for start, size in _merge_ranges(wanted):
            data, _ = await self.fetcher.get(path, f"bytes={start}-{start + size - 1}")
            of.sparse.add(start, data)

    @staticmethod
    def _read_column(pf: pq.ParquetFile, group: int, column: str) -> pa.ChunkedArray:
        return pf.read_row_group(group, columns=[column]).column(column)

    async def query_crawl(self, crawl_id: str, matcher: KeyMatcher, from_date: str, to_date: str,
                          include_attachments: bool, limit: int) -> List[CDXRecord]:
        """Matching records of one crawl: status 200, HTML (+PDF), within the date range."""
        started = time.monotonic()
        requests_before, bytes_before = self.fetcher.requests, self.fetcher.bytes
        fmap = await self.footer_map(crawl_id)
        candidates: Dict[str, List[int]] = {}
        for path, entry in fmap.items():
            groups = [g for g, (lo, hi, _rows) in enumerate(entry["rgs"]) if matcher.overlaps(lo, hi)]
            if groups:
                candidates[path] = groups
        mimes = [HTML_MIME, PDF_MIME] if include_attachments else [HTML_MIME]
        ts_from, ts_to = _timestamp_bounds(from_date, to_date)

        records: List[Tuple[str, CDXRecord]] = []
        row_groups = sum(len(g) for g in candidates.values())
        for path, groups in candidates.items():
            of = await self._read_footer(path)
            for group in groups:
                if len(records) >= limit:
                    break
                records.extend(await self._query_row_group(of, path, group, matcher, mimes, ts_from, ts_to))
        records.sort(key=lambda item: (item[0], item[1].timestamp))
        result = [rec for _, rec in records[:limit]]
        logger.info(
            f"CC columnar {crawl_id}: {len(result)} records from {row_groups} candidate row groups in "
            f"{len(candidates)} files, {self.fetcher.requests - requests_before} requests, "
            f"{(self.fetcher.bytes - bytes_before) / 1e6:.1f} MB, {time.monotonic() - started:.1f}s"
        )
        return result

    async def _query_row_group(self, of, path, group, matcher, mimes, ts_from, ts_to
                               ) -> List[Tuple[str, CDXRecord]]:
        # Phase 1: host/status/mime chunks only, to see whether this row group holds anything.
        await self._prefetch(of, path, group, FILTER_COLS)
        hosts = await asyncio.to_thread(self._read_column, of.pf, group, "url_host_name")
        status = await asyncio.to_thread(self._read_column, of.pf, group, "fetch_status")
        mime = await asyncio.to_thread(self._read_column, of.pf, group, "content_mime_type")
        mask = pc.and_(matcher.host_mask(hosts), pc.equal(pc.cast(status, pa.string()), "200"))
        mask = pc.and_(mask, pc.is_in(mime, value_set=pa.array(mimes)))
        if not pc.any(mask).as_py():
            return []

        # Phase 2: key + record columns, only for row groups that hold candidate rows.
        # A domain query is already exact on url_host_name, so its 15-19 MB key chunk is skipped.
        needs_key = matcher.mode != "domain"
        await self._prefetch(of, path, group, ((SURTKEY_COL,) if needs_key else ()) + RECORD_COLS)
        keys = None
        if needs_key:
            keys = await asyncio.to_thread(self._read_column, of.pf, group, SURTKEY_COL)
            mask = pc.and_(mask, matcher.mask(keys))
        rows = pc.indices_nonzero(mask)
        if len(rows) == 0:
            return []
        cols = {}
        for name in RECORD_COLS:
            col = await asyncio.to_thread(self._read_column, of.pf, group, name)
            cols[name] = col.take(rows)
        # whole seconds only: strftime on a ms/us timestamp would append ".000"
        cols["fetch_time"] = pc.strftime(pc.cast(cols["fetch_time"], pa.timestamp("s")),
                                         format="%Y%m%d%H%M%S")
        sort_keys = keys.take(rows) if needs_key else cols["url"]  # stable output order
        mime = mime.take(rows)

        out: List[Tuple[str, CDXRecord]] = []
        for i in range(len(rows)):
            ts = cols["fetch_time"][i].as_py()
            if not ts_from <= ts <= ts_to:
                continue
            offset, length = cols["warc_record_offset"][i].as_py(), cols["warc_record_length"][i].as_py()
            out.append((sort_keys[i].as_py(), CDXRecord.from_common_crawl_response({
                "timestamp": ts,
                "url": cols["url"][i].as_py(),
                "mimetype": mime[i].as_py(),
                "statuscode": "200",
                "digest": cols["content_digest"][i].as_py() or "",
                "length": str(length) if length is not None else "",
                "filename": cols["warc_filename"][i].as_py(),
                "offset": int(offset) if offset is not None else None,
                "warc_length": int(length) if length is not None else None,
            })))
        return out
