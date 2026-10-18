"""Corpus manifest loading and validation.

The manifest (``corpus_manifest.yaml``) is the single curated definition of
the eval corpus: which sites, which eras, what page type each entry is
expected to be, and how snapshots should be sampled. Everything downstream
(collection, expected-label seeding, dedup ground truth) derives from it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from evals.classify_era import ERAS
from evals.classify_page_type import PAGE_TYPES
from evals.config import MANIFEST_PATH

VALID_CATEGORIES = {
    "news", "blog", "forum", "social", "reference", "gov", "personal",
    "magazine", "qa", "campaign", "promo", "directory",
}
VALID_SOURCES = {"wayback", "commoncrawl", "both"}
# 'mixed' = entry deliberately spans several page types (e.g. a 1996 site
# prefix); such snapshots get no expected label and rely on human labeling.
VALID_EXPECTED = set(PAGE_TYPES) | {"mixed"}


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class SiteEntry:
    key: str
    category: str
    source: str
    expected_page_type: str
    from_year: int
    to_year: int
    urls: tuple[str, ...] = ()
    prefix: str | None = None
    url_include: str | None = None
    snapshots_per_url: int = 3
    max_urls_per_prefix: int = 5
    era_hint: str | None = None
    dedup_group: str | None = None
    notes: str = ""

    def url_include_re(self) -> re.Pattern | None:
        return re.compile(self.url_include) if self.url_include else None

    @property
    def sources(self) -> list[str]:
        return ["wayback", "commoncrawl"] if self.source == "both" else [self.source]


_REQUIRED = ("key", "category", "source", "expected_page_type", "from_year", "to_year")


def _validate(raw: dict, index: int) -> SiteEntry:
    where = f"manifest entry #{index} ({raw.get('key', '?')})"
    for name in _REQUIRED:
        if name not in raw:
            raise ManifestError(f"{where}: missing required field '{name}'")
    unknown = set(raw) - set(SiteEntry.__dataclass_fields__)
    if unknown:
        raise ManifestError(f"{where}: unknown fields {sorted(unknown)}")
    if raw["category"] not in VALID_CATEGORIES:
        raise ManifestError(f"{where}: category '{raw['category']}' not in {sorted(VALID_CATEGORIES)}")
    if raw["source"] not in VALID_SOURCES:
        raise ManifestError(f"{where}: source '{raw['source']}' not in {sorted(VALID_SOURCES)}")
    if raw["expected_page_type"] not in VALID_EXPECTED:
        raise ManifestError(
            f"{where}: expected_page_type '{raw['expected_page_type']}' not in {sorted(VALID_EXPECTED)}"
        )
    era_hint = raw.get("era_hint")
    if era_hint and era_hint not in ERAS:
        raise ManifestError(f"{where}: era_hint '{era_hint}' not in {ERAS}")
    urls = tuple(raw.get("urls") or ())
    prefix = raw.get("prefix")
    if bool(urls) == bool(prefix):
        raise ManifestError(f"{where}: exactly one of 'urls' or 'prefix' must be set")
    from_year, to_year = int(raw["from_year"]), int(raw["to_year"])
    if not (1993 <= from_year <= to_year <= 2100):
        raise ManifestError(f"{where}: implausible year range {from_year}..{to_year}")
    if raw.get("url_include"):
        try:
            re.compile(raw["url_include"])
        except re.error as exc:
            raise ManifestError(f"{where}: url_include is not a valid regex: {exc}") from exc
    return SiteEntry(
        key=raw["key"],
        category=raw["category"],
        source=raw["source"],
        expected_page_type=raw["expected_page_type"],
        from_year=from_year,
        to_year=to_year,
        urls=urls,
        prefix=prefix,
        url_include=raw.get("url_include"),
        snapshots_per_url=int(raw.get("snapshots_per_url", 3)),
        max_urls_per_prefix=int(raw.get("max_urls_per_prefix", 5)),
        era_hint=era_hint,
        dedup_group=raw.get("dedup_group"),
        notes=raw.get("notes", ""),
    )


def load_manifest(path: Path | str = MANIFEST_PATH) -> list[SiteEntry]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or "sites" not in data:
        raise ManifestError("manifest must be a mapping with a top-level 'sites' list")
    entries = [_validate(raw, i) for i, raw in enumerate(data["sites"])]
    keys = [e.key for e in entries]
    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        raise ManifestError(f"duplicate site keys: {sorted(dupes)}")
    return entries
