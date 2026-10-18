import pytest

yaml = pytest.importorskip("yaml")

from evals.config import MANIFEST_PATH  # noqa: E402
from evals.manifest import ManifestError, _validate, load_manifest  # noqa: E402


def test_real_manifest_loads_and_validates():
    entries = load_manifest(MANIFEST_PATH)
    assert len(entries) >= 30, "corpus should stay at a few dozen entries"


def test_real_manifest_covers_all_eras():
    entries = load_manifest(MANIFEST_PATH)
    hints = {e.era_hint for e in entries if e.era_hint}
    assert {"early_static", "table_layout", "css_layout", "html5_semantic", "spa_hydrated"} <= hints


def test_real_manifest_has_negatives_and_dedup_groups():
    entries = load_manifest(MANIFEST_PATH)
    assert sum(1 for e in entries if e.expected_page_type == "list") >= 4
    assert sum(1 for e in entries if e.dedup_group) >= 3
    assert len({e.category for e in entries}) >= 8


def test_real_manifest_commoncrawl_only_after_2013():
    for entry in load_manifest(MANIFEST_PATH):
        if "commoncrawl" in entry.sources:
            assert entry.to_year >= 2013, f"{entry.key}: CC has no useful pre-2013 coverage"


_BASE = {
    "key": "x", "category": "news", "source": "wayback",
    "expected_page_type": "article", "from_year": 2000, "to_year": 2001,
    "urls": ["http://example.com/a"],
}


def test_validate_rejects_missing_field():
    raw = dict(_BASE)
    del raw["category"]
    with pytest.raises(ManifestError):
        _validate(raw, 0)


def test_validate_rejects_urls_and_prefix_together():
    raw = dict(_BASE, prefix="example.com/")
    with pytest.raises(ManifestError):
        _validate(raw, 0)


def test_validate_rejects_bad_regex():
    raw = dict(_BASE, url_include="([unclosed")
    with pytest.raises(ManifestError):
        _validate(raw, 0)


def test_validate_rejects_unknown_field():
    raw = dict(_BASE, surprise=True)
    with pytest.raises(ManifestError):
        _validate(raw, 0)
