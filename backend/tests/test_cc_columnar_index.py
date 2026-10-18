"""
Tests for Common Crawl columnar-index discovery. All I/O is mocked: Parquet files are written
locally with pyarrow and served through a fake range fetcher that counts requests.
"""
import json
import re
from datetime import datetime
from pathlib import Path

import aiohttp
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.core.config import settings
from app.services import cc_columnar_index as cci
from app.services.cc_columnar_index import (
    ColumnarIndexClient,
    ColumnarIndexError,
    RangeFetcher,
    build_key_matcher,
    host_to_surt,
    url_to_surt_prefix,
)
from app.services.common_crawl_direct_service import CommonCrawlDirectService, DirectCommonCrawlException

CRAWL = "CC-MAIN-2021-04"
DIR = f"cc-index/table/cc-main/warc/crawl={CRAWL}/subset=warc"


def _row(surt, url, ts, status="200", mime="text/html", digest="D", offset=10, length=500):
    return {
        "url_surtkey": surt, "url": url, "url_host_name": url.split("/")[2], "fetch_time": datetime.strptime(ts, "%Y%m%d%H%M%S"),
        "fetch_status": int(status), "content_mime_type": mime, "content_digest": digest,
        "warc_filename": f"crawl-data/{CRAWL}/segments/x/warc/f-{ts}.warc.gz",
        "warc_record_offset": offset, "warc_record_length": length,
    }


SCHEMA = pa.schema([
    ("url_surtkey", pa.string()), ("url", pa.string()), ("url_host_name", pa.string()), ("fetch_time", pa.timestamp("ms")),
    ("fetch_status", pa.int16()), ("content_mime_type", pa.string()), ("content_digest", pa.string()),
    ("warc_filename", pa.string()), ("warc_record_offset", pa.int64()), ("warc_record_length", pa.int64()),
])

# file 0: one row group before the domain, one with it; file 1: another row group holding more of it
FILE0_RG0 = [_row("nl,aaa)/", "https://aaa.nl/", "20210110000000")]
FILE0_RG1 = [
    _row("nl,linksmith,coderood)/", "https://coderood.linksmith.nl/", "20210120120000", digest="HOME", offset=111, length=222),
    _row("nl,linksmith,coderood)/a", "https://coderood.linksmith.nl/a", "20210121000000"),
    _row("nl,linksmith,coderood)/doc.pdf", "https://coderood.linksmith.nl/doc.pdf", "20210121000000", mime="application/pdf"),
    _row("nl,linksmith,coderood)/gone", "https://coderood.linksmith.nl/gone", "20210121000000", status="404"),
    _row("nl,linksmith,coderood)/img", "https://coderood.linksmith.nl/img", "20210121000000", mime="image/png"),
    _row("nl,linksmith,coderood)/old", "https://coderood.linksmith.nl/old", "20190101000000"),
    _row("nl,linksmith,coderood,blog)/p", "https://blog.coderood.linksmith.nl/p", "20210122000000"),
    _row("nl,linksmith,coderood2)/x", "https://coderood2.linksmith.nl/x", "20210122000000"),
]
FILE1_RG0 = [
    _row("nl,linksmith,coderood)/z", "https://coderood.linksmith.nl/z", "20210123000000"),
    _row("nl,zzz)/", "https://zzz.nl/", "20210123000000"),
]
FILE1_RG1 = [_row("com,other)/", "https://other.com/", "20210124000000")]  # a later sorted run


def _write(path: Path, row_groups):
    with pq.ParquetWriter(path, SCHEMA, compression="gzip") as writer:
        for rows in row_groups:
            writer.write_table(pa.Table.from_pylist(rows, schema=SCHEMA))


@pytest.fixture
def crawl_files(tmp_path):
    remote = tmp_path / "remote"
    (remote / DIR).mkdir(parents=True)
    names = [f"{DIR}/part-00000.gz.parquet", f"{DIR}/part-00001.gz.parquet"]
    _write(remote / names[0], [FILE0_RG0, FILE0_RG1])
    _write(remote / names[1], [FILE1_RG0, FILE1_RG1])
    import gzip
    (remote / f"crawl-data/{CRAWL}").mkdir(parents=True)
    listing = names + [f"{DIR.replace('subset=warc', 'subset=robotstxt')}/part-00000.gz.parquet"]
    (remote / f"crawl-data/{CRAWL}/cc-index-table.paths.gz").write_bytes(gzip.compress("\n".join(listing).encode()))
    return remote


class FakeCDN:
    """Stands in for RangeFetcher.get: serves local files, honours Range, records every request."""

    def __init__(self, root: Path):
        self.root, self.calls = root, []

    async def get(self, path, byte_range=None):
        data = (self.root / path).read_bytes()
        self.calls.append((path, byte_range))
        total = len(data)
        if byte_range:
            m = re.fullmatch(r"bytes=(-?)(\d+)(?:-(\d+))?", byte_range)
            if m.group(1):
                start, end = max(0, total - int(m.group(2))), total - 1
            else:
                start, end = int(m.group(2)), int(m.group(3))
            return data[start:end + 1], total
        return data, None


@pytest.fixture
def client(crawl_files, tmp_path, monkeypatch):
    c = ColumnarIndexClient(session=None, base_url="https://cdn", cache_dir=str(tmp_path / "cache"),
                            min_interval=0, max_retries=2, backoff_base=0.01)
    cdn = FakeCDN(crawl_files)
    monkeypatch.setattr(c.fetcher, "get", cdn.get)
    c.cdn = cdn
    return c


# --------------------------------------------------------------------------
# SURT keys and filter translation
# --------------------------------------------------------------------------

def test_host_to_surt():
    assert host_to_surt("coderood.linksmith.nl") == "nl,linksmith,coderood"
    assert host_to_surt("WWW.Example.CO.UK:8080") == "uk,co,example"


def test_url_to_surt_prefix_lowercases_sorts_query_and_resolves_bare_paths():
    assert url_to_surt_prefix("https://www.A.nl/Blog/Post?b=2&a=1") == "nl,a)/blog/post?a=1&b=2"
    assert url_to_surt_prefix("a.nl") == "nl,a)/"
    assert url_to_surt_prefix("/blog", default_host="a.nl") == "nl,a)/blog"


def test_domain_matcher_takes_host_and_subdomains_but_not_longer_sibling():
    m = build_key_matcher("coderood.linksmith.nl", "domain", None)
    keys = pa.chunked_array([[
        "nl,linksmith,coderood)/a", "nl,linksmith,coderood,blog)/p", "nl,linksmith,coderood2)/x",
        "nl,linksmith)/", "nl,linksmith,coderoo)/",
    ]])
    assert m.mask(keys).to_pylist() == [True, True, False, False, False]
    assert (m.lo, m.mode) == ("nl,linksmith,coderood", "domain")


def test_prefix_matcher_uses_url_path_and_exact_matches_only_that_key():
    prefix = build_key_matcher("a.nl", "prefix", "https://a.nl/blog")
    keys = pa.chunked_array([["nl,a)/blog", "nl,a)/blog/post", "nl,a)/other"]])
    assert prefix.mask(keys).to_pylist() == [True, True, False]
    exact = build_key_matcher("a.nl", "exact", "https://a.nl/blog")
    assert exact.mask(keys).to_pylist() == [True, False, False]
    assert exact.hi == exact.lo


def test_prefix_without_url_path_and_unknown_types_fall_back_to_domain():
    assert build_key_matcher("a.nl", "prefix", None).mode == "domain"
    assert build_key_matcher("https://www.a.nl/", "domain", None).key == "nl,a"


def test_matcher_range_overlap():
    m = build_key_matcher("coderood.linksmith.nl", "domain", None)
    assert m.overlaps("nl,aaa)/", "nl,linksmith,coderood)/z")
    assert m.overlaps("nl,linksmith,coderood)/a", "nl,zzz)/")
    assert not m.overlaps("nl,aaa)/", "nl,linksmith,coder)/")
    assert not m.overlaps("nl,linksmith,coderooe)/", "nl,zzz)/")


# --------------------------------------------------------------------------
# Footer map (surt range -> file / row group)
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_footer_map_lists_only_warc_subset_and_holds_row_group_ranges(client):
    fmap = await client.footer_map(CRAWL)
    assert sorted(fmap) == [f"{DIR}/part-00000.gz.parquet", f"{DIR}/part-00001.gz.parquet"]
    rgs0 = fmap[f"{DIR}/part-00000.gz.parquet"]["rgs"]
    assert rgs0[0] == ["nl,aaa)/", "nl,aaa)/", 1]
    assert rgs0[1][:2] == ["nl,linksmith,coderood)/", "nl,linksmith,coderood2)/x"] and rgs0[1][2] == 8
    # one paths.gz + one footer request per file
    assert len(client.cdn.calls) == 3


@pytest.mark.asyncio
async def test_footer_map_is_cached_on_disk_and_resumable(client, crawl_files, tmp_path, monkeypatch):
    await client.footer_map(CRAWL)
    first = len(client.cdn.calls)
    await client.footer_map(CRAWL)
    assert len(client.cdn.calls) == first  # second call: zero requests

    # a fresh client over the same cache dir needs no requests either
    again = ColumnarIndexClient(None, "https://cdn", str(tmp_path / "cache"), 0, 2, 0.01)
    cdn = FakeCDN(crawl_files)
    monkeypatch.setattr(again.fetcher, "get", cdn.get)
    assert len(await again.footer_map(CRAWL)) == 2 and cdn.calls == []

    # drop one file from the cached map: only that footer is fetched again
    cache = tmp_path / "cache" / CRAWL / "footer_map.json"
    data = json.loads(cache.read_text())
    data.pop(f"{DIR}/part-00001.gz.parquet")
    cache.write_text(json.dumps(data))
    await again.footer_map(CRAWL)
    assert [c[0] for c in cdn.calls] == [f"{DIR}/part-00001.gz.parquet"]


@pytest.mark.asyncio
async def test_failed_footer_keeps_progress_for_the_next_attempt(client, tmp_path, monkeypatch):
    real_get = client.fetcher.get

    async def flaky(path, byte_range=None):
        if path.endswith("part-00001.gz.parquet"):
            raise ColumnarIndexError("boom")
        return await real_get(path, byte_range)

    monkeypatch.setattr(client.fetcher, "get", flaky)
    client._concurrency = 1
    with pytest.raises(ColumnarIndexError):
        await client.footer_map(CRAWL)
    saved = json.loads((tmp_path / "cache" / CRAWL / "footer_map.json").read_text())
    assert list(saved) == [f"{DIR}/part-00000.gz.parquet"]


# --------------------------------------------------------------------------
# Query: filters, record shape, request economy
# --------------------------------------------------------------------------

async def _urls(client, **kw):
    args = dict(matcher=build_key_matcher("coderood.linksmith.nl", "domain", None), from_date="20190101",
                to_date="20251231", include_attachments=False, limit=1000)
    args.update(kw)
    return await client.query_crawl(CRAWL, **args)


@pytest.mark.asyncio
async def test_query_applies_status_mime_date_and_domain_filters(client):
    recs = await _urls(client)
    assert [r.original_url for r in recs] == [
        "https://blog.coderood.linksmith.nl/p",
        "https://coderood.linksmith.nl/",
        "https://coderood.linksmith.nl/a",
        "https://coderood.linksmith.nl/old",
        "https://coderood.linksmith.nl/z",
    ]  # no pdf, 404, png, sibling domain coderood2; deterministic order (by URL for domain queries)


@pytest.mark.asyncio
async def test_query_includes_pdf_with_attachments_and_honours_date_range(client):
    with_pdf = await _urls(client, include_attachments=True, from_date="20210120", to_date="20210121")
    assert [r.original_url for r in with_pdf] == [
        "https://coderood.linksmith.nl/", "https://coderood.linksmith.nl/a", "https://coderood.linksmith.nl/doc.pdf"]
    # to_date is inclusive of the whole day
    day = await _urls(client, from_date="20210121", to_date="20210121")
    assert [r.original_url for r in day] == ["https://coderood.linksmith.nl/a"]


@pytest.mark.asyncio
async def test_query_prefix_exact_and_limit(client):
    prefix = build_key_matcher("coderood.linksmith.nl", "prefix", "https://coderood.linksmith.nl/")
    assert len(await _urls(client, matcher=prefix)) == 4  # no subdomain, no sibling
    exact = build_key_matcher("coderood.linksmith.nl", "exact", "https://coderood.linksmith.nl/a")
    assert [r.original_url for r in await _urls(client, matcher=exact)] == ["https://coderood.linksmith.nl/a"]
    assert len(await _urls(client, limit=2)) == 2


@pytest.mark.asyncio
async def test_record_shape_matches_the_index_api_path(client):
    rec = next(r for r in await _urls(client) if r.original_url == "https://coderood.linksmith.nl/")
    from_index = CommonCrawlDirectService._record_from_index_line(json.dumps({
        "urlkey": "nl,linksmith,coderood)/", "timestamp": "20210120120000", "url": "https://coderood.linksmith.nl/",
        "mime": "text/html", "status": "200", "digest": "HOME", "length": "222", "offset": "111",
        "filename": f"crawl-data/{CRAWL}/segments/x/warc/f-20210120120000.warc.gz",
    }))
    assert rec.__dict__ == from_index.__dict__
    assert rec.is_common_crawl and rec.warc_offset == 111 and rec.warc_length == 222 and rec.digest == "HOME"


@pytest.mark.asyncio
async def test_unrelated_row_groups_are_never_downloaded(client, crawl_files):
    await client.footer_map(CRAWL)
    client.cdn.calls.clear()
    await _urls(client)
    # row group 0 of file 0 (nl,aaa) and row group 1 of file 1 (com,other) are pruned by the map:
    # per used file = 1 footer; per candidate row group = 3 filter chunks (+ merged record chunks if hits)
    footers = [c for c in client.cdn.calls if c[1] and c[1].startswith("bytes=-")]
    assert len(footers) == 2
    pq_file = pq.ParquetFile(crawl_files / f"{DIR}/part-00000.gz.parquet")
    rg0 = pq_file.metadata.row_group(0)
    rg0_start = min(o for o in (rg0.column(0).dictionary_page_offset, rg0.column(0).data_page_offset) if o)
    rg0_end = rg0_start + sum(rg0.column(i).total_compressed_size for i in range(rg0.num_columns))
    for path, rng in client.cdn.calls:
        m = re.fullmatch(r"bytes=(\d+)-(\d+)", rng or "")
        if m and path.endswith("part-00000.gz.parquet"):
            assert not (int(m.group(1)) < rg0_end and int(m.group(2)) >= rg0_start)


@pytest.mark.asyncio
async def test_no_match_reads_no_record_columns(client):
    other = build_key_matcher("nothere.example.nl", "domain", None)
    # key range overlaps no row group at all -> only the footer map is touched
    assert await _urls(client, matcher=other) == []
    assert all(rng is None or rng.startswith("bytes=-") or "gz.parquet" not in p for p, rng in client.cdn.calls)


@pytest.mark.asyncio
async def test_unprefetched_read_is_an_error_not_a_hidden_request():
    sparse = cci._SparseFile(100)
    sparse.add(0, b"x" * 10)
    sparse.seek(50)
    with pytest.raises(ColumnarIndexError):
        sparse.readinto(bytearray(5))


# --------------------------------------------------------------------------
# HTTP layer
# --------------------------------------------------------------------------

class _Resp:
    def __init__(self, status, body=b"", headers=None):
        self.status, self._body, self.headers = status, body, headers or {}

    async def read(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, responses):
        self.responses, self.calls, self.headers = list(responses), [], []

    def get(self, url, headers=None, **kw):
        self.calls.append((url, headers))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.mark.asyncio
async def test_503_slow_down_is_retried_with_backoff_then_succeeds():
    session = _Session([_Resp(503, headers={"Retry-After": "0"}), aiohttp.ClientConnectionError("reset"),
                        _Resp(206, b"abc", {"Content-Range": "bytes 0-2/99"})])
    fetcher = RangeFetcher(session, "https://cdn/", min_interval=0, max_retries=4, backoff_base=0.01)
    body, total = await fetcher.get("x/y", "bytes=0-2")
    assert (body, total, len(session.calls)) == (b"abc", 99, 3)
    assert session.calls[0][1]["Range"] == "bytes=0-2" and session.calls[0][0] == "https://cdn/x/y"


@pytest.mark.asyncio
async def test_persistent_503_gives_up_and_404_is_immediate():
    fetcher = RangeFetcher(_Session([_Resp(503)] * 3), "https://cdn", 0, 3, 0.01)
    with pytest.raises(ColumnarIndexError):
        await fetcher.get("x")
    session = _Session([_Resp(404)])
    with pytest.raises(ColumnarIndexError):
        await RangeFetcher(session, "https://cdn", 0, 3, 0.01).get("x")
    assert len(session.calls) == 1


# --------------------------------------------------------------------------
# Backend selection and fallback in CommonCrawlDirectService
# --------------------------------------------------------------------------

def _collinfo():
    return [{"id": f"CC-MAIN-2021-{n:02d}", "cdx-api": f"https://index.commoncrawl.org/CC-MAIN-2021-{n:02d}-index",
             "from": f"2021-{n:02d}-01T00:00:00", "to": f"2021-{n:02d}-20T00:00:00"} for n in (10, 7, 4, 1)]


def _rec(url, ts):
    return CommonCrawlDirectService._record_from_index_line(json.dumps({
        "timestamp": ts, "url": url, "mime": "text/html", "status": "200", "digest": "D", "length": "5",
        "offset": "1", "filename": "f.warc.gz"}))


@pytest.fixture
def svc(tmp_path, monkeypatch):
    CommonCrawlDirectService._collinfo_cache = _collinfo()
    monkeypatch.setattr(settings, "CC_INDEX_PARALLELISM", 1)
    service = CommonCrawlDirectService(cache_dir=str(tmp_path))
    service.index_calls, service.columnar_calls = [], []

    class FakeColumnar:
        async def query_crawl(_self, crawl_id, matcher, from_date, to_date, include_attachments, limit):
            service.columnar_calls.append(crawl_id)
            return [_rec(f"https://a.nl/{crawl_id}-col", "20210110000000")]

    service._columnar_client = FakeColumnar()
    yield service
    CommonCrawlDirectService._collinfo_cache = None


def _fake_index(service, failing=()):
    async def fake(cdx_api, *args, **kwargs):
        crawl = cdx_api.split("/")[-1].removesuffix("-index")
        service.index_calls.append(crawl)
        if crawl in failing:
            raise DirectCommonCrawlException("blocked")
        return [_rec(f"https://a.nl/{crawl}-idx", "20210110000000")]
    service._query_index_api = fake


@pytest.mark.asyncio
async def test_default_backend_is_auto_and_a_healthy_index_never_touches_columnar(svc, monkeypatch):
    assert settings.CC_DISCOVERY_BACKEND == "auto"
    _fake_index(svc)
    recs, stats = await svc.fetch_cdx_records_simple("a.nl", "20210101", "20211231")
    assert len(recs) == 4 and svc.columnar_calls == [] and stats["columnar_crawls"] == 0


@pytest.mark.asyncio
async def test_index_api_backend_does_not_fall_back(svc, monkeypatch):
    monkeypatch.setattr(settings, "CC_DISCOVERY_BACKEND", "index_api")
    _fake_index(svc, failing={"CC-MAIN-2021-07"})
    recs, stats = await svc.fetch_cdx_records_simple("a.nl", "20210101", "20211231")
    assert len(recs) == 3 and stats["failed_collections"] == 1 and svc.columnar_calls == []


@pytest.mark.asyncio
async def test_columnar_backend_skips_the_index_server(svc, monkeypatch):
    monkeypatch.setattr(settings, "CC_DISCOVERY_BACKEND", "columnar")
    _fake_index(svc)
    recs, stats = await svc.fetch_cdx_records_simple("a.nl", "20210101", "20211231")
    assert svc.index_calls == [] and len(svc.columnar_calls) == 4 and stats["columnar_crawls"] == 4
    assert all(r.is_common_crawl for r in recs)


@pytest.mark.asyncio
async def test_auto_falls_back_per_crawl_then_stops_asking_a_blocked_index(svc, monkeypatch):
    monkeypatch.setattr(settings, "CC_DISCOVERY_BACKEND", "auto")
    monkeypatch.setattr(settings, "CC_AUTO_INDEX_FAILURE_THRESHOLD", 2)
    _fake_index(svc, failing={"CC-MAIN-2021-10", "CC-MAIN-2021-07", "CC-MAIN-2021-04", "CC-MAIN-2021-01"})
    recs, stats = await svc.fetch_cdx_records_simple("a.nl", "20210101", "20211231")
    assert len(recs) == 4 and stats["failed_collections"] == 0
    assert svc.index_calls == ["CC-MAIN-2021-10", "CC-MAIN-2021-07"]  # then the index is skipped
    assert len(svc.columnar_calls) == 4


@pytest.mark.asyncio
async def test_auto_recovers_the_failure_count_after_an_index_success(svc, monkeypatch):
    monkeypatch.setattr(settings, "CC_DISCOVERY_BACKEND", "auto")
    monkeypatch.setattr(settings, "CC_AUTO_INDEX_FAILURE_THRESHOLD", 2)
    _fake_index(svc, failing={"CC-MAIN-2021-10", "CC-MAIN-2021-04"})
    await svc.fetch_cdx_records_simple("a.nl", "20210101", "20211231")
    assert len(svc.index_calls) == 4 and len(svc.columnar_calls) == 2


@pytest.mark.asyncio
async def test_all_crawls_failing_in_every_backend_raises(svc, monkeypatch):
    monkeypatch.setattr(settings, "CC_DISCOVERY_BACKEND", "auto")

    async def boom(*a, **k):
        raise DirectCommonCrawlException("down")

    svc._query_index_api = boom
    svc._columnar_client.query_crawl = boom
    with pytest.raises(DirectCommonCrawlException):
        await svc.fetch_cdx_records_simple("a.nl", "20210101", "20211231")


@pytest.mark.asyncio
async def test_unknown_backend_is_rejected(svc, monkeypatch):
    monkeypatch.setattr(settings, "CC_DISCOVERY_BACKEND", "duckdb")
    with pytest.raises(DirectCommonCrawlException):
        await svc.fetch_cdx_records_simple("a.nl", "20210101", "20211231")


# --------------------------------------------------------------------------
# Crawl selection when the index server is unreachable
# --------------------------------------------------------------------------

LISTING = ('<a href="./CC-MAIN-2021-04/index.html">CC-MAIN-2021-04</a> <a href="./CC-MAIN-2020-50/index.html">x</a>'
           '<a href="./CC-MAIN-2021-04/index.html">dup</a> <a href="./CC-MAIN-2013-20/index.html">old</a>')


class _ListingSession:
    def __init__(self, fail_collinfo):
        self.fail_collinfo = fail_collinfo

    def get(self, url, **kw):
        if url.endswith("collinfo.json") and self.fail_collinfo:
            raise aiohttp.ClientConnectionError("refused")
        return _TextResp(200, LISTING)


class _TextResp(_Resp):
    def raise_for_status(self):
        pass

    async def text(self):
        return self._body

    async def json(self, content_type=None):
        return [{"id": "from-index-server"}]


@pytest.mark.asyncio
async def test_crawl_list_falls_back_to_data_host_unless_backend_is_index_api(svc, monkeypatch):
    CommonCrawlDirectService._collinfo_cache = None
    svc.session = _ListingSession(fail_collinfo=True)
    monkeypatch.setattr(settings, "CC_DISCOVERY_BACKEND", "columnar")
    info = await svc._get_collinfo()
    assert [c["id"] for c in info] == ["CC-MAIN-2021-04", "CC-MAIN-2020-50", "CC-MAIN-2013-20"]
    window = svc._collection_window(info[0])
    assert window[0] <= "20210115" and window[1] >= "20210128"  # CC-MAIN-2021-04 really ran Jan 15-28
    assert CommonCrawlDirectService._collinfo_cache is None  # fallback list is not memoised

    monkeypatch.setattr(settings, "CC_DISCOVERY_BACKEND", "index_api")
    with pytest.raises(aiohttp.ClientConnectionError):
        await svc._get_collinfo()


@pytest.mark.asyncio
async def test_crawl_list_prefers_the_index_server_when_it_answers(svc, monkeypatch):
    CommonCrawlDirectService._collinfo_cache = None
    svc.session = _ListingSession(fail_collinfo=False)
    monkeypatch.setattr(settings, "CC_DISCOVERY_BACKEND", "auto")
    assert await svc._get_collinfo() == [{"id": "from-index-server"}]
