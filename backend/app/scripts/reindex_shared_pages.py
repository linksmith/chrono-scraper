#!/usr/bin/env python3
"""
Rebuild the ``shared_pages`` Meilisearch index from Postgres and swap it in.

    python -m app.scripts.reindex_shared_pages --help

Modes
    --apply-settings-only   Only apply TARGET_INDEX_SETTINGS to the live index
                            (idempotent; waits for the settings task).
    --dry-run               Report what a rebuild would do; writes nothing.
    (default)               Build ``shared_pages_rebuild_<utc timestamp>`` from
                            scratch with the target settings, verify its document
                            count against Postgres, atomically swap it with
                            ``shared_pages`` (Meilisearch swap-indexes), then
                            delete the old data (unless --keep-old-index).

    --delete-legacy-indexes Also delete empty legacy ``project_<N>`` indexes.
                            Only indexes with zero documents are ever removed.

Pages written while a rebuild is running are not guaranteed to be in the new
index; run it while scraping is idle, or follow up with another run.
"""
import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import distinct, func, select

from app.core.database import AsyncSessionLocal
from app.models.shared_pages import ProjectPage
from app.services.shared_pages_meilisearch import (
    INDEX_NAME,
    TARGET_INDEX_SETTINGS,
    SharedPagesMeilisearchService,
    close_meili_client,
    ensure_index_settings,
    get_meili_client,
)

logger = logging.getLogger("reindex_shared_pages")

LEGACY_INDEX_RE = re.compile(r"^project_\d+$")
TASK_TIMEOUT_MS = 30 * 60 * 1000


async def _wait(client, task_uid: int, what: str) -> None:
    from meilisearch_python_async.task import wait_for_task

    result = await wait_for_task(client, task_uid, timeout_in_ms=TASK_TIMEOUT_MS, interval_in_ms=200)
    if result.status != "succeeded":
        raise RuntimeError(f"Meilisearch task {task_uid} ({what}) {result.status}: {result.error}")


async def _count_indexable_pages() -> int:
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(func.count(distinct(ProjectPage.page_id))))).scalar_one()


async def _next_page_ids(after: Optional[UUID], batch_size: int) -> List[UUID]:
    stmt = select(distinct(ProjectPage.page_id)).order_by(ProjectPage.page_id).limit(batch_size)
    if after is not None:
        stmt = stmt.where(ProjectPage.page_id > after)
    async with AsyncSessionLocal() as db:
        return list((await db.execute(stmt)).scalars().all())


async def _legacy_indexes(client) -> List[str]:
    """Names of legacy per-project indexes that are empty (safe to delete)."""
    stats = await client.get_all_stats()
    return sorted(
        uid for uid, idx in stats.indexes.items()
        if LEGACY_INDEX_RE.match(uid) and idx.number_of_documents == 0
    )


async def _delete_legacy_indexes(client, delete: bool) -> None:
    empty = await _legacy_indexes(client)
    if not delete:
        logger.info("%d empty legacy project_N indexes found (pass --delete-legacy-indexes to remove)", len(empty))
        return
    for uid in empty:
        await client.delete_index_if_exists(uid)
        logger.info("Deleted empty legacy index %s", uid)


async def _rebuild(batch_size: int, keep_old: bool) -> None:
    client = get_meili_client()
    expected = await _count_indexable_pages()
    new_name = "shared_pages_rebuild_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    logger.info("Rebuilding %s into %s: %d pages to index", INDEX_NAME, new_name, expected)

    await ensure_index_settings(new_name, client=client, wait=True)  # creates the index
    new_index = client.index(new_name)

    indexed = 0
    last_id: Optional[UUID] = None
    task_uids: List[int] = []
    batches = 0
    while True:
        page_ids = await _next_page_ids(last_id, batch_size)
        if not page_ids:
            break
        last_id = page_ids[-1]
        async with AsyncSessionLocal() as db:
            documents, _ = await SharedPagesMeilisearchService(db, index_name=new_name).build_documents(page_ids)
        if documents:
            task_uids.append((await new_index.add_documents(documents)).task_uid)
            indexed += len(documents)
        batches += 1
        if batches % 10 == 0:
            logger.info("Queued %d/%d documents", indexed, expected)

    for uid in task_uids:
        await _wait(client, uid, f"add documents to {new_name}")

    actual = (await new_index.get_stats()).number_of_documents
    if actual != expected:
        raise RuntimeError(
            f"Rebuilt index {new_name} has {actual} documents, expected {expected}; "
            f"NOT swapped (index left in place for inspection)"
        )

    # swap-indexes needs both indexes to exist
    await client.get_or_create_index(INDEX_NAME, primary_key="id")
    swap = await client.swap_indexes([(INDEX_NAME, new_name)])
    await _wait(client, swap.task_uid, "swap-indexes")
    logger.info("Swapped %s <-> %s (%d documents live)", INDEX_NAME, new_name, actual)

    if keep_old:
        logger.info("Previous data kept in index %s", new_name)
    else:
        await client.delete_index_if_exists(new_name)
        logger.info("Deleted previous index data (%s)", new_name)


async def _run(args: argparse.Namespace) -> None:
    client = get_meili_client()
    try:
        if args.apply_settings_only:
            changed = await ensure_index_settings(wait=True)
            logger.info("Applied settings: %s", sorted(changed) or "none (already up to date)")
        elif args.dry_run:
            drift = await ensure_index_settings(apply=False)
            logger.info(
                "[dry-run] %d pages would be indexed; live settings drift: %s",
                await _count_indexable_pages(), sorted(drift) or "none",
            )
            logger.info("[dry-run] target settings: %s", sorted(TARGET_INDEX_SETTINGS))
        else:
            await _rebuild(args.batch_size, args.keep_old_index)

        if args.dry_run:
            logger.info("[dry-run] empty legacy indexes: %s", await _legacy_indexes(client))
        else:
            await _delete_legacy_indexes(client, args.delete_legacy_indexes)
    finally:
        await close_meili_client()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply-settings-only", action="store_true", help="only apply index settings to the live index")
    parser.add_argument("--dry-run", action="store_true", help="report the plan, write nothing")
    parser.add_argument("--batch-size", type=int, default=100, help="pages per Postgres read / Meilisearch add (default 100)")
    parser.add_argument("--keep-old-index", action="store_true", help="keep the pre-swap data in its own index")
    parser.add_argument("--delete-legacy-indexes", action="store_true", help="delete empty legacy project_<N> indexes")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(_run(args))
    except Exception as e:
        logger.error("Reindex failed: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
