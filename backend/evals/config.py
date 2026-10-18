"""Central configuration for the eval harness.

Every tunable threshold lives here so calibration runs only ever touch one
file. Defaults are research-backed:

* Dedup: 64-bit SimHash, Hamming k=3 (Manku et al., WWW 2007), word 5-gram
  shingles (FineWeb convention), 50-token minimum for reliable fingerprints.
* Scoring: word 4-gram shingles for the order-sensitive metric (matches the
  scrapinghub/article-extraction-benchmark).
* Page-type: link-density style thresholds in the spirit of Kohlschütter et
  al. (WSDM 2010) shallow text features.

No pydantic on purpose — importing ``app.core.config`` requires the full app
environment, and the eval core must also run outside the backend container.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = PACKAGE_DIR / "corpus_data"
GOLD_DIR = PACKAGE_DIR / "gold"
MANIFEST_PATH = PACKAGE_DIR / "corpus_manifest.yaml"


@dataclass(frozen=True)
class DedupConfig:
    shingle_size: int = 5
    hamming_threshold: int = 3
    min_tokens: int = 50
    # Bodies below this token count are non-dedupable singletons — stops
    # empty/failed extractions (all sha256("")) collapsing into one cluster.
    min_exact_tokens: int = 5


@dataclass(frozen=True)
class ScoringConfig:
    body_shingle_n: int = 4
    date_tolerance_days: int = 1
    # Aggregate report flags a (era, extractor) cell as failing under this.
    body_f1_target: float = 0.85


@dataclass(frozen=True)
class PageTypeConfig:
    # Link density above this is a strong listing signal; below the article
    # max it is a strong content signal (Kohlschütter-style shallow features).
    link_density_list: float = 0.50
    link_density_article_max: float = 0.35
    # A single text block at least this long usually means a canonical body.
    min_article_block_chars: int = 800
    # N same-classed block elements => repeated template rows (listing).
    repeated_block_threshold: int = 8
    # Many anchors + no substantial block => navigation page.
    listing_anchor_count: int = 40
    listing_max_block_chars: int = 400
    min_pagination_hints: int = 2
    # Discussion/thread pages (forums, HN, comment threads) carry lots of prose
    # in many small blocks rather than one big block. Substantial cumulative
    # text at a link density below the listing range votes article — the guard
    # keeps it from firing on link-dominated real list pages.
    min_prose_chars: int = 1500
    prose_link_density_max: float = 0.5
    # |top score - runner-up| below this margin => low confidence.
    decision_margin: float = 1.0


@dataclass(frozen=True)
class EraConfig:
    spa_script_ratio: float = 0.70
    spa_max_text_chars: int = 800
    table_layout_text_ratio: float = 0.50


@dataclass(frozen=True)
class CollectConfig:
    snapshots_per_site: int = 6
    wayback_delay_seconds: float = 1.5   # ~1 req/2s keeps CDX + fetches polite
    commoncrawl_delay_seconds: float = 1.0
    timeout_seconds: float = 60.0
    max_html_bytes: int = 10 * 1024 * 1024
    cdx_row_limit: int = 500             # rows requested per per-URL snapshot query
    cdx_discovery_limit: int = 2000      # rows requested per prefix discovery query
    max_cc_collections: int = 4          # CC indexes probed per date range
    user_agent: str = "chrono-scraper-evals/0.1 (research tool)"


@dataclass(frozen=True)
class EvalConfig:
    data_dir: Path = DEFAULT_DATA_DIR
    gold_dir: Path = GOLD_DIR
    manifest_path: Path = MANIFEST_PATH
    dedup: DedupConfig = field(default_factory=DedupConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    page_type: PageTypeConfig = field(default_factory=PageTypeConfig)
    era: EraConfig = field(default_factory=EraConfig)
    collect: CollectConfig = field(default_factory=CollectConfig)

    @property
    def catalog_path(self) -> Path:
        return self.data_dir / "catalog.db"

    @property
    def objects_dir(self) -> Path:
        return self.data_dir / "objects"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"


def load_config(
    data_dir: str | os.PathLike | None = None,
    gold_dir: str | os.PathLike | None = None,
) -> EvalConfig:
    """Build config.

    ``EVALS_DATA_DIR`` overrides the corpus location (bulky raw snapshots must
    live outside git). ``EVALS_GOLD_DIR`` overrides the gold directory — the
    default is the checked-in ``evals/gold/``, but smoke/CI runs point it at a
    scratch dir so drafting never pollutes the curated corpus.
    """
    resolved_data = Path(data_dir or os.environ.get("EVALS_DATA_DIR") or DEFAULT_DATA_DIR)
    resolved_gold = Path(gold_dir or os.environ.get("EVALS_GOLD_DIR") or GOLD_DIR)
    return EvalConfig(data_dir=resolved_data, gold_dir=resolved_gold)
