from evals.score import bootstrap_ci, dedup_yield, score_dedup, score_filtering
from evals.config import load_config
from evals.storage import Catalog, SnapshotRef


def test_bootstrap_ci_suppressed_below_min_n():
    # Small samples must NOT emit a CI dressed as statistics.
    result = bootstrap_ci([0.9, 0.9, 0.9, 0.9])
    assert result["mean"] == 0.9
    assert result["ci_suppressed"] is True
    assert result["ci_low"] is None and result["ci_high"] is None
    assert result["n"] == 4


def test_bootstrap_ci_single_value_suppressed():
    result = bootstrap_ci([0.5])
    assert result["mean"] == 0.5 and result["n"] == 1 and result["ci_suppressed"] is True


def test_bootstrap_ci_empty():
    r = bootstrap_ci([])
    assert r["n"] == 0 and r["ci_suppressed"] is True


def test_bootstrap_ci_computed_at_sufficient_n():
    values = [0.2, 0.4, 0.6, 0.8, 1.0, 0.5, 0.7, 0.9, 0.3, 0.65]  # n=10 >= min
    first = bootstrap_ci(values)
    second = bootstrap_ci(values)
    assert first == second                 # seeded/deterministic
    assert first["ci_suppressed"] is False
    assert first["ci_low"] <= first["mean"] <= first["ci_high"]
    assert first["ci_low"] < first["ci_high"]


def _seed_catalog(tmp_path):
    cfg = load_config(tmp_path)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cat = Catalog(cfg.catalog_path)
    # two eras; era1 has 3 snapshots collapsing to 1 body, era2 has 2 distinct
    plan = [
        ("s1", "early_static", "cA"), ("s2", "early_static", "cA"), ("s3", "early_static", "cA"),
        ("s4", "html5_semantic", "cB"), ("s5", "html5_semantic", "cC"),
    ]
    cluster_map = {}
    for i, (name, era, cluster) in enumerate(plan):
        sid = cat.upsert_snapshot(SnapshotRef(
            site_key=name, url=f"http://x/{name}", source="wayback", timestamp=f"2020010100000{i}"))
        cat.mark_fetched(sid, "h" * 64, 100, "2026-07-05T00:00:00+00:00")
        cat.set_label(sid, "era", era, "classifier")
        eid = cat.upsert_extraction(sid, "trafilatura", body_sha256="b" * 64, n_tokens=100)
        cluster_map[eid] = cluster
    cat.replace_clusters("trafilatura", cluster_map)
    return cfg, cat


def test_dedup_yield_by_era(tmp_path):
    cfg, cat = _seed_catalog(tmp_path)
    result = dedup_yield(cat, "trafilatura")
    assert result["overall"] == {
        "snapshots": 5, "unique_bodies": 3, "redundant": 2, "redundancy_pct": 40.0,
    }
    assert result["by_era"]["early_static"]["unique_bodies"] == 1
    assert result["by_era"]["early_static"]["redundant"] == 2
    assert result["by_era"]["html5_semantic"]["redundant"] == 0
    cat.close()


def test_dedup_yield_none_without_clusters(tmp_path):
    cfg = load_config(tmp_path)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cat = Catalog(cfg.catalog_path)
    assert dedup_yield(cat, "trafilatura") is None
    cat.close()


def test_score_dedup_truth_is_same_canonical_page(tmp_path):
    # Two captures of one page (URL variants) are true dups; a different page
    # in the same seed group is NOT — even if clustered wrongly.
    cfg = load_config(tmp_path)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cat = Catalog(cfg.catalog_path)
    plan = [
        # (url, cluster, body_key) — page A has 2 URL-variant captures, same body
        ("http://w3.org/TR/spec", "c1", "aaa"),
        ("http://w3.org:80/TR/spec#top", "c1", "aaa"),  # same canonical page + body
        ("http://w3.org/TR/other", "c2", "ccc"),         # different page + body
    ]
    cmap = {}
    for i, (url, cluster, bkey) in enumerate(plan):
        sid = cat.upsert_snapshot(SnapshotRef(
            site_key="w3", url=url, source="wayback", timestamp=f"2020010100000{i}"))
        cat.mark_fetched(sid, "h" * 64, 100, "2026-07-05T00:00:00+00:00")
        cat.set_label(sid, "dup_group", "g", "manifest")
        eid = cat.upsert_extraction(
            sid, "trafilatura", body_sha256="b" * 64, body_key=bkey, n_tokens=100)
        cmap[eid] = cluster
    cat.replace_clusters("trafilatura", cmap)
    result = score_dedup(cat, cfg, "trafilatura")
    assert result["n_pages"] == 2                    # canonical collapse: 2 distinct pages
    assert result["pairwise"]["tp"] == 1             # the 2 variants correctly merged
    assert result["pairwise"]["fp"] == 0             # different page NOT merged with them
    assert result["pairwise"]["f1"] == 1.0
    inv = result["exact_dup_invariant"]
    assert inv["identical_body_pairs"] == 1          # the two 'aaa' bodies
    assert inv["rate"] == 1.0                        # and they co-clustered
    cat.close()


def test_score_filtering_by_era_shape(tmp_path):
    cfg = load_config(tmp_path)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cat = Catalog(cfg.catalog_path)
    sid = cat.upsert_snapshot(SnapshotRef(
        site_key="s", url="http://x/a", source="wayback", timestamp="20200101000000"))
    cat.set_label(sid, "page_type", "article", "manifest")
    cat.set_label(sid, "page_type", "article", "classifier")
    cat.set_label(sid, "era", "table_layout", "classifier")
    result = score_filtering(cat, cfg)
    assert result["classifier"]["content_detection"]["tp"] == 1
    assert result["classifier"]["content_detection_by_era"]["table_layout"]["tp"] == 1
    cat.close()
