"""Scoring: extraction vs gold, filter accuracy, dedup accuracy.

Three independent scoreboards:

* ``score_extractions``  — body token-F1 / shingle-F1 + title/author/date
  field scores per (gold sample x extractor), aggregated by extractor, era
  and category, with bootstrap 95% CIs on the headline F1 (the
  scrapinghub-benchmark convention).
* ``score_filtering``    — does each page-type predictor (this harness's
  structural classifier; the app's URL-regex filter) agree with labeled
  ground truth? Multiclass confusion for the classifier, binary
  keep-content/drop-noise for both.
* ``score_dedup``        — pairwise precision/recall of predicted duplicate
  clusters against manifest ``dup_group`` ground truth.
"""

from __future__ import annotations

import logging
import random
import statistics
from collections import defaultdict

from evals.classify_page_type import PAGE_TYPES
from evals.config import EvalConfig
from evals.gold_tools import GoldDoc
from evals.storage import BlobStore, Catalog
from evals.text_metrics import PRF, score_sample
from evals.urls import canonicalize_url

logger = logging.getLogger(__name__)


MIN_CI_N = 8  # below this a bootstrap CI is noise dressed as statistics


def bootstrap_ci(
    values: list[float], iterations: int = 1000, seed: int = 13, min_ci_n: int = MIN_CI_N
) -> dict:
    """Mean with 95% bootstrap CI (percentile method).

    For n < ``min_ci_n`` the CI is suppressed (``ci_low``/``ci_high`` = None,
    ``ci_suppressed`` = True): resampling 2-3 points produces an interval that
    looks authoritative but means nothing, so we report the mean and n only.
    """
    if not values:
        return {"mean": 0.0, "ci_low": None, "ci_high": None, "n": 0, "ci_suppressed": True}
    mean = round(statistics.fmean(values), 4)
    if len(values) < min_ci_n:
        return {"mean": mean, "ci_low": None, "ci_high": None, "n": len(values), "ci_suppressed": True}
    rng = random.Random(seed)
    means = sorted(
        statistics.fmean(rng.choices(values, k=len(values))) for _ in range(iterations)
    )
    hi_idx = min(int(0.975 * iterations), iterations - 1)
    return {
        "mean": mean,
        "ci_low": round(means[int(0.025 * iterations)], 4),
        "ci_high": round(means[hi_idx], 4),
        "n": len(values),
        "ci_suppressed": False,
    }


def _binary_prf(tp: int, fp: int, fn: int) -> dict:
    prf = PRF.from_counts(tp, tp + fp, tp + fn)
    return {
        "precision": round(prf.precision, 4),
        "recall": round(prf.recall, 4),
        "f1": round(prf.f1, 4),
        "tp": tp, "fp": fp, "fn": fn,
    }


# --------------------------------------------------------------------------
# Extraction scoring
# --------------------------------------------------------------------------

def score_extractions(
    catalog: Catalog,
    store: BlobStore,
    cfg: EvalConfig,
    gold_docs: list[GoldDoc],
    extractors: list[str],
) -> dict:
    from evals.extract import extract_snapshot  # local import avoids cycles

    era_map = catalog.labels("era", "classifier")
    era_hints = catalog.labels("era_hint", "manifest")
    categories = catalog.labels("category", "manifest")

    samples: list[dict] = []
    missing = 0
    for gold in gold_docs:
        snapshot = catalog.snapshot_by_id(gold.snapshot_id)
        if snapshot is None or not snapshot["raw_sha256"]:
            logger.warning("score: gold %s references missing snapshot %s", gold.sample_id, gold.snapshot_id)
            missing += 1
            continue
        era = era_map.get(gold.snapshot_id) or era_hints.get(gold.snapshot_id) or "unknown"
        category = categories.get(gold.snapshot_id) or "unknown"
        for extractor in extractors:
            extraction_id = extract_snapshot(catalog, store, cfg, snapshot, extractor)
            if extraction_id is None:
                missing += 1
                continue
            row = catalog.conn.execute(
                "SELECT * FROM extractions WHERE id=?", (extraction_id,)
            ).fetchone()
            pred_body = store.get_text(row["body_sha256"]) if row["body_sha256"] else ""
            result = score_sample(
                gold_body=gold.body,
                pred_body=pred_body,
                gold_title=gold.title,
                pred_title=row["title"],
                gold_author=gold.author,
                pred_author=row["author"],
                gold_date=gold.date_published,
                pred_date=row["date_published"],
                date_tolerance_days=cfg.scoring.date_tolerance_days,
            )
            samples.append(
                {
                    "sample_id": gold.sample_id,
                    "site": snapshot["site_key"],
                    "era": era,
                    "category": category,
                    "extractor": extractor,
                    "token_f1": round(result.body_token.f1, 4),
                    "token_precision": round(result.body_token.precision, 4),
                    "token_recall": round(result.body_token.recall, 4),
                    "shingle_f1": round(result.body_shingle.f1, 4),
                    "title_similarity": round(result.title.similarity, 4),
                    "author_f1": round(result.author.token_f1, 4),
                    "date_ok": result.date_ok,
                    "gold_tokens": result.gold_tokens,
                    "pred_tokens": result.pred_tokens,
                    "extraction_error": row["error"],
                }
            )

    def _aggregate(group_keys: tuple[str, ...]) -> dict:
        grouped: dict[tuple, list[dict]] = defaultdict(list)
        for sample in samples:
            grouped[tuple(sample[k] for k in group_keys)].append(sample)
        out = {}
        for group, rows in sorted(grouped.items()):
            token_f1s = [r["token_f1"] for r in rows]
            dated = [r["date_ok"] for r in rows if r["date_ok"] is not None]
            out["|".join(map(str, group))] = {
                "token_f1": bootstrap_ci(token_f1s),
                "shingle_f1": round(statistics.fmean(r["shingle_f1"] for r in rows), 4),
                "title_similarity": round(statistics.fmean(r["title_similarity"] for r in rows), 4),
                "date_accuracy": round(statistics.fmean(dated), 4) if dated else None,
                "date_coverage": round(len(dated) / len(rows), 4),
                "below_target": sum(1 for f in token_f1s if f < cfg.scoring.body_f1_target),
                "n": len(rows),
            }
        return out

    return {
        "n_gold": len(gold_docs),
        "n_scored": len(samples),
        "n_missing": missing,
        "samples": samples,
        "by_extractor": _aggregate(("extractor",)),
        "by_extractor_era": _aggregate(("extractor", "era")),
        "by_extractor_category": _aggregate(("extractor", "category")),
    }


# ------------------------------------------------------------------------------
# Filter / page-type scoring
# ------------------------------------------------------------------------------

def _detection_key(truth_content: bool, pred_content: bool) -> str:
    return ("tp" if truth_content else "fp") if pred_content else ("fn" if truth_content else "tn")


def score_filtering(catalog: Catalog, cfg: EvalConfig) -> dict:
    truth = dict(catalog.labels("page_type", "manifest"))
    truth.update(catalog.labels("page_type", "human"))  # human overrides manifest
    classifier = catalog.labels("page_type", "classifier")
    app_filter = catalog.labels("app_filter_keep", "app_filter")
    era = catalog.labels("era", "classifier")

    confusion: dict[str, dict[str, int]] = {t: {p: 0 for p in PAGE_TYPES} for t in PAGE_TYPES}
    clf = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    app = {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "n": 0}
    # Per-era content-detection for the classifier — shows detail-vs-noise
    # separation holds for 90s/00s markup as well as modern pages.
    by_era: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "tn": 0})

    for snapshot_id, true_label in truth.items():
        truth_content = true_label == "article"
        predicted = classifier.get(snapshot_id)
        if predicted:
            confusion[true_label][predicted] += 1
            key = _detection_key(truth_content, predicted == "article")
            clf[key] += 1
            by_era[era.get(snapshot_id, "unknown")][key] += 1
        app_pred = app_filter.get(snapshot_id)
        if app_pred:
            app["n"] += 1
            key = _detection_key(truth_content, app_pred == "keep")
            app[key] += 1

    return {
        "n_ground_truth": len(truth),
        "classifier": {
            "confusion": confusion,
            "accuracy": _confusion_accuracy(confusion),
            "content_detection": _binary_prf(clf["tp"], clf["fp"], clf["fn"]),
            "content_detection_by_era": {
                e: _binary_prf(c["tp"], c["fp"], c["fn"]) for e, c in sorted(by_era.items())
            },
        },
        "app_url_filter": {
            "n_evaluated": app["n"],
            "content_detection": _binary_prf(app["tp"], app["fp"], app["fn"]),
            "note": "app filter drops on URL patterns only (pre-fetch); "
                    "compared against structural ground truth",
        },
    }


def dedup_yield(catalog: Catalog, extractor: str) -> dict | None:
    """Real-world redundancy caught over ALL extracted bodies (not just seed
    groups): how many fetched snapshots collapse into unique bodies, overall
    and per era. Answers "are we storing only non-duplicates?" across eras."""
    clusters = catalog.clusters(extractor)
    if not clusters:
        return None
    era = catalog.labels("era", "classifier")
    overall_items = 0
    overall_clusters: set[str] = set()
    by_era: dict[str, dict] = defaultdict(lambda: {"items": 0, "clusters": set()})
    for row in catalog.extractions(extractor, with_bodies_only=True):
        cluster_id = clusters.get(int(row["id"]))
        if cluster_id is None:
            continue
        overall_items += 1
        overall_clusters.add(cluster_id)
        bucket = by_era[era.get(int(row["snapshot_id"]), "unknown")]
        bucket["items"] += 1
        bucket["clusters"].add(cluster_id)

    def _fmt(items: int, n_clusters: int) -> dict:
        redundant = items - n_clusters
        return {
            "snapshots": items,
            "unique_bodies": n_clusters,
            "redundant": redundant,
            "redundancy_pct": round(100 * redundant / items, 1) if items else 0.0,
        }

    return {
        "extractor": extractor,
        "overall": _fmt(overall_items, len(overall_clusters)),
        "by_era": {e: _fmt(v["items"], len(v["clusters"])) for e, v in sorted(by_era.items())},
    }


def _confusion_accuracy(confusion: dict[str, dict[str, int]]) -> float | None:
    total = sum(sum(row.values()) for row in confusion.values())
    if not total:
        return None
    correct = sum(confusion[label][label] for label in confusion)
    return round(correct / total, 4)


# ------------------------------------------------------------------------------
# Dedup scoring
# ------------------------------------------------------------------------------

def score_dedup(catalog: Catalog, cfg: EvalConfig, extractor: str) -> dict:
    """Pairwise near-dup P/R on curated seed pages.

    Universe = snapshots carrying a manifest ``dup_group`` label that have an
    extraction under ``extractor``. Truth: two snapshots are duplicates iff
    they are captures of the SAME canonical page (same site + canonical URL).
    Seed pages are chosen for stable content, so their captures over time are
    genuine near-duplicates that *should* cluster, while different pages within
    one seed entry (e.g. several BBC stories) must NOT merge. Canonicalizing
    the URL collapses ``:80``/``#fragment`` variants of one page.
    """
    seed_snapshots = set(catalog.labels("dup_group", "manifest"))
    cluster_of = catalog.clusters(extractor)

    items: list[tuple[tuple[str, str], str | None, str | None]] = []
    for row in catalog.extractions(extractor, with_bodies_only=True):
        if int(row["snapshot_id"]) not in seed_snapshots:
            continue
        truth_key = (row["site_key"], canonicalize_url(row["url"]))
        items.append((truth_key, cluster_of.get(int(row["id"])), row["body_key"]))

    tp = fp = fn = tn = 0
    exact_pairs = exact_coclustered = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            same_truth = items[i][0] == items[j][0]
            cluster_a, cluster_b = items[i][1], items[j][1]
            same_pred = cluster_a is not None and cluster_a == cluster_b
            if same_pred and same_truth:
                tp += 1
            elif same_pred:
                fp += 1
            elif same_truth:
                fn += 1
            else:
                tn += 1
            # Invariant: byte-identical bodies (same normalized body_key) MUST
            # co-cluster regardless of URL — the clean correctness signal, since
            # the P/R above is confounded by seed pages whose content genuinely
            # drifts across captures (e.g. Wikipedia over years).
            if items[i][2] and items[i][2] == items[j][2]:
                exact_pairs += 1
                if same_pred:
                    exact_coclustered += 1

    return {
        "extractor": extractor,
        "n_labeled_snapshots": len(items),
        "n_pages": len({key for key, _, _ in items}),
        "pairs": {"positive": tp + fn, "negative": fp + tn},
        "pairwise": _binary_prf(tp, fp, fn),
        "exact_dup_invariant": {
            "identical_body_pairs": exact_pairs,
            "co_clustered": exact_coclustered,
            "rate": round(exact_coclustered / exact_pairs, 4) if exact_pairs else None,
        },
        "note": "P/R positives = captures of the same canonical seed page (confounded "
                "by intentional content drift, e.g. Wikipedia); exact_dup_invariant "
                "is the clean signal — identical bodies must always co-cluster (want 1.0)",
    }
