"""Two-tier duplicate detection over extracted body text.

Tier 1 — exact: sha256 of the normalized token stream (``textnorm.body_key``).
Catches snapshots whose body is byte-different (whitespace, entities, case)
but textually identical. This is deliberately computed on the *extracted body*
rather than raw HTML: the Wayback Machine stores the same article dozens of
times with only header/footer/boilerplate churn, and the CDX ``digest`` field
(SHA-1 of the raw payload) cannot see through that.

Tier 2 — near: 64-bit SimHash over word shingles, near-duplicate when the
Hamming distance is <= k. Parameters follow Manku, Jain & Das Sarma (WWW 2007,
"Detecting Near-Duplicates for Web Crawling"): 64-bit fingerprints, k=3.
Candidate pairs are found with bit-block banding: with k+1 equal bit blocks,
any pair within Hamming distance k must agree exactly on at least one block
(pigeonhole), so recall of the candidate stage is 100% while lookups stay
O(n) dict probes instead of O(n^2) comparisons.

SimHash is unreliable on very short texts (too few shingles), so documents
under ``min_tokens`` participate in exact matching only.

Pure stdlib — no external dependencies.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass

from evals.textnorm import body_key, shingle_counts

logger = logging.getLogger(__name__)

SIMHASH_BITS = 64


def _shingle_hash64(shingle: str) -> int:
    return int.from_bytes(
        hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(), "big"
    )


def simhash64(text: str, shingle_size: int = 5) -> int:
    """64-bit SimHash of a text over word ``shingle_size``-grams.

    Each shingle votes its hash bits weighted by its occurrence count; the
    fingerprint keeps the sign of each bit-position sum.
    """
    counts = shingle_counts(text, shingle_size)
    if not counts:
        return 0
    weights = [0] * SIMHASH_BITS
    for shingle, count in counts.items():
        h = _shingle_hash64(shingle)
        for bit in range(SIMHASH_BITS):
            if (h >> bit) & 1:
                weights[bit] += count
            else:
                weights[bit] -= count
    fingerprint = 0
    for bit in range(SIMHASH_BITS):
        if weights[bit] > 0:
            fingerprint |= 1 << bit
    return fingerprint


def hamming64(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


@dataclass(frozen=True)
class BodyFingerprint:
    """Everything dedup needs to know about one extracted body."""

    item_id: str
    exact_key: str
    simhash: int
    n_tokens: int


def fingerprint_body(item_id: str, text: str, shingle_size: int = 5) -> BodyFingerprint:
    from evals.textnorm import tokenize

    tokens = tokenize(text)
    return BodyFingerprint(
        item_id=item_id,
        exact_key=body_key(text),
        simhash=simhash64(text, shingle_size),
        n_tokens=len(tokens),
    )


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, x: str) -> None:
        self._parent.setdefault(x, x)

    def find(self, x: str) -> str:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression.
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Deterministic winner so cluster ids are stable across runs.
            keep, drop = sorted((ra, rb))
            self._parent[drop] = keep

    def components(self) -> dict[str, str]:
        return {x: self.find(x) for x in self._parent}


class NearDupClusterer:
    """Cluster body fingerprints into duplicate groups.

    Usage::

        clusterer = NearDupClusterer(hamming_threshold=3, min_tokens=50)
        for row in extractions:
            clusterer.add(fingerprint)
        mapping = clusterer.clusters()   # item_id -> cluster_id
    """

    def __init__(
        self, hamming_threshold: int = 3, min_tokens: int = 50, min_exact_tokens: int = 5
    ) -> None:
        if not 0 <= hamming_threshold < SIMHASH_BITS:
            raise ValueError(f"hamming_threshold must be in [0, {SIMHASH_BITS})")
        self.hamming_threshold = hamming_threshold
        self.min_tokens = min_tokens
        # Bodies below this are non-dedupable singletons. Without it, every
        # empty/failed extraction shares body_key = sha256("") and the exact
        # tier unions them all into one giant bogus "duplicate" cluster —
        # inflating redundancy and merging genuinely different (failed) pages.
        self.min_exact_tokens = min_exact_tokens
        self._n_bands = hamming_threshold + 1
        self._band_width = SIMHASH_BITS // self._n_bands
        self._items: dict[str, BodyFingerprint] = {}
        self._uf = _UnionFind()
        self._by_exact: dict[str, str] = {}
        # (band_index, band_bits) -> item ids sharing that block value.
        self._bands: dict[tuple[int, int], list[str]] = defaultdict(list)
        self.near_dup_pairs = 0
        self.exact_dup_pairs = 0

    def _band_keys(self, fingerprint: int) -> list[tuple[int, int]]:
        keys = []
        for i in range(self._n_bands):
            lo = i * self._band_width
            # Last band absorbs any leftover bits (64 % n_bands != 0).
            hi = SIMHASH_BITS if i == self._n_bands - 1 else lo + self._band_width
            mask = (1 << (hi - lo)) - 1
            keys.append((i, (fingerprint >> lo) & mask))
        return keys

    def add(self, fp: BodyFingerprint) -> None:
        if fp.item_id in self._items:
            raise ValueError(f"duplicate item_id added to clusterer: {fp.item_id}")
        self._items[fp.item_id] = fp
        self._uf.add(fp.item_id)

        # Bodies too short to be meaningful (empty/failed extractions, stubs)
        # stay singletons — never merged by either tier.
        if fp.n_tokens < self.min_exact_tokens:
            return

        # Tier 1: exact normalized-body match.
        first = self._by_exact.setdefault(fp.exact_key, fp.item_id)
        if first != fp.item_id:
            self._uf.union(first, fp.item_id)
            self.exact_dup_pairs += 1

        # Tier 2: SimHash banding, only for bodies long enough to trust.
        if fp.n_tokens < self.min_tokens:
            return
        seen: set[str] = set()
        for key in self._band_keys(fp.simhash):
            for other_id in self._bands[key]:
                if other_id in seen:
                    continue
                seen.add(other_id)
                other = self._items[other_id]
                if hamming64(fp.simhash, other.simhash) <= self.hamming_threshold:
                    self._uf.union(other_id, fp.item_id)
                    self.near_dup_pairs += 1
            self._bands[key].append(fp.item_id)

    def clusters(self) -> dict[str, str]:
        """Map every item_id to its cluster id (the lexicographically smallest
        member, so ids are stable and human-checkable)."""
        return self._uf.components()

    def groups(self, min_size: int = 1) -> list[list[str]]:
        by_root: dict[str, list[str]] = defaultdict(list)
        for item, root in self.clusters().items():
            by_root[root].append(item)
        out = [sorted(members) for members in by_root.values() if len(members) >= min_size]
        out.sort(key=lambda g: (-len(g), g[0]))
        return out

    def stats(self) -> dict[str, int]:
        groups = self.groups()
        dup_groups = [g for g in groups if len(g) > 1]
        return {
            "items": len(self._items),
            "clusters": len(groups),
            "dup_clusters": len(dup_groups),
            "redundant_items": sum(len(g) - 1 for g in dup_groups),
            "exact_dup_pairs": self.exact_dup_pairs,
            "near_dup_pairs": self.near_dup_pairs,
        }
