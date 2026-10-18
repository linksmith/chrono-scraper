from evals.storage import BlobStore, Catalog, SnapshotRef


def _ref(**overrides) -> SnapshotRef:
    base = dict(
        site_key="test-site",
        url="http://example.com/page",
        source="wayback",
        timestamp="20050301000000",
        cdx_digest="ABC123",
        status_code=200,
        mime="text/html",
        fetch_url="http://web.archive.org/web/20050301000000id_/http://example.com/page",
    )
    base.update(overrides)
    return SnapshotRef(**base)


def test_blobstore_roundtrip_and_dedup(tmp_path):
    store = BlobStore(tmp_path / "objects")
    sha1, new1 = store.put(b"<html>hello</html>")
    sha2, new2 = store.put(b"<html>hello</html>")
    assert sha1 == sha2
    assert new1 is True and new2 is False
    assert store.get(sha1) == b"<html>hello</html>"
    assert store.stats()["objects"] == 1


def test_blobstore_text(tmp_path):
    store = BlobStore(tmp_path / "objects")
    sha, _ = store.put_text("héllo wörld")
    assert store.get_text(sha) == "héllo wörld"


def test_blobstore_bytes_are_deterministic(tmp_path):
    # Same content -> byte-identical blob (gzip mtime pinned to 0), so runs are
    # reproducible and content-addressing is stable across machines/time.
    data = b"<html><body>reproducible</body></html>"
    a = BlobStore(tmp_path / "a")
    b = BlobStore(tmp_path / "b")
    sha_a, _ = a.put(data)
    sha_b, _ = b.put(data)
    assert sha_a == sha_b
    raw_a = (tmp_path / "a" / sha_a[:2] / sha_a[2:4] / f"{sha_a}.gz").read_bytes()
    raw_b = (tmp_path / "b" / sha_b[:2] / sha_b[2:4] / f"{sha_b}.gz").read_bytes()
    assert raw_a == raw_b


def test_blobstore_no_stray_tmp_files(tmp_path):
    store = BlobStore(tmp_path / "objects")
    store.put(b"data")
    assert not list((tmp_path / "objects").rglob("*.tmp"))


def test_catalog_sets_busy_timeout(tmp_path):
    with Catalog(tmp_path / "cat.db") as catalog:
        assert catalog.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000


def test_catalog_snapshot_upsert_idempotent(tmp_path):
    with Catalog(tmp_path / "cat.db") as catalog:
        first = catalog.upsert_snapshot(_ref())
        second = catalog.upsert_snapshot(_ref(cdx_digest="XYZ789"))
        assert first == second
        row = catalog.snapshot_by_id(first)
        assert row["cdx_digest"] == "XYZ789"
        assert catalog.summary()["snapshots"] == 1


def test_catalog_fetch_lifecycle(tmp_path):
    with Catalog(tmp_path / "cat.db") as catalog:
        snapshot_id = catalog.upsert_snapshot(_ref())
        catalog.mark_fetch_error(snapshot_id, "timeout")
        assert catalog.snapshot_by_id(snapshot_id)["fetch_error"] == "timeout"
        catalog.mark_fetched(snapshot_id, "a" * 64, 1234, "2026-07-05T00:00:00+00:00")
        row = catalog.snapshot_by_id(snapshot_id)
        assert row["raw_sha256"] == "a" * 64
        assert row["fetch_error"] is None
        assert catalog.snapshots(fetched_only=True)[0]["id"] == snapshot_id


def test_catalog_extraction_upsert(tmp_path):
    with Catalog(tmp_path / "cat.db") as catalog:
        snapshot_id = catalog.upsert_snapshot(_ref())
        eid1 = catalog.upsert_extraction(
            snapshot_id, "trafilatura", title="T", body_sha256="b" * 64,
            body_key="k" * 64, simhash="00ff00ff00ff00ff", n_tokens=100,
        )
        eid2 = catalog.upsert_extraction(snapshot_id, "trafilatura", title="T2")
        assert eid1 == eid2
        rows = catalog.extractions("trafilatura")
        assert len(rows) == 1
        assert rows[0]["title"] == "T2"


def test_catalog_extraction_rejects_unknown_fields(tmp_path):
    import pytest

    with Catalog(tmp_path / "cat.db") as catalog:
        snapshot_id = catalog.upsert_snapshot(_ref())
        with pytest.raises(ValueError):
            catalog.upsert_extraction(snapshot_id, "trafilatura", bogus_field=1)


def test_catalog_features_and_labels(tmp_path):
    with Catalog(tmp_path / "cat.db") as catalog:
        snapshot_id = catalog.upsert_snapshot(_ref())
        catalog.set_features(snapshot_id, {"link_density": 0.5, "fingerprint": [0.1] * 4})
        assert catalog.get_features(snapshot_id)["link_density"] == 0.5
        catalog.set_label(snapshot_id, "page_type", "article", "manifest")
        catalog.set_label(snapshot_id, "page_type", "list", "classifier", {"confidence": 0.6})
        catalog.set_label(snapshot_id, "page_type", "article", "classifier")  # overwrite
        assert catalog.labels("page_type", "manifest") == {snapshot_id: "article"}
        assert catalog.labels("page_type", "classifier") == {snapshot_id: "article"}


def test_catalog_clusters_replace(tmp_path):
    with Catalog(tmp_path / "cat.db") as catalog:
        snapshot_id = catalog.upsert_snapshot(_ref())
        eid = catalog.upsert_extraction(snapshot_id, "trafilatura", n_tokens=10)
        catalog.replace_clusters("trafilatura", {eid: "c1"})
        assert catalog.clusters("trafilatura") == {eid: "c1"}
        catalog.replace_clusters("trafilatura", {eid: "c2"})
        assert catalog.clusters("trafilatura") == {eid: "c2"}
