"""Offline tests for the collector's pure logic and its integration seams.

No network: CDX/WARC responses are synthesized. These lock down the parsing
and sampling that can only otherwise be checked against the live archives,
plus the empty-selection path that once crashed the whole run.
"""

import gzip

import pytest

from evals.collect import (
    CdxRow,
    _dechunk,
    _spread,
    _select_detail_urls,
    collect_entry,
    parse_retry_after,
    parse_warc_record,
    pick_spread,
    sample_entry_rows,
)
from evals.config import load_config
from evals.manifest import SiteEntry
from evals.storage import BlobStore, Catalog
from evals.urls import canonicalize_url


# --- WARC / HTTP parsing --------------------------------------------------

def _warc(http_headers: bytes, body: bytes) -> bytes:
    http_block = http_headers + b"\r\n\r\n" + body
    warc = (
        b"WARC/1.0\r\n"
        b"WARC-Type: response\r\n"
        b"WARC-Target-URI: http://example.com/\r\n"
        b"Content-Type: application/http; msgtype=response\r\n"
        b"Content-Length: " + str(len(http_block)).encode() + b"\r\n"
        b"\r\n" + http_block
    )
    return warc


def test_parse_warc_record_plain():
    record = _warc(b"HTTP/1.1 200 OK\r\nContent-Type: text/html", b"<html><body>hi</body></html>")
    assert parse_warc_record(record) == b"<html><body>hi</body></html>"


def test_parse_warc_record_chunked():
    body = b"1e\r\n<html><body>hello world</body>\r\n8\r\n</html>\n\r\n0\r\n\r\n"
    record = _warc(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked", body)
    assert parse_warc_record(record) == b"<html><body>hello world</body></html>\n"


def test_parse_warc_record_gzip_content_encoding():
    inner = gzip.compress(b"<html>gzipped</html>")
    record = _warc(b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip", inner)
    assert parse_warc_record(record) == b"<html>gzipped</html>"


def test_parse_warc_record_rejects_non_warc():
    with pytest.raises(Exception):
        parse_warc_record(b"HTTP/1.1 200 OK\r\n\r\nhi")


def test_parse_warc_record_rejects_revisit():
    # revisit records have no payload; must be rejected, not stored as a page.
    record = (
        b"WARC/1.0\r\nWARC-Type: revisit\r\n"
        b"WARC-Refers-To-Target-URI: http://example.com/\r\n\r\n"
        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
    )
    with pytest.raises(Exception):
        parse_warc_record(record)


# --- Retry-After parsing (was a crash: float() on an HTTP-date) -----------

def test_parse_retry_after_delta_seconds():
    assert parse_retry_after("120") == 120.0
    assert parse_retry_after("0") == 0.0


def test_parse_retry_after_http_date_does_not_crash():
    # An HTTP-date must parse to a non-negative bounded number, never raise.
    val = parse_retry_after("Wed, 21 Oct 2099 07:28:00 GMT")
    assert isinstance(val, float) and 0.0 <= val <= 300.0


def test_parse_retry_after_garbage_and_none():
    assert parse_retry_after(None) == 0.0
    assert parse_retry_after("soon-ish") == 0.0
    assert parse_retry_after("-5") == 0.0  # clamped


def test_parse_retry_after_is_clamped():
    assert parse_retry_after("999999") == 300.0


def test_dechunk_basic():
    assert _dechunk(b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n") == b"hello world"


def test_dechunk_handles_extension_and_early_end():
    assert _dechunk(b"3;ext=1\r\nabc\r\n0\r\n") == b"abc"


# --- URL canonicalization -------------------------------------------------

def test_canonicalize_strips_fragment_and_default_ports():
    assert canonicalize_url("http://www.w3.org:80/TR/REC-CSS1#list") == "http://www.w3.org/TR/REC-CSS1"
    assert canonicalize_url("https://x.com:443/a") == "https://x.com/a"
    assert canonicalize_url("http://EN.wikipedia.org:80/wiki/Internet#Sec") == "http://en.wikipedia.org/wiki/Internet"


def test_canonicalize_preserves_query_identity():
    # article.pl?sid= and item?id= are real page identity — must survive.
    assert canonicalize_url("http://slashdot.org:80/article.pl?05/16/1") == "http://slashdot.org/article.pl?05/16/1"
    assert canonicalize_url("https://news.ycombinator.com/item?id=42") == "https://news.ycombinator.com/item?id=42"


def test_canonicalize_variants_collapse_to_same_key():
    variants = [
        "http://en.wikipedia.org/wiki/Internet",
        "http://en.wikipedia.org:80/wiki/Internet",
        "http://en.wikipedia.org:80/wiki/Internet#The_World_Wide_Web",
    ]
    assert len({canonicalize_url(v) for v in variants}) == 1


def test_canonicalize_trailing_slash():
    assert canonicalize_url("http://w3.org/TR/REC-CSS1/") == "http://w3.org/TR/REC-CSS1"
    assert canonicalize_url("http://w3.org:80/TR/REC-CSS1/#x") == "http://w3.org/TR/REC-CSS1"
    # bare root keeps its slash; a query is left intact
    assert canonicalize_url("http://w3.org/") == "http://w3.org/"
    assert canonicalize_url("http://x.com/search/?q=1") == "http://x.com/search/?q=1"


# --- sampling -------------------------------------------------------------

def test_spread_edges():
    assert _spread([], 3) == []
    assert _spread([1, 2], 5) == [1, 2]
    assert _spread([1, 2, 3, 4, 5], 1) == [1]
    out = _spread(list(range(10)), 3)
    assert out[0] == 0 and out[-1] == 9 and len(out) == 3


def _row(url, ts, digest):
    return CdxRow(url=url, timestamp=ts, digest=digest, mime="text/html", status=200, source="wayback")


def test_pick_spread_dedupes_by_digest():
    rows = [_row("u", "2001", "A"), _row("u", "2002", "A"), _row("u", "2003", "B")]
    picked = pick_spread(rows, 5)
    assert {r.digest for r in picked} == {"A", "B"}  # identical digests collapse


def test_select_detail_urls_applies_include_and_spreads():
    entry = SiteEntry(
        key="k", category="news", source="wayback", expected_page_type="article",
        from_year=2003, to_year=2006, prefix="news.bbc.co.uk/2/hi/",
        url_include=r"/\d{6,}\.stm$", max_urls_per_prefix=2,
    )
    rows = [
        _row("http://news.bbc.co.uk/2/hi/", "2003", "A"),          # section root - excluded
        _row("http://news.bbc.co.uk/2/hi/africa/111111.stm", "2003", "B"),
        _row("http://news.bbc.co.uk/2/hi/uk/222222.stm", "2003", "C"),
        _row("http://news.bbc.co.uk/2/hi/world/333333.stm", "2003", "D"),
    ]
    urls = _select_detail_urls(entry, rows)
    assert all(u.endswith(".stm") for u in urls)
    assert len(urls) == 2  # capped + spread across the 3 matching


# --- empty-selection regression -------------------------------------------

class _StubResponse:
    def __init__(self, json_data):
        self._json = json_data
        self.status_code = 200
        self.text = ""

    def json(self):
        return self._json


class _EmptyClient:
    """Returns a CDX JSON payload with only the header row (no captures)."""

    max_bytes = 10_000_000

    def get(self, url, *, params=None, headers=None, attempts=3):
        return _StubResponse([["timestamp", "original", "mimetype", "statuscode", "digest", "length"]])

    def get_bytes(self, url, *, headers=None, attempts=3, tolerate_incomplete=False):
        return 200, b""


def test_collect_entry_empty_selection_does_not_crash(tmp_path):
    # Regression: the "0 snapshots selected" path once referenced an undefined
    # variable and crashed the entire run on the first barren site.
    cfg = load_config(tmp_path)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    catalog = Catalog(cfg.catalog_path)
    store = BlobStore(cfg.objects_dir)
    entry = SiteEntry(
        key="barren", category="news", source="wayback", expected_page_type="article",
        from_year=2003, to_year=2006, urls=("http://example.com/gone",),
    )
    client = _EmptyClient()
    stats = collect_entry(entry, catalog, store, cfg, client, client)
    assert stats["selected"] == 0
    assert stats["fetched"] == 0
    catalog.close()
