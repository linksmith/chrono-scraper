"""Report assembly and rendering (JSON for machines, Markdown for humans).

The report answers four questions, each its own section:

1. Corpus — what did we collect, is it structurally diverse, how much
   storage did content-addressing save?
2. Classification — how do snapshots distribute over eras and page types?
3. Extraction — per extractor / era / category body F1 against gold, the
   headline result.
4. Filtering & Dedup — does the pipeline keep articles and drop noise, and
   does near-dup clustering match ground truth?
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from evals.config import EvalConfig
from evals.html_features import cosine
from evals.storage import BlobStore, Catalog


def _pkg_version(name: str) -> str:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return "unknown"


def provenance(cfg: EvalConfig | None = None) -> dict:
    """Best-effort run provenance so a metric change is attributable to a
    threshold vs manifest vs extractor-version change. Never raises."""
    info: dict = {
        "extractor_versions": {
            name: _pkg_version(name)
            for name in ("trafilatura", "readability-lxml", "newspaper3k", "lxml")
        },
    }
    try:
        info["git_sha"] = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip() or "unknown"
    except Exception:
        info["git_sha"] = "unknown"
    if cfg is not None:
        try:
            info["manifest_sha256"] = hashlib.sha256(
                Path(cfg.manifest_path).read_bytes()
            ).hexdigest()[:16]
            from dataclasses import asdict

            thresholds = asdict(cfg)
            thresholds.pop("data_dir", None)
            thresholds.pop("gold_dir", None)
            thresholds.pop("manifest_path", None)
            info["config"] = {
                k: v for k, v in thresholds.items()
                if k in ("dedup", "scoring", "page_type", "era")
            }
        except Exception:
            pass
    return info

logger = logging.getLogger(__name__)

SIMILAR_SITE_COSINE = 0.90  # per-site mean-fingerprint similarity worth flagging


# --------------------------------------------------------------------------
# Corpus overview
# --------------------------------------------------------------------------

def _site_fingerprints(catalog: Catalog) -> dict[str, list[float]]:
    """Mean structure fingerprint per site (unit-normalized)."""
    sums: dict[str, list[float]] = {}
    counts: Counter[str] = Counter()
    for snapshot in catalog.snapshots(fetched_only=True):
        features = catalog.get_features(snapshot["id"])
        if not features or not features.get("fingerprint"):
            continue
        vector = features["fingerprint"]
        site = snapshot["site_key"]
        if site not in sums:
            sums[site] = [0.0] * len(vector)
        sums[site] = [a + b for a, b in zip(sums[site], vector)]
        counts[site] += 1
    means = {}
    for site, total in sums.items():
        norm = sum(v * v for v in total) ** 0.5
        if norm > 0:
            means[site] = [v / norm for v in total]
    return means


def corpus_overview(catalog: Catalog, store: BlobStore) -> dict:
    summary = catalog.summary()
    blob_stats = store.stats()

    label_dist = {}
    for kind, source in (("era", "classifier"), ("page_type", "classifier"),
                         ("page_type", "manifest"), ("category", "manifest")):
        label_dist[f"{kind}/{source}"] = dict(Counter(catalog.labels(kind, source).values()))

    per_site = defaultdict(lambda: {"snapshots": 0, "fetched": 0, "errors": 0})
    for snapshot in catalog.snapshots():
        entry = per_site[snapshot["site_key"]]
        entry["snapshots"] += 1
        if snapshot["raw_sha256"]:
            entry["fetched"] += 1
        if snapshot["fetch_error"]:
            entry["errors"] += 1

    fingerprints = _site_fingerprints(catalog)
    sites = sorted(fingerprints)
    similar_pairs = []
    cosines = []
    for i, site_a in enumerate(sites):
        for site_b in sites[i + 1 :]:
            value = cosine(fingerprints[site_a], fingerprints[site_b])
            cosines.append(value)
            if value >= SIMILAR_SITE_COSINE:
                similar_pairs.append({"sites": [site_a, site_b], "cosine": round(value, 3)})

    total_raw = sum(
        int(s["raw_bytes"] or 0) for s in catalog.snapshots(fetched_only=True)
    )
    return {
        "summary": summary,
        "storage": {
            **blob_stats,
            "logical_raw_bytes": total_raw,
            "dedup_note": (
                f"{summary['fetched']} fetched snapshots map to "
                f"{summary['unique_raw_blobs']} unique raw payloads"
            ),
        },
        "labels": label_dist,
        "per_site": dict(sorted(per_site.items())),
        "diversity": {
            "sites_with_fingerprints": len(fingerprints),
            "mean_pairwise_cosine": round(sum(cosines) / len(cosines), 3) if cosines else None,
            "structurally_similar_pairs": similar_pairs,
        },
    }


# ------------------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------------------

def _table(headers: list[str], rows: list[list]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def _fmt_ci(ci: dict) -> str:
    if ci.get("ci_suppressed") or ci.get("ci_low") is None:
        return f"{ci['mean']:.3f} (n={ci['n']}, CI n/a)"
    return f"{ci['mean']:.3f} [{ci['ci_low']:.3f}, {ci['ci_high']:.3f}]"


def _render_extraction(extraction: dict, lines: list[str]) -> None:
    proxy = extraction.get("gold_mode") == "proxy-draft"
    lines.append("## Extraction quality")
    if proxy:
        lines.append(
            "\n> ⚠️ **PROXY gold** — scored against *auto-drafted, unreviewed* gold "
            "(drafted from trafilatura). These numbers measure **agreement with "
            "trafilatura**, not absolute quality — trafilatura scores ~1.0 by "
            "construction. For real quality, review the drafts in `gold/`, set "
            "`review_status: approved`, and re-run `score` (without `--include-drafts`)."
        )
    else:
        lines.append("\nScored against human-approved gold.")
    lines.append(
        f"\nGold docs: {extraction['n_gold']} · scored pairs: {extraction['n_scored']}"
        f" · missing: {extraction['n_missing']}\n"
    )
    rows = []
    for extractor, agg in extraction["by_extractor"].items():
        rows.append([
            extractor, _fmt_ci(agg["token_f1"]), f"{agg['shingle_f1']:.3f}",
            f"{agg['title_similarity']:.3f}",
            f"{agg['date_accuracy']}" if agg["date_accuracy"] is not None else "–",
            f"{agg['date_coverage']:.0%}", agg["below_target"], agg["n"],
        ])
    lines.append(_table(
        ["extractor", "token F1 [95% CI]", "shingle F1", "title sim",
         "date acc", "date cov", f"below target", "n"],
        rows,
    ))

    # era x extractor matrix of token F1 means
    matrix: dict[str, dict[str, str]] = defaultdict(dict)
    extractors = set()
    for key, agg in extraction["by_extractor_era"].items():
        extractor, era = key.split("|", 1)
        extractors.add(extractor)
        matrix[era][extractor] = f"{agg['token_f1']['mean']:.3f} (n={agg['n']})"
    if matrix:
        cols = sorted(extractors)
        lines.append("\n### Token F1 by era\n")
        lines.append(_table(
            ["era", *cols],
            [[era, *[matrix[era].get(c, "–") for c in cols]] for era in sorted(matrix)],
        ))

    matrix.clear()
    extractors.clear()
    for key, agg in extraction["by_extractor_category"].items():
        extractor, category = key.split("|", 1)
        extractors.add(extractor)
        matrix[category][extractor] = f"{agg['token_f1']['mean']:.3f} (n={agg['n']})"
    if matrix:
        cols = sorted(extractors)
        lines.append("\n### Token F1 by category\n")
        lines.append(_table(
            ["category", *cols],
            [[cat, *[matrix[cat].get(c, "–") for c in cols]] for cat in sorted(matrix)],
        ))


def _render_filtering(filtering: dict, lines: list[str]) -> None:
    lines.append("\n## Page-type / filter accuracy")
    lines.append(f"\nGround-truth labeled snapshots: {filtering['n_ground_truth']}\n")
    clf = filtering["classifier"]
    lines.append(f"Structural classifier accuracy: **{clf['accuracy']}**\n")
    content = clf["content_detection"]
    lines.append(
        f"Content detection (article vs rest): precision {content['precision']}, "
        f"recall {content['recall']}, F1 {content['f1']}\n"
    )
    used = [t for t, row in clf["confusion"].items() if sum(row.values())]
    if used:
        preds = sorted({p for row in clf["confusion"].values() for p, n in row.items() if n})
        lines.append(_table(
            ["truth \\ predicted", *preds],
            [[t, *[clf["confusion"][t].get(p, 0) for p in preds]] for t in sorted(used)],
        ))
    by_era = clf.get("content_detection_by_era") or {}
    if by_era:
        lines.append("\n### Content detection (article vs rest) by era\n")
        lines.append(_table(
            ["era", "precision", "recall", "f1", "tp", "fp", "fn"],
            [[e, d["precision"], d["recall"], d["f1"], d["tp"], d["fp"], d["fn"]]
             for e, d in by_era.items()],
        ))
    app = filtering["app_url_filter"]
    detection = app["content_detection"]
    lines.append(
        f"\nApp URL-regex filter (n={app['n_evaluated']}): precision {detection['precision']}, "
        f"recall {detection['recall']}, F1 {detection['f1']} — {app['note']}"
    )


def _render_dedup(dedup: dict, lines: list[str]) -> None:
    lines.append("\n## Near-duplicate detection")
    lines.append(
        "\n**Exact-duplicate invariant** (clean signal): byte-identical extracted "
        "bodies must always co-cluster. The seed pair-P/R below is confounded by "
        "seed pages whose content genuinely drifts across captures (Wikipedia over "
        "years), so it understates real quality — read it alongside the invariant "
        "and the real-world redundancy table.\n"
    )
    inv_rows = []
    for extractor, result in dedup.items():
        inv = result.get("exact_dup_invariant", {})
        inv_rows.append([
            extractor, inv.get("identical_body_pairs", "–"),
            inv.get("co_clustered", "–"),
            inv.get("rate") if inv.get("rate") is not None else "–",
        ])
    lines.append(_table(
        ["extractor", "identical-body pairs", "co-clustered", "rate (want 1.0)"], inv_rows,
    ))
    lines.append("\nSeed pair-accuracy (same canonical page = duplicate):\n")
    rows = []
    for extractor, result in dedup.items():
        pairwise = result["pairwise"]
        rows.append([
            extractor, result["n_labeled_snapshots"], result["n_pages"],
            pairwise["precision"], pairwise["recall"], pairwise["f1"],
        ])
    lines.append(_table(
        ["extractor", "seed snapshots", "distinct pages", "pair precision", "pair recall", "pair F1"],
        rows,
    ))


def _render_dedup_yield(dedup_yield: dict, lines: list[str]) -> None:
    lines.append("\n### Real-world redundancy caught (all extracted bodies)\n")
    lines.append(
        "How many fetched snapshots collapse into unique bodies — the storage "
        "savings from body-level dedup, broken down by era.\n"
    )
    for extractor, result in dedup_yield.items():
        if not result:
            continue
        o = result["overall"]
        lines.append(
            f"\n**{extractor}** — overall {o['snapshots']} snapshots → "
            f"{o['unique_bodies']} unique bodies ({o['redundancy_pct']}% redundant)\n"
        )
        rows = [
            [era, d["snapshots"], d["unique_bodies"], d["redundant"], f"{d['redundancy_pct']}%"]
            for era, d in result["by_era"].items()
        ]
        lines.append(_table(["era", "snapshots", "unique bodies", "redundant", "redundancy"], rows))


def render_markdown(report: dict) -> str:
    lines = [f"# Chrono Scraper extraction eval — {report['generated_at']}"]
    prov = report.get("provenance")
    if prov:
        vers = ", ".join(f"{k} {v}" for k, v in prov.get("extractor_versions", {}).items())
        lines.append(
            f"\n_git {prov.get('git_sha', '?')} · manifest {prov.get('manifest_sha256', '?')} · {vers}_"
        )
    corpus = report.get("corpus")
    if corpus:
        summary = corpus["summary"]
        storage = corpus["storage"]
        lines.append("\n## Corpus")
        lines.append(
            f"\nSites: {summary['sites']} · snapshots: {summary['snapshots']} · "
            f"fetched: {summary['fetched']} · fetch errors: {summary['fetch_errors']}"
        )
        lines.append(
            f"\nStorage: {storage['objects']} unique blobs, "
            f"{storage['compressed_bytes'] / 1_048_576:.1f} MiB compressed "
            f"({storage['logical_raw_bytes'] / 1_048_576:.1f} MiB logical). "
            f"{storage['dedup_note']}."
        )
        for kind, dist in corpus["labels"].items():
            if dist:
                pretty = ", ".join(f"{k}: {v}" for k, v in sorted(dist.items(), key=lambda kv: -kv[1]))
                lines.append(f"\n- **{kind}** — {pretty}")
        diversity = corpus["diversity"]
        if diversity["mean_pairwise_cosine"] is not None:
            lines.append(
                f"\nStructural diversity: mean pairwise site cosine "
                f"{diversity['mean_pairwise_cosine']} "
                f"(similar pairs flagged: {len(diversity['structurally_similar_pairs'])})"
            )
    if report.get("extraction"):
        lines.append("")
        _render_extraction(report["extraction"], lines)
    if report.get("filtering"):
        _render_filtering(report["filtering"], lines)
    if report.get("dedup"):
        _render_dedup(report["dedup"], lines)
    if report.get("dedup_yield"):
        _render_dedup_yield(report["dedup_yield"], lines)
    return "\n".join(lines) + "\n"


def build_report(
    corpus: dict | None = None,
    extraction: dict | None = None,
    filtering: dict | None = None,
    dedup: dict | None = None,
    dedup_yield: dict | None = None,
    provenance: dict | None = None,
) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provenance": provenance,
        "corpus": corpus,
        "extraction": extraction,
        "filtering": filtering,
        "dedup": dedup,
        "dedup_yield": dedup_yield,
    }


def write_reports(cfg: EvalConfig, report: dict) -> tuple[Path, Path]:
    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["generated_at"].replace(":", "").replace("-", "").replace("+0000", "Z")
    json_path = cfg.reports_dir / f"eval-{stamp}.json"
    md_path = cfg.reports_dir / f"eval-{stamp}.md"
    # samples are bulky; keep them in JSON only
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(report))
    logger.info("report: wrote %s and %s", json_path, md_path)
    return json_path, md_path
