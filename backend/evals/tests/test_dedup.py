from evals.dedup import (
    BodyFingerprint,
    NearDupClusterer,
    fingerprint_body,
    hamming64,
    simhash64,
)
from evals.tests.fixtures import BODY_LONG_A, BODY_LONG_A_EDIT, BODY_LONG_B


def test_simhash_deterministic():
    assert simhash64(BODY_LONG_A) == simhash64(BODY_LONG_A)


def test_simhash_whitespace_case_invariant():
    assert simhash64(BODY_LONG_A) == simhash64("  " + BODY_LONG_A.upper() + "\n\n")


def test_hamming():
    assert hamming64(0b1010, 0b1010) == 0
    assert hamming64(0b1010, 0b0101) == 4


def test_near_duplicate_is_closer_than_different_document():
    a = simhash64(BODY_LONG_A)
    edited = simhash64(BODY_LONG_A_EDIT)
    b = simhash64(BODY_LONG_B)
    assert hamming64(a, edited) < hamming64(a, b)


def test_exact_tier_clusters_formatting_variants():
    clusterer = NearDupClusterer(hamming_threshold=3, min_tokens=50)
    clusterer.add(fingerprint_body("a1", BODY_LONG_A))
    clusterer.add(fingerprint_body("a2", BODY_LONG_A.upper() + "   "))
    clusterer.add(fingerprint_body("b1", BODY_LONG_B))
    mapping = clusterer.clusters()
    assert mapping["a1"] == mapping["a2"]
    assert mapping["a1"] != mapping["b1"]


def test_banding_clusters_within_threshold():
    # Synthetic fingerprints: differ by exactly 2 bits (<= k) and 10 bits (> k).
    base = 0x0123456789ABCDEF
    near = base ^ 0b11                     # 2 differing bits
    far = base ^ ((1 << 10) - 1)           # 10 differing bits
    clusterer = NearDupClusterer(hamming_threshold=3, min_tokens=50)
    for item_id, fp in (("base", base), ("near", near), ("far", far)):
        clusterer.add(
            BodyFingerprint(item_id=item_id, exact_key=item_id, simhash=fp, n_tokens=100)
        )
    mapping = clusterer.clusters()
    assert mapping["base"] == mapping["near"]
    assert mapping["base"] != mapping["far"]


def test_short_documents_skip_simhash_tier():
    # Two short, different texts whose fingerprints could collide must NOT
    # merge via the near tier; only exact matches count under min_tokens.
    clusterer = NearDupClusterer(hamming_threshold=3, min_tokens=50)
    clusterer.add(
        BodyFingerprint(item_id="s1", exact_key="k1", simhash=0xFF, n_tokens=5)
    )
    clusterer.add(
        BodyFingerprint(item_id="s2", exact_key="k2", simhash=0xFE, n_tokens=5)
    )
    mapping = clusterer.clusters()
    assert mapping["s1"] != mapping["s2"]


def test_empty_and_tiny_bodies_stay_singletons():
    # Regression: empty/failed extractions all share body_key=sha256("") and
    # must NOT collapse into one giant false "duplicate" cluster.
    clusterer = NearDupClusterer(hamming_threshold=3, min_tokens=50, min_exact_tokens=5)
    empty_key = "e" * 64
    for i in range(5):
        clusterer.add(
            BodyFingerprint(item_id=f"empty{i}", exact_key=empty_key, simhash=0, n_tokens=0)
        )
    # two-token stubs sharing a key are still below min_exact_tokens
    for i in range(3):
        clusterer.add(
            BodyFingerprint(item_id=f"stub{i}", exact_key="s" * 64, simhash=1, n_tokens=2)
        )
    mapping = clusterer.clusters()
    # every short/empty body is its own cluster
    assert len({mapping[f"empty{i}"] for i in range(5)}) == 5
    assert len({mapping[f"stub{i}"] for i in range(3)}) == 3


def test_real_bodies_above_threshold_still_dedup():
    clusterer = NearDupClusterer(hamming_threshold=3, min_tokens=50, min_exact_tokens=5)
    clusterer.add(fingerprint_body("a1", BODY_LONG_A))
    clusterer.add(fingerprint_body("a2", BODY_LONG_A.upper()))
    assert clusterer.clusters()["a1"] == clusterer.clusters()["a2"]


def test_stats_shape():
    clusterer = NearDupClusterer()
    clusterer.add(fingerprint_body("a1", BODY_LONG_A))
    clusterer.add(fingerprint_body("a2", BODY_LONG_A))
    stats = clusterer.stats()
    assert stats["items"] == 2
    assert stats["clusters"] == 1
    assert stats["redundant_items"] == 1
