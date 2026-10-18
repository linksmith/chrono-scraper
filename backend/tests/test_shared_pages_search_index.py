"""
Unit tests for the shared pages search index: filter builder, per-project
document fields, hit shaping, index settings diffing and reindexing.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.shared_pages import PageCategory, PageReviewStatus
from app.services import shared_pages_meilisearch as svc
from app.services.shared_pages_meilisearch import (
    TARGET_INDEX_SETTINGS,
    SharedPageDocument,
    SharedPagesMeilisearchService,
    build_search_filter,
    diff_index_settings,
    ensure_index_settings,
    shape_hit,
)


def make_page(**overrides):
    page = dict(
        id=uuid4(), url="https://example.org/a", content_url=None, title="Title",
        extracted_title=None, content="body text", extracted_text=None,
        markdown_content=None, meta_description="desc", author="me", language="en",
        unix_timestamp=20200101000000, capture_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc), quality_score=2,
        word_count=10, character_count=50,
    )
    page.update(overrides)
    return SimpleNamespace(**page)


def make_assoc(project_id, **overrides):
    assoc = dict(
        project_id=project_id, domain_id=None, is_starred=False,
        review_status=PageReviewStatus.PENDING, page_category=None, tags=[],
    )
    assoc.update(overrides)
    return SimpleNamespace(**assoc)


class TestBuildSearchFilter:
    def test_scope_only(self):
        assert build_search_filter([1, 2]) == "project_ids IN [1, 2]"

    def test_starred_is_scoped_to_searched_projects(self):
        f = build_search_filter([3], {"is_starred": True})
        assert f == "project_ids IN [3] AND starred_in IN [3]"

    def test_review_statuses_and_tags_are_per_project(self):
        f = build_search_filter([1, 2], {"review_statuses": ["relevant"], "tags": ["a b"]})
        assert 'review_keys IN ["1:relevant", "2:relevant"]' in f
        assert 'tag_keys IN ["1:a b", "2:a b"]' in f

    def test_categories_are_per_project(self):
        f = build_search_filter([1], {"categories": ["news"]})
        assert 'category_keys IN ["1:news"]' in f

    def test_values_cannot_break_out_of_the_filter(self):
        f = build_search_filter([1], {"tags": ['x" OR project_ids = 99 OR tag_keys = "y']})
        # The whole payload stays inside one quoted string; nothing is appended to the scope.
        assert f.startswith("project_ids IN [1] AND tag_keys IN [")
        assert f.count('"') - f.count('\\"') == 2

    def test_numeric_filters(self):
        f = build_search_filter(
            [1], {"min_word_count": "100", "min_quality_score": 2.5, "date_range": {"start": 2020, "end": 2021}}
        )
        assert "word_count >= 100" in f
        assert "quality_score >= 2.5" in f
        assert "timestamp >= 2020" in f and "timestamp <= 2021" in f

    @pytest.mark.parametrize("filters", [
        {"min_word_count": "1 OR project_ids = 5"},
        {"min_quality_score": "abc"},
        {"date_range": {"start": "1; DROP"}},
    ])
    def test_malformed_numbers_are_rejected(self, filters):
        with pytest.raises(ValueError):
            build_search_filter([1], filters)

    def test_is_shared(self):
        assert build_search_filter([1], {"is_shared": False}).endswith("is_shared = false")
        assert build_search_filter([1], {"is_shared": "true"}).endswith("is_shared = true")


class TestSharedPageDocument:
    def test_per_project_fields_do_not_mix_projects(self):
        doc = SharedPageDocument(make_page(), [
            make_assoc(1, is_starred=True, review_status=PageReviewStatus.RELEVANT,
                       tags=["osint"], page_category=PageCategory.NEWS),
            make_assoc(2, is_starred=False, review_status="irrelevant", tags=["other"]),
        ]).to_dict()

        assert doc["project_ids"] == [1, 2]
        assert doc["starred_in"] == [1]
        assert doc["review_keys"] == ["1:relevant", "2:irrelevant"]
        assert doc["tag_keys"] == ["1:osint", "2:other"]
        assert doc["category_keys"] == ["1:news"]
        assert doc["project_count"] == 2 and doc["is_shared"] is True

    def test_legacy_global_metadata_fields_are_gone(self):
        doc = SharedPageDocument(make_page(), [make_assoc(1)]).to_dict()
        for legacy in ("is_starred", "review_statuses", "categories", "priority_levels"):
            assert legacy not in doc

    def test_tags_union_is_search_only_and_unscoped_keys_are_prefixed(self):
        doc = SharedPageDocument(make_page(), [make_assoc(1, tags=["a"]), make_assoc(2, tags=["a", "b"])]).to_dict()
        assert doc["tags"] == ["a", "b"]
        assert doc["tag_keys"] == ["1:a", "2:a", "2:b"]

    def test_content_fallback_chain_and_missing_values(self):
        page = make_page(content=None, extracted_text=None, markdown_content="md", created_at=None, quality_score=None)
        doc = SharedPageDocument(page, [make_assoc(1)]).to_dict()
        assert doc["content"] == "md"
        assert doc["created_at"] is None and doc["quality_score"] is None


class TestShapeHit:
    def assoc(self, project_id, **kw):
        base = {
            "project_id": project_id, "project_name": f"p{project_id}", "tags": [],
            "review_status": "pending", "page_category": None, "priority_level": "medium",
            "is_starred": False, "reviewed_at": None, "notes": None,
        }
        base.update(kw)
        return base

    def test_strips_foreign_project_ids_and_builds_preview_from_formatted(self):
        hit = {
            "id": "x", "url": "https://e.org", "title": "T", "project_ids": [1, 99],
            "_formatted": {"title": "<mark>T</mark>", "content": "...a <mark>match</mark> here..."},
        }
        out = shape_hit(hit, [self.assoc(1, is_starred=True, review_status="relevant", tags=["t"])], [1, 2])

        assert "project_ids" not in out
        assert out["accessible_projects"] == [1]
        assert out["is_starred"] is True
        assert out["review_statuses"] == ["relevant"]
        assert out["tags"] == ["t"]
        assert out["content_preview"] == "...a match here..."
        assert "content" not in out

    def test_no_associations(self):
        out = shape_hit({"id": "x", "project_ids": [1], "_formatted": {}}, [], [1])
        assert out["is_starred"] is False
        assert out["review_statuses"] == []
        assert out["content_preview"] == ""


def _response(status=200, payload=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload if payload is not None else {}
    resp.raise_for_status = MagicMock()
    return resp


def _client(get_responses):
    client = MagicMock()
    client.http_client.get = AsyncMock(side_effect=get_responses)
    client.http_client.patch = AsyncMock(return_value=_response(202, {"taskUid": 7}))
    client.create_index = AsyncMock()
    return client


class TestIndexSettings:
    def test_diff_ignores_order_for_filterable_and_sortable_only(self):
        current = dict(TARGET_INDEX_SETTINGS)
        current["filterableAttributes"] = list(reversed(TARGET_INDEX_SETTINGS["filterableAttributes"]))
        current["sortableAttributes"] = list(reversed(TARGET_INDEX_SETTINGS["sortableAttributes"]))
        assert diff_index_settings(current, TARGET_INDEX_SETTINGS) == {}

        current["rankingRules"] = list(reversed(TARGET_INDEX_SETTINGS["rankingRules"]))
        assert set(diff_index_settings(current, TARGET_INDEX_SETTINGS)) == {"rankingRules"}

    def test_diff_treats_missing_settings_as_changed(self):
        assert set(diff_index_settings({}, TARGET_INDEX_SETTINGS)) == set(TARGET_INDEX_SETTINGS)

    def test_target_matches_what_the_code_filters_and_sorts_on(self):
        filterable = set(TARGET_INDEX_SETTINGS["filterableAttributes"])
        assert {"project_ids", "starred_in", "review_keys", "tag_keys", "category_keys"} <= filterable
        assert TARGET_INDEX_SETTINGS["rankingRules"][-1] == "quality_score:desc"
        assert "word_count:desc" not in TARGET_INDEX_SETTINGS["rankingRules"]
        assert TARGET_INDEX_SETTINGS["searchCutoffMs"] == 150

    @pytest.mark.asyncio
    async def test_no_write_when_up_to_date(self):
        client = _client([_response(200, dict(TARGET_INDEX_SETTINGS))])
        assert await ensure_index_settings("idx", client=client) == {}
        client.http_client.patch.assert_not_called()

    @pytest.mark.asyncio
    async def test_only_changed_settings_are_sent(self):
        current = dict(TARGET_INDEX_SETTINGS, searchCutoffMs=None, proximityPrecision="byWord")
        client = _client([_response(200, current)])

        changed = await ensure_index_settings("idx", client=client)

        assert changed == {"searchCutoffMs": 150, "proximityPrecision": "byAttribute"}
        client.http_client.patch.assert_awaited_once_with("/indexes/idx/settings", json=changed)

    @pytest.mark.asyncio
    async def test_apply_false_reports_drift_without_writing(self):
        client = _client([_response(200, {})])
        changed = await ensure_index_settings("idx", client=client, apply=False)
        assert set(changed) == set(TARGET_INDEX_SETTINGS)
        client.http_client.patch.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_index_is_created_then_configured(self):
        client = _client([_response(404), _response(200, {})])
        await ensure_index_settings("idx", client=client)
        client.create_index.assert_awaited_once_with("idx", primary_key="id")
        client.http_client.patch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_index_not_created_when_not_applying(self):
        client = _client([_response(404)])
        await ensure_index_settings("idx", client=client, apply=False)
        client.create_index.assert_not_called()

    @pytest.mark.parametrize("value,expected", [("true", True), ("1", True), ("", False), ("no", False)])
    def test_startup_toggle(self, monkeypatch, value, expected):
        monkeypatch.setenv(svc.CONFIGURE_ON_STARTUP_ENV, value)
        assert svc.configure_on_startup_enabled() is expected


class TestSharedClient:
    @pytest.mark.asyncio
    async def test_one_client_per_loop(self):
        with patch.object(svc.meilisearch, "Client") as client_cls:
            first = svc.get_meili_client()
            second = svc.get_meili_client()
            assert first is second
            client_cls.assert_called_once_with(svc.settings.MEILISEARCH_HOST, svc.settings.MEILISEARCH_MASTER_KEY)
            client_cls.return_value.aclose = AsyncMock()
            await svc.close_meili_client()
            client_cls.return_value.aclose.assert_awaited_once()
            svc.get_meili_client()
            assert client_cls.call_count == 2
            await svc.close_meili_client()


class TestReindexPages:
    def make_service(self, documents, orphans):
        service = SharedPagesMeilisearchService(db=MagicMock())
        service.build_documents = AsyncMock(return_value=(documents, orphans))
        index = MagicMock()
        index.add_documents = AsyncMock()
        index.delete_documents = AsyncMock()
        client = MagicMock()
        client.index.return_value = index
        return service, index, client

    @pytest.mark.asyncio
    async def test_writes_documents_and_deletes_orphans(self):
        orphan = uuid4()
        service, index, client = self.make_service([{"id": "a"}, {"id": "b"}], [orphan])
        with patch.object(svc, "get_meili_client", return_value=client):
            result = await service.reindex_pages([uuid4(), uuid4(), orphan])

        index.add_documents.assert_awaited_once_with([{"id": "a"}, {"id": "b"}])
        index.delete_documents.assert_awaited_once_with([str(orphan)])
        assert result["indexed"] == 2 and result["deleted"] == 1 and result["failed"] == 0

    @pytest.mark.asyncio
    async def test_no_ids_is_a_noop(self):
        service, index, client = self.make_service([], [])
        with patch.object(svc, "get_meili_client", return_value=client):
            assert (await service.reindex_pages([]))["total_requested"] == 0
        service.build_documents.assert_not_called()

    @pytest.mark.asyncio
    async def test_failure_is_reported_not_raised(self):
        service, index, client = self.make_service([{"id": "a"}], [])
        index.add_documents.side_effect = RuntimeError("meili down")
        with patch.object(svc, "get_meili_client", return_value=client):
            result = await service.reindex_pages([uuid4()])
        assert result["failed"] == 1 and "meili down" in result["error"]

    @pytest.mark.asyncio
    async def test_bulk_index_pages_delegates(self):
        service, _, _ = self.make_service([], [])
        service.reindex_pages = AsyncMock(return_value={"indexed": 3})
        ids = [uuid4()]
        assert await service.bulk_index_pages(ids) == {"indexed": 3}
        service.reindex_pages.assert_awaited_once_with(ids)
