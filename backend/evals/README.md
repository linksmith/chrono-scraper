# Extraction-Quality Evaluation Harness

Measures how well Chrono Scraper captures **canonical content pages** (articles,
posts, threads — not lists, archives, or search results) from the Wayback
Machine and Common Crawl, across every web era from 1994 table-soup to 2026
SPA shells.

```
manifest ──▶ collect ──▶ features ──▶ extract ──▶ dedup ──▶ draft-gold ──▶ score
(curated     (CDX +      (structure,  (pipeline+  (SimHash   (auto-draft,   (F1 vs gold,
 sites)       raw bytes)  era, page    baselines)  clusters)  human review)  filter+dedup
                          type)                                              accuracy)
```

## Quickstart

```bash
# inside the backend container: docker compose exec backend bash
python -m evals.runner status                 # what exists, which extractors work
python -m evals.runner collect                # fetch snapshots per corpus_manifest.yaml
python -m evals.runner features               # classify structure/era/page-type
python -m evals.runner extract --extractor pipeline --extractor trafilatura
python -m evals.runner dedup   --extractor trafilatura
python -m evals.runner draft-gold --per-site 1
#   → review evals/gold/*.yaml, fix title/body, set review_status: approved
python -m evals.runner score   --extractor pipeline --extractor trafilatura
```

Unit tests (offline, no network, no app imports):

```bash
docker compose exec backend pytest evals/tests --no-cov -q
```

`--no-cov` matters: `backend/pytest.ini` enforces `--cov=app --cov-fail-under=80`,
which is meaningless for the eval package.

## What gets measured

| Scoreboard | Question | Metric |
|---|---|---|
| Extraction | Did we capture the right title/body/metadata? | Token-multiset F1 (order-free) **and** word 4-gram shingle F1 (order-sensitive), per extractor × era × category, with bootstrap 95% CIs. Title/author scored as fields with partial credit; dates with ±1-day tolerance and coverage reported separately. |
| Filtering | Do we keep articles and drop lists/search/noise? | Multiclass confusion for the structural classifier; binary content-detection P/R/F1 for both the classifier and the app's URL-regex filter (`intelligent_filter.is_list_page`). |
| Dedup | Do near-identical bodies cluster? | Pairwise P/R/F1 against manifest `dup_group` ground truth. |
| Corpus | Is the corpus actually diverse? | Era/category/page-type distributions + pairwise cosine of per-site structure fingerprints (similar-site pairs get flagged). |

Metric choices follow the two benchmarks that define this space: the
scrapinghub/article-extraction-benchmark (4-gram shingle F1, bootstrap CIs,
MIT) and WCXB 2026 (word-level F1 across 7 page types — which showed article
scores converge near 0.93 while list/forum/product pages spread 27–33 F1
points; that blind spot is exactly what the negative samples here probe).

## Duplicate detection design

The Internet Archive stores the same article dozens of times where only
header/footer chrome changed. The archive's own CDX `digest` (SHA-1 of raw
bytes) can't see through that, so dedup here operates on the **extracted
body**, in two tiers:

1. **Exact** — sha256 of the normalized token stream (case/whitespace/entity
   churn is invisible).
2. **Near** — 64-bit SimHash over word 5-gram shingles, duplicate at Hamming
   distance ≤ 3 (Manku et al., WWW 2007 parameters). Candidate pairs come
   from pigeonhole banding (k+1 bit-blocks: any pair within distance k must
   agree on one block), so lookup stays O(n) with guaranteed candidate
   recall. Bodies under 50 tokens use tier 1 only (SimHash is unreliable on
   short texts).

Upgrade path if fuzzier matching is ever needed (e.g. dedup *before*
extraction): FineWeb-style MinHash/LSH (5-grams, 14×8 buckets, ~0.75 Jaccard)
via `datasketch` — a new dependency, hence not the default.

## Storage design

- **Content-addressed blob store** (`corpus_data/objects/ab/cd/<sha256>.gz`):
  raw payloads and extracted bodies stored once per unique content. Identical
  re-crawls and identical bodies deduplicate by construction; the savings are
  visible in `runner status` (`fetched` vs `unique_raw_blobs`).
- **SQLite catalog** (`corpus_data/catalog.db`): snapshots, extractions,
  features, labels (multi-source: manifest/classifier/human/app_filter),
  dup clusters. One file, transactional, stdlib.
- `corpus_data/` is git-ignored; gold annotations (`gold/*.yaml`) are curated
  artifacts and **are** checked in.
- Scale-up path (≥10⁶ docs): WARC + zstd with trained dictionaries for blobs,
  parquet/DuckDB for the catalog. The schema ports as-is.

## Corpus policy (`corpus_manifest.yaml`)

~36 entries across four eras (early_static → spa_hydrated) and 12 categories,
including on purpose:

- **Negatives**: Yahoo! 1996 directory, BBC/Guardian front pages, Wikipedia
  `Category:` pages, Stack Overflow tag pages — the filter eval needs things
  that *should* be dropped.
- **Known-hard cases**: IMDb entity pages (structured data, not prose),
  phpBB/reddit threads (weak spot for article extractors).
- **Robustness cases**: post-2020 Twitter/X and Instagram snapshots are JS
  shells (Twitter went client-rendered June 2020) — these measure graceful
  failure and og:-metadata fallback, not extraction success.
- **Dedup seeds**: W3C HTML 4.01 spec (body frozen 1999–2012), BBC .stm
  stories (heavily re-crawled), Wikipedia articles (gradual drift → probes
  the near-dup boundary).
- **Cross-era pairs**: Wikipedia 2005 vs 2023 isolates era effects on the
  same content type.

Availability is validated by `collect` (zero-row entries are reported, not
fatal). Wayback has no cnn.com before mid-2000; the CNN O.J. entry therefore
samples 2000–2002 captures of the unchanged 1996 pages.

## Gold workflow

1. `draft-gold` writes `gold/<site>--<snapshot>.yaml` from the best available
   extraction (`review_status: draft`).
2. A human compares against the archived page, fixes title/body/metadata,
   sets `review_status: approved`. Existing files are never overwritten.
3. Only approved docs are scored (drafts would bias toward the drafting
   extractor). `--include-drafts` exists for smoke tests only.

Optional seed data: the scrapinghub benchmark corpus (181 annotated articles,
MIT) and WCXB (2,008 pages, CC-BY-4.0) can be imported as extra gold if more
volume is needed.

## Design notes & caveats

- **`id_` vs `if_`**: this harness fetches Wayback originals with the `id_`
  modifier (byte-exact). The production pipeline fetches `if_` URLs
  (`wayback_machine.py:175`), which rewrite embedded links. Comparing
  extraction over both is an open eval question the corpus supports.
- The eval core (`textnorm`, `dedup`, `html_features`, classifiers, storage,
  scoring) is stdlib-only and runs anywhere; `collect` needs httpx+pyyaml;
  the `pipeline` extractor needs the backend environment (run in container).
- Era classification is by **structure, not capture date** — a 2020 capture
  of an unchanged 1996 page is early_static, because that's what the
  extractor faces.
- `collapse=digest` on CDX only merges *adjacent* identical captures; real
  dedup always happens on our side.
- All thresholds live in `config.py`; tests in `tests/` encode intended
  classifier behavior on era-representative fixtures, so tune with tests on.
