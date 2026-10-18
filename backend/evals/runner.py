"""CLI entry point: ``python -m evals.runner <command>``.

Pipeline order:

    collect → features → extract → dedup → draft-gold → (human review) → score

Run inside the backend container (``docker compose exec backend python -m
evals.runner ...``) for the ``pipeline`` extractor; the other extractors and
all offline stages work anywhere the backend requirements are installed.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from evals.classify_era import classify_era
from evals.classify_page_type import PAGE_TYPES, classify_page_type
from evals.config import EvalConfig, load_config
from evals.dedup import BodyFingerprint, NearDupClusterer
from evals.html_features import decode_html, extract_features
from evals.storage import BlobStore, Catalog

logger = logging.getLogger("evals")


def _open(cfg: EvalConfig) -> tuple[Catalog, BlobStore]:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    return Catalog(cfg.catalog_path), BlobStore(cfg.objects_dir)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_status(cfg: EvalConfig, args) -> int:
    from evals.extract import available_extractors
    from evals.gold_tools import validate_gold
    from evals.manifest import load_manifest

    entries = load_manifest(cfg.manifest_path)
    catalog, store = _open(cfg)
    print(f"manifest: {len(entries)} site entries ({cfg.manifest_path})")
    print(f"data dir: {cfg.data_dir}")
    print(json.dumps(catalog.summary(), indent=2))
    print(f"blob store: {json.dumps(store.stats())}")
    print("extractors:")
    for name, status in available_extractors().items():
        print(f"  {name}: {status}")
    gold = validate_gold(cfg.gold_dir)
    print(f"gold: {gold['files']} files — approved {gold['approved']}, draft {gold['draft']}")
    for name, problems in gold["problems"].items():
        print(f"  PROBLEM {name}: {problems}")
    return 0


def cmd_collect(cfg: EvalConfig, args) -> int:
    from evals.collect import collect_all
    from evals.manifest import load_manifest

    entries = load_manifest(cfg.manifest_path)
    catalog, store = _open(cfg)
    results = collect_all(entries, catalog, store, cfg, site_filter=args.site)
    total = {"cdx_rows": 0, "selected": 0, "fetched": 0, "cached": 0, "errors": 0, "query_errors": 0}
    # Distinguish "archive has nothing" (manifest problem) from "our queries
    # errored" (transient/network) — they need different fixes.
    zero_archived, query_error_sites = [], []
    for result in results:
        for key in total:
            total[key] += result.get(key, 0)
        if result["selected"] == 0:
            (query_error_sites if result.get("query_errors") else zero_archived).append(result["site"])
    print(json.dumps({"totals": total, "sites": len(results)}, indent=2))
    if zero_archived:
        print(f"sites with 0 archived captures (check manifest URL/prefix): {zero_archived}")
    if query_error_sites:
        print(f"sites that errored during query (transient — safe to re-run --site): {query_error_sites}")

    # Coverage floor: fail loudly if a full run (not a single --site) leaves the
    # corpus too thin to trust, so a silent collapse can't masquerade as success.
    if not args.site:
        floor = args.min_sites
        collected = sum(1 for r in results if r["selected"] > 0)
        if collected < floor:
            print(f"COVERAGE FLOOR NOT MET: {collected} sites with data < required {floor}")
            return 1
    return 0


def cmd_manifest_lint(cfg: EvalConfig, args) -> int:
    from collections import Counter
    from evals.manifest import load_manifest

    entries = load_manifest(cfg.manifest_path)
    print(f"manifest: {len(entries)} entries ({cfg.manifest_path})")
    ok = True
    for dim, key in (("era_hint", lambda e: e.era_hint or "(none)"),
                     ("expected_page_type", lambda e: e.expected_page_type),
                     ("category", lambda e: e.category),
                     ("source", lambda e: e.source)):
        dist = Counter(key(e) for e in entries)
        print(f"  {dim}: {dict(sorted(dist.items(), key=lambda kv: -kv[1]))}")
    # Balance warnings: every era and a healthy negatives count.
    eras = Counter(e.era_hint for e in entries if e.era_hint)
    for era in ("early_static", "table_layout", "css_layout", "html5_semantic", "spa_hydrated"):
        if eras.get(era, 0) < args.min_per_era:
            print(f"  WARN: era '{era}' has {eras.get(era, 0)} entries (< {args.min_per_era})")
            ok = False
    negatives = sum(1 for e in entries if e.expected_page_type in ("list", "search"))
    if negatives < args.min_negatives:
        print(f"  WARN: only {negatives} negative (list/search) entries (< {args.min_negatives})")
        ok = False
    dedup_groups = len({e.dedup_group for e in entries if e.dedup_group})
    print(f"  dedup seed groups: {dedup_groups}")
    print("OK" if ok else "WARNINGS present")
    return 0 if ok else 1


def cmd_features(cfg: EvalConfig, args) -> int:
    catalog, store = _open(cfg)
    app_filter = _load_app_filter()
    done = errors = 0
    for snapshot in catalog.snapshots(site_key=args.site, fetched_only=True):
        try:
            html = decode_html(store.get(snapshot["raw_sha256"]))
            features = extract_features(html)
            catalog.set_features(snapshot["id"], features.to_dict())

            year = int(snapshot["timestamp"][:4]) if snapshot["timestamp"][:4].isdigit() else None
            era = classify_era(features, cfg.era, snapshot_year=year)
            catalog.set_label(
                snapshot["id"], "era", era.label, "classifier",
                {"confidence": era.confidence, "signals": era.signals[:8]},
            )
            page_type = classify_page_type(features, snapshot["url"], cfg.page_type)
            catalog.set_label(
                snapshot["id"], "page_type", page_type.label, "classifier",
                {"confidence": page_type.confidence, "scores": page_type.scores},
            )
            if app_filter is not None:
                keep = "drop" if app_filter.is_list_page(snapshot["url"]) else "keep"
                catalog.set_label(snapshot["id"], "app_filter_keep", keep, "app_filter")
            done += 1
        except Exception:
            logger.exception("features: failed on snapshot %s", snapshot["id"])
            errors += 1
    print(f"features: processed {done}, errors {errors}, app_filter={'on' if app_filter else 'off'}")
    return 0 if errors == 0 else 1


def _load_app_filter():
    try:
        from app.services.intelligent_filter import get_intelligent_filter

        return get_intelligent_filter()
    except Exception as exc:
        logger.warning("features: app filter unavailable (%s) — skipping app_filter labels", exc)
        return None


def cmd_extract(cfg: EvalConfig, args) -> int:
    from evals.extract import extract_all

    catalog, store = _open(cfg)
    stats = extract_all(
        catalog, store, cfg, args.extractor, site_filter=args.site, force=args.force
    )
    print(json.dumps(stats, indent=2))
    return 0


def cmd_dedup(cfg: EvalConfig, args) -> int:
    catalog, _ = _open(cfg)
    for extractor in args.extractor:
        rows = catalog.extractions(extractor, with_bodies_only=True)
        clusterer = NearDupClusterer(
            cfg.dedup.hamming_threshold, cfg.dedup.min_tokens, cfg.dedup.min_exact_tokens
        )
        skipped = 0
        for row in rows:
            # Require real fingerprint data rather than defaulting NULLs to
            # ""/0 (which would silently merge or misplace malformed rows).
            if not row["body_key"] or not row["simhash"]:
                skipped += 1
                continue
            clusterer.add(
                BodyFingerprint(
                    item_id=str(row["id"]),
                    exact_key=row["body_key"],
                    simhash=int(row["simhash"], 16),
                    n_tokens=int(row["n_tokens"] or 0),
                )
            )
        mapping = {int(item): f"c{root}" for item, root in clusterer.clusters().items()}
        catalog.replace_clusters(extractor, mapping)
        stats = clusterer.stats()
        if skipped:
            stats["skipped_no_fingerprint"] = skipped
        print(f"[{extractor}] {json.dumps(stats)}")
    return 0


def cmd_draft_gold(cfg: EvalConfig, args) -> int:
    from evals.gold_tools import draft_gold

    catalog, store = _open(cfg)
    written = draft_gold(
        catalog, store, cfg, per_site=args.per_site,
        site_filter=args.site, from_engine=args.from_engine,
    )
    print(f"drafted {len(written)} gold files into {cfg.gold_dir}")
    for path in written:
        print(f"  {path.name}")
    if written:
        print("Review each file, fix title/body, then set review_status: approved")
    return 0


def cmd_validate_gold(cfg: EvalConfig, args) -> int:
    from evals.gold_tools import validate_gold

    result = validate_gold(cfg.gold_dir)
    print(json.dumps(result, indent=2))
    return 0 if not result["problems"] else 1


def cmd_label(cfg: EvalConfig, args) -> int:
    catalog, _ = _open(cfg)
    if args.list:
        manifest_labels = catalog.labels("page_type", "manifest")
        human_labels = catalog.labels("page_type", "human")
        classifier = catalog.labels("page_type", "classifier")
        print("unlabeled snapshots (no manifest/human page_type):")
        for snapshot in catalog.snapshots(fetched_only=True):
            sid = snapshot["id"]
            if sid in manifest_labels or sid in human_labels:
                continue
            print(f"  #{sid} [{snapshot['site_key']}] {snapshot['url']} "
                  f"@{snapshot['timestamp']} — classifier says: {classifier.get(sid, '?')}")
        return 0
    if args.snapshot_id is None or not args.page_type:
        print("usage: label --snapshot-id N --page-type TYPE  (or label --list)")
        return 2
    catalog.set_label(args.snapshot_id, "page_type", args.page_type, "human")
    print(f"labeled snapshot {args.snapshot_id} as {args.page_type} (source=human)")
    return 0


def cmd_score(cfg: EvalConfig, args) -> int:
    from evals.gold_tools import load_gold
    from evals.report import build_report, corpus_overview, provenance, write_reports
    from evals.score import dedup_yield, score_dedup, score_extractions, score_filtering

    catalog, store = _open(cfg)
    gold = load_gold(cfg.gold_dir, only_approved=not args.include_drafts)
    extraction = None
    if gold:
        extraction = score_extractions(catalog, store, cfg, gold, args.extractor)
        extraction["gold_mode"] = "proxy-draft" if args.include_drafts else "approved"
    else:
        logger.warning("score: no approved gold docs — skipping extraction scoring "
                       "(draft-gold, review, approve first)")
    filtering = score_filtering(catalog, cfg)
    extractors_with_clusters = [e for e in args.extractor if catalog.clusters(e)]
    dedup = {e: score_dedup(catalog, cfg, e) for e in extractors_with_clusters}
    yields = {e: dedup_yield(catalog, e) for e in extractors_with_clusters}
    report = build_report(
        corpus=corpus_overview(catalog, store),
        extraction=extraction, filtering=filtering,
        dedup=dedup or None, dedup_yield=yields or None,
        provenance=provenance(cfg),
    )
    json_path, md_path = write_reports(cfg, report)
    if extraction:
        for extractor, agg in extraction["by_extractor"].items():
            ci = agg["token_f1"]
            if ci.get("ci_low") is None:
                print(f"{extractor}: token F1 {ci['mean']:.3f} (n={ci['n']}, CI n/a)")
            else:
                print(f"{extractor}: token F1 {ci['mean']:.3f} [{ci['ci_low']:.3f},{ci['ci_high']:.3f}] (n={ci['n']})")
    detection = filtering["classifier"]["content_detection"]
    print(f"classifier content detection F1: {detection['f1']}")
    print(f"report: {md_path}")
    print(f"        {json_path}")
    return 0


def cmd_report(cfg: EvalConfig, args) -> int:
    from evals.report import build_report, corpus_overview, provenance, write_reports

    catalog, store = _open(cfg)
    report = build_report(corpus=corpus_overview(catalog, store), provenance=provenance(cfg))
    _, md_path = write_reports(cfg, report)
    print(f"report: {md_path}")
    return 0


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals.runner",
        description="Chrono Scraper extraction-quality eval harness",
    )
    parser.add_argument("--data-dir", help="corpus data dir (default: EVALS_DATA_DIR or evals/corpus_data)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="corpus, extractor and gold status")

    p_collect = sub.add_parser("collect", help="collect snapshots per the manifest")
    p_collect.add_argument("--site", help="only this manifest key")
    p_collect.add_argument("--min-sites", type=int, default=30,
                           help="fail (exit 1) if fewer sites yield data on a full run")

    p_lint = sub.add_parser("manifest-lint", help="check corpus balance across eras/types/categories")
    p_lint.add_argument("--min-per-era", type=int, default=4)
    p_lint.add_argument("--min-negatives", type=int, default=5)

    p_features = sub.add_parser("features", help="structural features + era/page-type classification")
    p_features.add_argument("--site")

    p_extract = sub.add_parser("extract", help="run extractors over fetched snapshots")
    p_extract.add_argument("--extractor", action="append", default=None,
                           help="repeatable; default: trafilatura")
    p_extract.add_argument("--site")
    p_extract.add_argument("--force", action="store_true", help="recompute existing extractions")

    p_dedup = sub.add_parser("dedup", help="near-dup clustering of extracted bodies")
    p_dedup.add_argument("--extractor", action="append", default=None)

    p_gold = sub.add_parser("draft-gold", help="draft gold annotations for review")
    p_gold.add_argument("--per-site", type=int, default=1)
    p_gold.add_argument("--site")
    p_gold.add_argument("--from-engine", dest="from_engine",
                        choices=["trafilatura", "readability", "newspaper", "pipeline"],
                        help="draft from ONE engine (use a non-primary one, e.g. readability, "
                             "so gold isn't authored by the system under test)")

    sub.add_parser("validate-gold", help="validate gold YAML files")

    p_label = sub.add_parser("label", help="set human page-type labels")
    p_label.add_argument("--snapshot-id", type=int)
    p_label.add_argument("--page-type", choices=PAGE_TYPES)
    p_label.add_argument("--list", action="store_true", help="list unlabeled snapshots")

    p_score = sub.add_parser("score", help="score extraction/filtering/dedup, write report")
    p_score.add_argument("--extractor", action="append", default=None)
    p_score.add_argument("--include-drafts", action="store_true",
                         help="score against draft gold too (biased — smoke tests only)")

    sub.add_parser("report", help="corpus-overview report only")
    return parser


_COMMANDS = {
    "status": cmd_status,
    "collect": cmd_collect,
    "manifest-lint": cmd_manifest_lint,
    "features": cmd_features,
    "extract": cmd_extract,
    "dedup": cmd_dedup,
    "draft-gold": cmd_draft_gold,
    "validate-gold": cmd_validate_gold,
    "label": cmd_label,
    "score": cmd_score,
    "report": cmd_report,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if getattr(args, "extractor", None) is None and args.command in ("extract", "dedup", "score"):
        args.extractor = ["trafilatura"]
    cfg = load_config(args.data_dir)
    return _COMMANDS[args.command](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
