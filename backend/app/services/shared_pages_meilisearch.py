"""
Enhanced Meilisearch service for shared pages architecture

Handles indexing and searching with multi-project support while maintaining
security boundaries and optimal search performance.

Per-project metadata (stars, review status, tags, category) is stored in the
index as ``<project_id>``-scoped values so filters are evaluated against the
projects being searched and never against other users' projects:

    starred_in:    [project_id, ...]
    review_keys:   ["<project_id>:<review_status>", ...]
    tag_keys:      ["<project_id>:<tag>", ...]
    category_keys: ["<project_id>:<category>", ...]
"""
import asyncio
import logging
import os
import re
import weakref
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import UUID

import meilisearch_python_async as meilisearch
from fastapi import Depends
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.models.shared_pages import Page, ProjectPage
from app.models.project import Project
from app.services.page_access_control import PageAccessControl, get_page_access_control

logger = logging.getLogger(__name__)

INDEX_NAME = "shared_pages"

DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 50
INDEX_BATCH_SIZE = 100
CROP_WORDS = 40

# Fields the search UI renders (frontend/src/routes/search/+page.svelte).
# project_ids is only used server-side (accessible_projects) and never returned.
SEARCH_RETRIEVE_FIELDS = ["id", "url", "title", "word_count", "capture_date", "project_ids"]

# Environment toggle for applying index settings from the API startup hook. Off
# by default so a (hot-)reloaded API never mutates a shared index unprompted;
# the explicit commands (`python -m app.scripts.reindex_shared_pages
# --apply-settings-only`) always apply.
CONFIGURE_ON_STARTUP_ENV = "MEILISEARCH_CONFIGURE_ON_STARTUP"

# Target index settings, in Meilisearch's camelCase REST format.
TARGET_INDEX_SETTINGS: Dict[str, Any] = {
    "rankingRules": [
        "words", "typo", "proximity", "attribute", "sort", "exactness",
        "quality_score:desc",
    ],
    "searchableAttributes": ["title", "description", "tags", "url", "author", "content"],
    # Exactly the attributes build_search_filter() filters on.
    "filterableAttributes": [
        "project_ids", "starred_in", "review_keys", "tag_keys", "category_keys",
        "quality_score", "word_count", "timestamp", "is_shared",
    ],
    # Sort options offered by the API (capture_date -> timestamp, scraped_at -> created_at).
    "sortableAttributes": ["timestamp", "created_at", "word_count", "quality_score"],
    "localizedAttributes": [{"attributePatterns": ["*"], "locales": ["eng", "nld"]}],
    "proximityPrecision": "byAttribute",
    "searchCutoffMs": 150,
}

# Settings where list order is irrelevant (compared as sets).
_UNORDERED_SETTINGS = {"filterableAttributes", "sortableAttributes"}


# --------------------------------------------------------------------------- #
# Shared client
# --------------------------------------------------------------------------- #

_clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, meilisearch.Client]" = weakref.WeakKeyDictionary()


def get_meili_client() -> meilisearch.Client:
    """Return the shared Meilisearch client for the running event loop (lazy).

    The underlying httpx client is bound to the loop it is first used on. The API
    process has a single loop, hence a single process-wide client. Celery tasks
    drive async code through short-lived (and per-thread) loops, so clients are
    kept per loop and dropped together with it.
    """
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None:
        client = meilisearch.Client(settings.MEILISEARCH_HOST, settings.MEILISEARCH_MASTER_KEY)
        _clients[loop] = client
        logger.debug("Created shared Meilisearch client for %s", settings.MEILISEARCH_HOST)
    return client


async def close_meili_client() -> None:
    """Close the running loop's shared client (API shutdown, end of scripts/tasks)."""
    client = _clients.pop(asyncio.get_running_loop(), None)
    if client is not None:
        try:
            await client.aclose()
        except Exception as e:
            logger.warning("Error closing Meilisearch client: %s", e)


# --------------------------------------------------------------------------- #
# Index settings
# --------------------------------------------------------------------------- #

def diff_index_settings(current: Dict[str, Any], target: Dict[str, Any]) -> Dict[str, Any]:
    """Return the subset of ``target`` that differs from ``current``."""
    changed: Dict[str, Any] = {}
    for key, wanted in target.items():
        have = current.get(key)
        if key in _UNORDERED_SETTINGS:
            same = set(have or []) == set(wanted)
        else:
            same = have == wanted
        if not same:
            changed[key] = wanted
    return changed


async def ensure_index_settings(
    index_name: str = INDEX_NAME,
    *,
    client: Optional[meilisearch.Client] = None,
    target: Optional[Dict[str, Any]] = None,
    apply: bool = True,
    wait: bool = False,
    wait_timeout_ms: int = 600_000,
) -> Dict[str, Any]:
    """Idempotently bring an index's settings in line with TARGET_INDEX_SETTINGS.

    Creates the index (primary key ``id``) when missing. Current settings are
    read first and only differing settings are sent, so a converged index costs
    one GET and triggers no re-indexing. With ``apply=False`` nothing is written;
    the drift is logged and returned.

    Returns the dict of settings that differed (empty when up to date).
    """
    client = client or get_meili_client()
    target = TARGET_INDEX_SETTINGS if target is None else target
    http = client.http_client

    response = await http.get(f"/indexes/{index_name}/settings")
    if response.status_code == 404:
        if not apply:
            logger.warning("Meilisearch index %s does not exist (settings not applied)", index_name)
            return dict(target)
        logger.info("Creating Meilisearch index %s", index_name)
        await client.create_index(index_name, primary_key="id")
        response = await http.get(f"/indexes/{index_name}/settings")
    response.raise_for_status()

    changed = diff_index_settings(response.json(), target)
    if not changed:
        logger.info("Meilisearch index %s settings already up to date", index_name)
        return {}

    if not apply:
        logger.warning(
            "Meilisearch index %s settings differ from target (%s); not applying",
            index_name, ", ".join(sorted(changed)),
        )
        return changed

    logger.info("Updating Meilisearch index %s settings: %s", index_name, ", ".join(sorted(changed)))
    response = await http.patch(f"/indexes/{index_name}/settings", json=changed)
    response.raise_for_status()
    if wait:
        from meilisearch_python_async.task import wait_for_task

        await wait_for_task(client.http_client, response.json()["taskUid"], timeout_in_ms=wait_timeout_ms)
    return changed


def configure_on_startup_enabled() -> bool:
    """Whether the API startup hook should apply (not just report) settings."""
    return os.environ.get(CONFIGURE_ON_STARTUP_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


# --------------------------------------------------------------------------- #
# Document building
# --------------------------------------------------------------------------- #

def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


class SharedPageDocument:
    """Document structure for Meilisearch with per-project metadata"""

    def __init__(self, page: Page, project_associations: Sequence[ProjectPage]):
        self.id = str(page.id)
        self.url = page.url or page.content_url or ""
        self.title = page.title or page.extracted_title or ""
        self.content = page.content or page.extracted_text or page.markdown_content or ""
        self.description = page.meta_description or ""
        self.author = page.author or ""
        self.language = page.language or ""
        self.timestamp = page.unix_timestamp
        self.capture_date = page.capture_date.isoformat() if page.capture_date else None
        self.created_at = page.created_at.isoformat() if page.created_at else None
        self.quality_score = float(page.quality_score) if page.quality_score else None
        self.word_count = page.word_count or 0
        self.character_count = page.character_count or 0

        self.project_ids = [pa.project_id for pa in project_associations]
        self.domain_ids = [pa.domain_id for pa in project_associations if pa.domain_id]

        # Per-project metadata: each value is scoped to the project that owns it.
        self.starred_in = [pa.project_id for pa in project_associations if pa.is_starred]
        self.review_keys = self._scoped_keys(project_associations, lambda pa: [pa.review_status])
        self.tag_keys = self._scoped_keys(project_associations, lambda pa: pa.tags or [])
        self.category_keys = self._scoped_keys(project_associations, lambda pa: [pa.page_category])

        # Union of tags, indexed only so tag text is searchable; never returned.
        self.tags = sorted({tag for pa in project_associations for tag in (pa.tags or [])})

        self.project_count = len(self.project_ids)
        self.is_shared = self.project_count > 1

    @staticmethod
    def _scoped_keys(associations: Sequence[ProjectPage], values_of) -> List[str]:
        keys: List[str] = []
        for pa in associations:
            for value in values_of(pa):
                value = _enum_value(value)
                if value is not None and value != "":
                    keys.append(f"{pa.project_id}:{value}")
        return sorted(set(keys))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Meilisearch indexing"""
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "description": self.description,
            "author": self.author,
            "language": self.language,
            "timestamp": self.timestamp,
            "capture_date": self.capture_date,
            "created_at": self.created_at,
            "quality_score": self.quality_score,
            "word_count": self.word_count,
            "character_count": self.character_count,
            "tags": self.tags,

            # Per-project fields
            "project_ids": self.project_ids,
            "domain_ids": self.domain_ids,
            "starred_in": self.starred_in,
            "review_keys": self.review_keys,
            "tag_keys": self.tag_keys,
            "category_keys": self.category_keys,

            # Sharing metadata
            "project_count": self.project_count,
            "is_shared": self.is_shared,
        }


# --------------------------------------------------------------------------- #
# Filter building
# --------------------------------------------------------------------------- #

def _quote(value: Any) -> str:
    """Quote a value for a Meilisearch filter expression."""
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _scoped_in(attribute: str, project_ids: Sequence[int], values: Iterable[Any]) -> str:
    keys = [_quote(f"{pid}:{value}") for pid in project_ids for value in values]
    return f"{attribute} IN [{', '.join(keys)}]"


def build_search_filter(project_ids: Sequence[int], filters: Optional[Dict[str, Any]] = None) -> str:
    """Build the Meilisearch filter for a search.

    ``project_ids`` is the already-authorised search scope (one project, or all
    of the user's projects). Per-project filters are translated against that
    scope so they never match metadata from projects outside it. Raises
    ValueError on malformed numeric filter values.
    """
    scope = [int(p) for p in project_ids]
    parts = [f"project_ids IN [{', '.join(map(str, scope))}]"]
    filters = filters or {}

    if filters.get("is_starred"):
        parts.append(f"starred_in IN [{', '.join(map(str, scope))}]")

    if filters.get("tags"):
        parts.append(_scoped_in("tag_keys", scope, filters["tags"]))

    if filters.get("review_statuses"):
        parts.append(_scoped_in("review_keys", scope, filters["review_statuses"]))

    if filters.get("categories"):
        parts.append(_scoped_in("category_keys", scope, filters["categories"]))

    if filters.get("min_quality_score"):
        parts.append(f"quality_score >= {float(filters['min_quality_score'])}")

    if filters.get("min_word_count"):
        parts.append(f"word_count >= {int(filters['min_word_count'])}")

    date_range = filters.get("date_range")
    if date_range:
        if date_range.get("start"):
            parts.append(f"timestamp >= {int(date_range['start'])}")
        if date_range.get("end"):
            parts.append(f"timestamp <= {int(date_range['end'])}")

    if filters.get("is_shared") is not None:
        shared = filters["is_shared"]
        if not isinstance(shared, bool):
            shared = str(shared).strip().lower() == "true"
        parts.append(f"is_shared = {str(shared).lower()}")

    return " AND ".join(parts)


_MARK_RE = re.compile(r"</?mark>")


def shape_hit(
    hit: Dict[str, Any],
    associations: Sequence[Dict[str, Any]],
    user_project_ids: Iterable[int],
) -> Dict[str, Any]:
    """Turn a raw index hit into the API hit.

    ``associations`` are the caller's own, in-scope project associations for the
    page (from Postgres), so per-project values never reflect other projects.
    ``project_ids`` from the index is reduced to the caller's projects and
    dropped from the hit.
    """
    user_set = {int(p) for p in user_project_ids}
    project_ids = hit.pop("project_ids", []) or []

    hit["user_has_access"] = True  # already restricted to the user's projects by the filter
    hit["accessible_projects"] = [p for p in project_ids if p in user_set]
    hit["project_associations"] = list(associations)

    hit["is_starred"] = any(a["is_starred"] for a in associations)
    hit["review_statuses"] = sorted({
        _enum_value(a["review_status"]) for a in associations if a["review_status"]
    })
    if associations:
        primary = associations[0]
        hit["tags"] = primary["tags"]
        hit["review_status"] = primary["review_status"]
        hit["page_category"] = primary["page_category"]
        hit["priority_level"] = primary["priority_level"]

    hit["original_url"] = hit.get("url", "")
    hit["wayback_url"] = hit.get("url", "")

    formatted = hit.get("_formatted") or {}
    snippet = formatted.get("content") or ""
    hit["content_preview"] = _MARK_RE.sub("", snippet)
    if snippet:
        hit["highlighted_snippet_html"] = snippet
    elif formatted.get("title"):
        hit["highlighted_snippet_html"] = formatted["title"]
    return hit


class SharedPagesMeilisearchService:
    """Enhanced Meilisearch service for shared pages architecture"""

    def __init__(
        self,
        db: AsyncSession,
        access_control: Optional[PageAccessControl] = None,
        index_name: str = INDEX_NAME,
    ):
        self.db = db
        self.access_control = access_control
        self.index_name = index_name

    @property
    def client(self) -> meilisearch.Client:
        return get_meili_client()

    @property
    def index(self):
        return self.client.index(self.index_name)

    # ------------------------------------------------------------------ #
    # Indexing
    # ------------------------------------------------------------------ #

    async def build_documents(self, page_ids: Sequence[UUID]) -> tuple[List[Dict[str, Any]], List[UUID]]:
        """Build index documents for pages from Postgres.

        Returns ``(documents, orphan_ids)``; orphans are the requested ids with
        no remaining project association (or no page row at all).
        """
        ids = [UUID(str(pid)) for pid in page_ids]
        if not ids:
            return [], []

        pages = (await self.db.execute(select(Page).where(Page.id.in_(ids)))).scalars().all()
        associations = (
            await self.db.execute(select(ProjectPage).where(ProjectPage.page_id.in_(ids)))
        ).scalars().all()

        by_page: Dict[UUID, List[ProjectPage]] = {}
        for assoc in associations:
            by_page.setdefault(assoc.page_id, []).append(assoc)

        documents: List[Dict[str, Any]] = []
        indexed_ids = set()
        for page in pages:
            page_assocs = by_page.get(page.id)
            if not page_assocs:
                continue
            documents.append(SharedPageDocument(page, page_assocs).to_dict())
            indexed_ids.add(page.id)

        return documents, [pid for pid in ids if pid not in indexed_ids]

    async def reindex_pages(self, page_ids: Sequence[UUID]) -> Dict[str, Any]:
        """Re-sync pages with the index from Postgres.

        Single entry point for every ProjectPage write (link, unlink, star,
        review, tags, notes) and for bulk indexing: pages that still belong to a
        project are (re)written, pages with no remaining project are deleted.
        """
        requested = len(page_ids)
        if not requested:
            return {"indexed": 0, "deleted": 0, "failed": 0, "total_requested": 0}

        try:
            documents, orphan_ids = await self.build_documents(page_ids)

            for start in range(0, len(documents), INDEX_BATCH_SIZE):
                await self.index.add_documents(documents[start:start + INDEX_BATCH_SIZE])
            if orphan_ids:
                await self.index.delete_documents([str(pid) for pid in orphan_ids])

            logger.info(
                "Reindexed shared pages: requested=%d indexed=%d deleted=%d",
                requested, len(documents), len(orphan_ids),
            )
            return {
                "indexed": len(documents),
                "deleted": len(orphan_ids),
                "failed": 0,
                "total_requested": requested,
            }
        except Exception as e:
            logger.error("Reindex of %d shared pages failed: %s", requested, e)
            return {"indexed": 0, "deleted": 0, "failed": requested, "total_requested": requested, "error": str(e)}

    async def bulk_index_pages(self, page_ids: List[UUID]) -> Dict[str, Any]:
        """Bulk index multiple pages (kept for the scraping tasks that call it)."""
        return await self.reindex_pages(page_ids)

    async def remove_project_from_all_pages(self, project_id: int) -> None:
        """Re-sync every indexed page of a project after the project is deleted."""
        try:
            page_ids: List[UUID] = []
            offset = 0
            while True:
                batch = await self.index.get_documents(
                    offset=offset, limit=1000, fields=["id"], filter=f"project_ids = {int(project_id)}"
                )
                if not batch.results:
                    break
                page_ids.extend(UUID(doc["id"]) for doc in batch.results)
                offset += len(batch.results)
            logger.info("Project %s deleted: re-syncing %d indexed pages", project_id, len(page_ids))
            for start in range(0, len(page_ids), INDEX_BATCH_SIZE):
                await self.reindex_pages(page_ids[start:start + INDEX_BATCH_SIZE])
        except Exception as e:
            logger.error("Failed to remove project %s from search index: %s", project_id, e)

    # ------------------------------------------------------------------ #
    # Searching
    # ------------------------------------------------------------------ #

    async def search_user_pages(
        self,
        user_id: int,
        query: str,
        project_id: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        offset: int = 0,
        sort: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Search pages with security filtering and project scoping"""
        limit = max(1, min(int(limit), MAX_SEARCH_LIMIT))
        offset = max(0, int(offset))

        try:
            user_project_ids = await self._get_user_project_ids(user_id)
            if not user_project_ids:
                return {
                    "hits": [],
                    "query": query,
                    "limit": limit,
                    "offset": offset,
                    "estimatedTotalHits": 0,
                    "processingTimeMs": 0
                }

            # Search a single project when requested and owned, else all owned projects.
            scope = [project_id] if project_id in user_project_ids else user_project_ids
            search_options: Dict[str, Any] = {
                "filter": build_search_filter(scope, filters),
                "limit": limit,
                "offset": offset,
                "attributes_to_retrieve": SEARCH_RETRIEVE_FIELDS,
                "attributes_to_highlight": ["title", "content"],
                "highlight_pre_tag": "<mark>",
                "highlight_post_tag": "</mark>",
                "attributes_to_crop": [f"content:{CROP_WORDS}"],
                "crop_marker": "…",
            }
            if sort:
                search_options["sort"] = sort

            results = await self.index.search(query, **search_options)

            associations = await self._load_associations(results.hits, scope)
            hits = [
                shape_hit(hit, associations.get(hit["id"], []), user_project_ids)
                for hit in results.hits
            ]
            logger.info(
                "Search user=%s projects=%d q_len=%d hits=%d total=%s took=%sms",
                user_id, len(scope), len(query or ""), len(hits),
                results.estimated_total_hits, results.processing_time_ms,
            )
            return {
                "hits": hits,
                "query": results.query,
                "processingTimeMs": results.processing_time_ms,
                "limit": results.limit,
                "offset": results.offset,
                "estimatedTotalHits": results.estimated_total_hits,
                "totalHits": results.estimated_total_hits,
                "total": len(hits)
            }

        except Exception as e:
            logger.error(f"Search failed for user {user_id}: {e}")
            raise

    async def get_search_statistics(self, user_id: int) -> Dict[str, Any]:
        """Get search statistics for user's accessible pages"""
        try:
            project_ids = await self._get_user_project_ids(user_id)
            if not project_ids:
                return {"total_pages": 0, "by_project": {}}

            filter_str = f"project_ids IN [{', '.join(map(str, project_ids))}]"

            # Get overall statistics
            stats_search = await self.index.search(
                "",
                filter=filter_str,
                limit=0,  # We only want the count
                facets=["project_ids", "is_shared"]
            )

            facets = dict(getattr(stats_search, 'facet_distribution', None) or {})
            if "project_ids" in facets:
                owned = {str(p) for p in project_ids}
                facets["project_ids"] = {k: v for k, v in facets["project_ids"].items() if k in owned}

            return {
                "total_pages": stats_search.estimated_total_hits,
                "facet_distribution": facets,
                "processing_time_ms": stats_search.processing_time_ms
            }

        except Exception as e:
            logger.error(f"Failed to get search statistics: {e}")
            return {"error": str(e)}

    async def _load_associations(
        self, hits: Sequence[Dict[str, Any]], scope: Sequence[int]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """The caller's in-scope ProjectPage rows for the hit pages, keyed by page id."""
        page_ids: List[UUID] = []
        for hit in hits:
            try:
                page_ids.append(UUID(hit["id"]))
            except (ValueError, TypeError):
                logger.warning("Invalid UUID in search result: %s", hit.get("id"))
        if not page_ids:
            return {}

        stmt = select(ProjectPage, Project.name).join(
            Project, ProjectPage.project_id == Project.id
        ).where(
            ProjectPage.page_id.in_(page_ids),
            ProjectPage.project_id.in_(list(scope)),
        )
        by_page: Dict[str, List[Dict[str, Any]]] = {}
        for assoc, project_name in (await self.db.execute(stmt)).all():
            by_page.setdefault(str(assoc.page_id), []).append({
                "project_id": assoc.project_id,
                "project_name": project_name,
                "tags": assoc.tags or [],
                "review_status": assoc.review_status,
                "page_category": assoc.page_category,
                "priority_level": assoc.priority_level,
                "is_starred": assoc.is_starred or False,
                "reviewed_at": assoc.reviewed_at.isoformat() if assoc.reviewed_at else None,
                "notes": assoc.notes,
            })
        return by_page

    async def _get_user_project_ids(self, user_id: int) -> List[int]:
        """IDs of the projects the user owns"""
        result = await self.db.execute(select(Project.id).where(Project.user_id == user_id))
        return list(result.scalars().all())


async def get_shared_pages_meilisearch_service(
    db: AsyncSession = Depends(get_db),
    access_control: Optional[PageAccessControl] = Depends(get_page_access_control)
) -> SharedPagesMeilisearchService:
    """Dependency injection for shared pages Meilisearch service"""
    return SharedPagesMeilisearchService(db, access_control)
