#!/usr/bin/env python3
"""
One-off cleanup of legacy scrape_pages written before fetch failures were recorded honestly.

    python -m app.scripts.reclassify_legacy_skips --help

Old code stored fetch failures (connection errors, archive 429 pages, blank browser pages)
as ``status=skipped, error_type=insufficient_content``. This converts those rows into
retryable ``failed`` rows (typed error_type, ``next_retry_at`` staggered so the beat task
drains them at SCRAPE_RETRY_BATCH per run). Rows that are genuinely thin pages stay skipped.

Default is a DRY RUN that only prints counts. Pass --no-dry-run to apply. Nothing is
deleted and no text is touched; the original message is kept in error_message.

The orphan-pending report is always read-only: it counts ``pending`` rows whose session
is finished/failed/cancelled (nothing will ever pick them up) and stale ``in_progress`` rows.
"""
import argparse
import logging
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import create_engine, text

from app.core.config import settings

logger = logging.getLogger("reclassify_legacy_skips")

# (error_type, retryable). All retryable except a clean HTTP error status from the archive.
_RULES = (
    (re.compile(r"extraction_failed_connection_error|connection_error|All connection attempts failed", re.I),
     "connection_error", True),
    (re.compile(r"429|too many requests|rate.?limit|blocked/failed|all rotating .* exits", re.I),
     "rate_limited", True),
    (re.compile(r"\b(404|410)\b|not found|gone", re.I), "http_error", False),
    (re.compile(r"extraction_failed_http_error", re.I), "http_error", True),
    (re.compile(r"extraction_failed_", re.I), "fetch_error", True),
)
_BLANK_BROWSER_TITLES = {"new tab", "about:blank", "extraction failed"}


def classify_legacy_skip(error_message: Optional[str], filter_details: Optional[Dict[str, Any]]) -> Optional[Tuple[str, bool]]:
    """
    (new error_type, retryable) when a legacy skipped row was really a fetch failure, else None.

    Only the fetch-failure markers the old pipeline produced are matched: the extraction_method
    (``extraction_failed_*``), an archive 429 page, or a blank browser page with no text.
    """
    details = filter_details or {}
    method = str(details.get("extraction_method") or "")
    title = str(details.get("title") or "").strip().lower()
    preview = str(details.get("text_preview") or "").strip()
    haystack = " ".join([method, preview[:300], str(error_message or "")[:300]])

    if method.startswith("extraction_failed_"):
        for pattern, error_type, retryable in _RULES:
            if pattern.search(haystack):
                return error_type, retryable
        return "fetch_error", True
    if title.startswith("429") or preview.lower().startswith("429 too many requests"):
        return "rate_limited", True
    if title in _BLANK_BROWSER_TITLES and not preview:
        return "block_page", True
    return None


def _orphan_report(conn) -> None:
    stale = settings.SCRAPE_STALE_IN_PROGRESS_MINUTES
    print("\nOrphan report (read-only)")
    rows = conn.execute(text("""
        SELECT COALESCE(s.status, 'NO SESSION') AS session_status, count(*) AS n
        FROM scrape_pages p LEFT JOIN scrape_sessions s ON s.id = p.scrape_session_id
        WHERE p.status = 'pending'
        GROUP BY 1 ORDER BY 2 DESC
    """)).all()
    total = sum(n for _, n in rows)
    print(f"  pending scrape_pages: {total}")
    for session_status, n in rows:
        note = "" if session_status == "running" else "  <- nothing will pick these up"
        print(f"    session {session_status:<12} {n}{note}")
    in_progress = conn.execute(text("""
        SELECT count(*) FILTER (WHERE last_attempt_at IS NULL OR last_attempt_at < now() - make_interval(mins => :m)),
               count(*)
        FROM scrape_pages WHERE status = 'in_progress'
    """), {"m": stale}).one()
    print(f"  in_progress scrape_pages: {in_progress[1]} ({in_progress[0]} older than {stale} min; "
          f"the reaper beat task resets these)")


def run(dry_run: bool, batch_size: int, limit: Optional[int]) -> int:
    engine = create_engine(settings.DATABASE_URL)
    counts: Counter = Counter()
    kept = 0
    scheduled = 0
    now = datetime.now(timezone.utc)
    per_slot = max(1, settings.SCRAPE_RETRY_BATCH)

    with engine.connect() as conn:
        last_id = 0
        examined = 0
        while True:
            rows = conn.execute(text("""
                SELECT id, error_message, filter_details
                FROM scrape_pages
                WHERE status = 'skipped' AND error_type = 'insufficient_content' AND id > :last
                ORDER BY id LIMIT :n
            """), {"last": last_id, "n": batch_size}).all()
            if not rows:
                break
            updates = []
            for row_id, message, details in rows:
                last_id = row_id
                examined += 1
                verdict = classify_legacy_skip(message, details)
                if verdict is None:
                    kept += 1
                    continue
                error_type, retryable = verdict
                counts[(error_type, retryable)] += 1
                retry_at = now + timedelta(minutes=10 * (scheduled // per_slot)) if retryable else None
                scheduled += 1 if retryable else 0
                updates.append({
                    "id": row_id, "error_type": error_type, "retry_at": retry_at,
                    "message": f"Reclassified from skipped/insufficient_content: {(message or '')[:300]}",
                })
            if updates and not dry_run:
                conn.execute(text("""
                    UPDATE scrape_pages
                    SET status = 'failed', error_type = :error_type, error_message = :message,
                        next_retry_at = :retry_at, updated_at = now()
                    WHERE id = :id AND status = 'skipped' AND error_type = 'insufficient_content'
                """), updates)
                conn.commit()
            if limit and examined >= limit:
                break

        print(f"{'DRY RUN - nothing written' if dry_run else 'APPLIED'}: examined {examined} legacy "
              f"skipped/insufficient_content rows")
        for (error_type, retryable), n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  -> failed/{error_type:<17} retryable={str(retryable):<5} {n}")
        print(f"  kept as skipped (genuinely thin pages): {kept}")
        if scheduled:
            hours = (scheduled // per_slot) * 10 / 60
            print(f"  retries staggered {per_slot} per 10 min: fully drained in ~{hours:.1f} h of beat runs")

        _orphan_report(conn)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True,
                        help="count only (default); use --no-dry-run to write")
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--limit", type=int, default=None, help="stop after examining this many rows")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return run(args.dry_run, args.batch_size, args.limit)


if __name__ == "__main__":
    sys.exit(main())
