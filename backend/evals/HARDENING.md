# Eval Harness — Hardening Roadmap (bigger bets)

Status of the quick-win batch (done, 2026-07-06): Retry-After crash, empty-body
dedup false-merge, per-query failure isolation, SQLite `busy_timeout`/`NORMAL`,
BlobStore atomic+deterministic writes, WARC revisit rejection, coverage-floor
exit code + `manifest-lint`, bootstrap-CI suppression at small n, report
provenance stamping, and `draft-gold --from-engine`. All covered by tests
(105 passing).

This file tracks the **remaining M/L-effort work** — the changes that make the
harness's own numbers *trustworthy, reproducible, and regression-guarded*. They
are ordered by leverage. Each item lists the concrete change and the files it
touches.

---

## 0. The one that unblocks everything: real (non-circular) gold — L

**Problem.** `gold/` currently holds only a README, so every extraction score
ran with `--include-drafts` against gold auto-drafted from trafilatura →
trafilatura `token_f1 == 1.0` mechanically. The extraction scoreboard measures
trafilatura against itself; the per-era/category F1 numbers are not real.

**Change.**
1. Build a human-reviewed gold set (see the interactive walkthrough — start
   with `draft-gold --from-engine readability`, then correct + `approved`).
   Target ≥3 articles per era, ≥2 per hard category (forum, qa, social, promo).
2. Optionally import ready-made ground truth:
   - scrapinghub `article-extraction-benchmark` (181 articles, **MIT**) →
     import as gold with `source: scrapinghub`.
   - WCXB (2,008 pages, 7 types, **CC-BY-4.0**) → import the 100-page eval
     subset. *Check redistribution + PII policy first (see §7).*
3. Add an **approval gate**: reject a draft as "approved" if its body is
   >0.98 token-F1 identical to the drafting engine's current output (i.e. the
   human didn't actually review it). Implement in `gold_tools.validate_gold`.
4. Stratify the extraction report by the stored `drafted_from` and asterisk any
   extractor scored against gold it authored.

**Files:** `gold_tools.py`, `score.py`, `report.py`, new `gold/*.yaml`.

---

## 1. Reproducibility lockfile + `--frozen` replay — L

**Problem.** The Internet Archive is not immutable — CDX ordering, snapshot
availability, and even payloads change. Today's 517-snapshot corpus and every
metric are non-reproducible; a re-run can silently differ.

**Change.**
- `collect` writes a committed `corpus_lock.yaml`: for every kept snapshot the
  resolved `(site_key, canonical_url, exact_timestamp | cc_record_id, source,
  warc_filename/offset/length, raw_sha256)`.
- Add `collect --frozen` that fetches *only* the locked coordinates (no
  discovery), so a checkout reproduces the exact corpus.
- Key gold docs to locked snapshot ids; `score` fails loudly on orphaned gold
  instead of silently skipping.

**Files:** `collect.py`, `runner.py`, `gold_tools.py`, new `corpus_lock.yaml`.

---

## 2. Record/replay HTTP cassette + deterministic CI — L

**Problem.** CI only runs offline unit tests; the entire `collect → features →
extract → dedup → score` path is never exercised without live archives, so a
regression in the real pipeline ships undetected.

**Change.**
- `httpx.MockTransport` cassette keyed by `(method, url, params, Range)`,
  recorded once from a tiny golden corpus (5–6 sites + one CC WARC + one
  deliberately-truncated capture).
- Commit the cassette; add a CI job that runs the full runner against it and
  diffs the report to a committed `baseline.json` (see §4).
- Gate the network-touching code behind a `PoliteClient` factory so tests
  inject the mock transport.

**Files:** new `evals/tests/cassette/`, `collect.py` (client injection),
`tests/test_pipeline_e2e.py`, CI config.

---

## 3. `runner compare` regression gate — M

**Problem.** No automated signal when a code/threshold/extractor change moves
the numbers.

**Change.**
- Persist an approved `baseline.json` (headline metrics only: per-extractor
  token-F1, detection P/R/F1, exact-dup invariant, dedup precision).
- `runner compare <report.json>` diffs vs baseline, exits non-zero beyond a
  tolerance. **Multiple-comparison aware:** only gate on large-n cells; small-n
  era/category cells are informational.

**Files:** new `evals/compare.py`, `runner.py`, `baseline.json`.

---

## 4. Site-level held-out threshold split — M

**Problem.** Page-type thresholds in `config.py` are hand-tuned and
`score_filtering` reports over the same 517 snapshots they were tuned on →
in-sample, optimistic. Template leakage (multiple snapshots per site) inflates
it further.

**Change.**
- Add a `fold` column to the manifest (`dev` / `test`), split **by site** (never
  put two snapshots of one site across folds).
- Tune thresholds on `dev`, report detection recall/precision on `test` only.
- Report both so the gap (overfit magnitude) is visible.

**Files:** `manifest.py`, `corpus_manifest.yaml`, `score.py`, `report.py`.

---

## 5. Learned, calibrated page-type classifier — L

**Problem.** 14 hand-guessed vote weights (`classify_page_type.py`) are brittle
and corpus-overfit; the 22% article-recall gap concentrates in `early_static`
and `spa_hydrated`.

**Change.**
- Fit a logistic-regression model on the labeled `PageFeatures` (train on the
  `dev` fold from §4), export coefficients to JSON, do a stdlib dot-product at
  inference. Keep the rule engine as an interpretable fallback / feature source.
- Choose per-class thresholds at **max recall subject to precision == 1.0** on
  dev, verify on test.
- Add a calibrated confidence + an `abstain` label for low-margin pages.

**Files:** new `evals/classifier_model.py`, `classify_page_type.py`,
`config.py`, training script + committed `page_type_model.json`.

---

## 6. Extraction realism — M/L

**Problems & changes:**
- **Score through the real path (L).** The eval calls the raw
  `IntelligentContentExtractor`, skipping production's `min_word_count=50` gate
  and `extract_with_recall` escalation (`content_extraction_service.py`).
  Refactor the gate/escalation to run offline so reported F1 matches what
  production actually keeps — and so the recall path (the fix for the weak
  buckets) is measured.
- **`if_` vs `id_` delta (M).** Eval fetches clean `id_` bytes; production
  consumes `if_` (Wayback chrome injected). Fetch both for a subset and report
  the extraction delta as a contamination metric.
- **Digest verification (M).** Recompute base32-SHA1 of fetched bytes vs the
  stored CDX `digest`; add a `digest_ok`/`partial` column so tolerated
  truncations and bad Ranges are flagged, not silently trusted.
- **More baselines (S–M).** Add resiliparse + goose3 adapters, and one
  LLM-extractor as an accuracy ceiling, to `extract.py`.

**Files:** `extract.py`, `collect.py`, `storage.py`, `content_extraction_service.py`.

---

## 7. Blind-spot backlog (from the completeness review)

- **Decompression bombs (S–M).** `fetch_cc_raw`/`get_bytes` gunzip with no
  decompressed-size ceiling → OOM risk. Add an incremental-decompress cap.
- **Unbounded disk growth (S).** BlobStore + catalog grow forever. Add a
  `runner prune` (drop blobs unreferenced by any snapshot/extraction) and a
  configurable size cap.
- **Dependency pinning (S).** Reproducibility needs the eval's own extractor
  deps pinned (trafilatura/newspaper/readability/lxml) in a lockfile, not just
  version-stamped. Also pin the app's currently-unpinned `requests`/
  `zstandard`/`numpy`/`aiofiles` (separate from evals but related).
- **CJK/RTL metric validity (M).** Before adding non-Latin gold, fix
  `textnorm.tokenize` — the `\w+` regex yields near-empty token sets for
  Chinese/Japanese/Thai (no word spaces), making `token_f1` meaningless. Add a
  script-aware tokenizer (char-n-gram fallback for spaceless scripts) + NFC.
- **Legal / PII (policy).** Committing archived third-party bodies to git is a
  GDPR/copyright concern (Dutch-newsroom context). Decide: store only
  hashes+offsets (re-fetch on demand) vs a vetted redistributable subset. Gate
  before any external gold or archived bodies land in version control.
- **SSRF / redirects (S).** Fetches target fixed archive hosts, but
  manifest-supplied URLs + archive redirects are followed without host
  allow-listing. Add an allow-list of archive hosts.
- **Thread-safety (S).** If an extraction watchdog thread is added, don't share
  the one `sqlite3` connection across threads (`check_same_thread`).

---

## 8. Corpus expansion — M/L

- Add the WCXB-hard categories the corpus claims to target but lacks: product/
  e-commerce, recipe/structured-data, documentation.
- Add 4–6 real `spa_hydrated` entries (only 2 today — `manifest-lint` flags it).
- Add non-Latin (CJK) + more Dutch coverage (paired with §7 tokenizer fix).
- Firm-label the 7 `mixed` 90s homepages so they count in filter scoring.
- Fix the ~10 zero-result deep/date-prefix sites (narrow prefixes or route to
  Common Crawl — same pattern already applied to arstechnica/SO/reddit).

**Files:** `corpus_manifest.yaml`, `manifest.py` (`VALID_CATEGORIES`).

---

### Suggested execution order
0 (gold) → 1 (lockfile) → 3 (compare gate) → 4 (held-out split) → 2 (CI
cassette) → 6 (extraction realism) → 5 (learned classifier) → 8 (corpus) → 7
(blind spots, as they become relevant). Items 0–4 make the numbers real and
protected; everything after improves the numbers themselves.
