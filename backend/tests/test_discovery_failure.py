"""
A CDX discovery failure must never look like a domain without captures: the
domain/session end up failed with a clear message, and a retryable failure is
re-run later (bounded) instead of completing silently with zero pages.
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.models.project import Domain, DomainStatus, Project, ScrapeSession, ScrapeSessionStatus
from app.services.archive_fetch_errors import ArchiveDiscoveryFailed
from app.services.archive_service_router import AllSourcesFailedException
from app.services.enhanced_archive_router import EnhancedArchiveServiceRouter, EnhancedRoutingConfig
from app.services.wayback_machine import CDXDeferred, CDXHTTPError, CDXRateLimited
from app.tasks import firecrawl_scraping as fs


def all_failed(cause: BaseException) -> AllSourcesFailedException:
    try:
        raise AllSourcesFailedException("All 1 archive sources failed for domain example.nl", []) from cause
    except AllSourcesFailedException as exc:
        return exc


class TestDescribeDiscoveryFailure:
    def test_rate_limited_is_retryable_with_the_pause_length(self):
        failure = fs.describe_discovery_failure(
            all_failed(CDXRateLimited("Rate limited: 429", status_code=429, retry_after=600.0)), "example.nl"
        )
        assert isinstance(failure, ArchiveDiscoveryFailed)
        assert failure.retryable is True and failure.retry_after == 600.0
        assert "example.nl" in str(failure) and "rate_limited" in str(failure) and "Retryable" in str(failure)

    def test_deferred_by_the_limiter_is_retryable(self):
        failure = fs.describe_discovery_failure(
            all_failed(CDXDeferred("Wayback paused for cdx (retry in 1800s)", retry_after=1800.0)), "example.nl"
        )
        assert failure.retryable and failure.retry_after == 1800.0 and "deferred" in str(failure)

    def test_timeout_is_retryable(self):
        failure = fs.describe_discovery_failure(all_failed(asyncio.TimeoutError()), "example.nl")
        assert failure.retryable and "timed out" in str(failure)

    def test_client_error_is_not_retryable(self):
        failure = fs.describe_discovery_failure(
            all_failed(CDXHTTPError("Client error: 400", status_code=400)), "example.nl"
        )
        assert failure.retryable is False and "Not retryable" in str(failure)

    def test_unrelated_exceptions_are_left_alone(self):
        assert fs.describe_discovery_failure(RuntimeError("Project not found"), "example.nl") is None


class FakeDb:
    """Just enough of a sync session for the task's bookkeeping."""

    def __init__(self, rows):
        self.rows = rows
        self.commits = 0

    def get(self, model, pk):
        return self.rows.get(model)

    def add(self, obj):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


@pytest.fixture
def task_env(monkeypatch):
    domain = SimpleNamespace(
        id=27, domain_name="bitsoffreedom.nl", project_id=23, status=DomainStatus.ACTIVE,
        from_date=None, to_date=None, match_type="domain", url_path=None,
    )
    scrape_session = SimpleNamespace(
        id=29, status=ScrapeSessionStatus.PENDING, error_message="stale", started_at=None, completed_at=None,
        total_urls=0, completed_urls=0, failed_urls=0, external_batch_id=None,
    )
    project = SimpleNamespace(id=23, enable_attachment_download=True)
    db = FakeDb({Domain: domain, ScrapeSession: scrape_session, Project: project})
    monkeypatch.setattr(fs, "get_sync_session", lambda: db)
    task = fs.scrape_domain_with_intelligent_extraction
    monkeypatch.setattr(task, "update_state", lambda *a, **k: None, raising=False)
    return SimpleNamespace(domain=domain, session=scrape_session, db=db, task=task)


def test_discovery_failure_fails_the_session_and_domain_with_a_clear_error_and_is_retried(task_env, monkeypatch):
    async def failing_discovery(domain, enable_attachments=True):
        raise all_failed(CDXRateLimited("Rate limited: 429", status_code=429, retry_after=600.0))

    monkeypatch.setattr(fs, "_discover_and_filter_pages", failing_discovery)

    # Called directly (no worker), Celery's retry() re-raises the exception it was given.
    with pytest.raises(ArchiveDiscoveryFailed) as excinfo:
        task_env.task.run(27, 29)

    assert excinfo.value.retryable
    assert task_env.session.status == ScrapeSessionStatus.FAILED  # never "completed"
    assert task_env.domain.status == DomainStatus.ERROR
    assert "Archive discovery failed for bitsoffreedom.nl" in task_env.session.error_message
    assert "rate_limited" in task_env.session.error_message and "Retryable" in task_env.session.error_message
    assert task_env.session.completed_urls == 0


def test_retryable_failure_schedules_a_celery_retry_after_the_pause(task_env, monkeypatch):
    async def failing_discovery(domain, enable_attachments=True):
        raise all_failed(CDXDeferred("Wayback paused for cdx", retry_after=1800.0))

    monkeypatch.setattr(fs, "_discover_and_filter_pages", failing_discovery)
    seen = {}

    class Retry(Exception):
        pass

    def fake_retry(exc=None, countdown=None, **kw):
        seen["countdown"] = countdown
        return Retry()

    monkeypatch.setattr(task_env.task, "retry", fake_retry, raising=False)

    with pytest.raises(Retry):
        task_env.task.run(27, 29)
    assert 1800 <= seen["countdown"] <= 3600  # not before the pause ends, capped at an hour


def test_non_retryable_discovery_failure_is_not_retried(task_env, monkeypatch):
    async def failing_discovery(domain, enable_attachments=True):
        raise all_failed(CDXHTTPError("Client error: 400", status_code=400))

    monkeypatch.setattr(fs, "_discover_and_filter_pages", failing_discovery)
    monkeypatch.setattr(task_env.task, "retry", lambda **kw: pytest.fail("must not retry"), raising=False)

    with pytest.raises(ArchiveDiscoveryFailed):
        task_env.task.run(27, 29)
    assert task_env.session.status == ScrapeSessionStatus.FAILED


@pytest.mark.asyncio
async def test_router_gives_wayback_a_generous_budget_and_chains_the_real_error(monkeypatch):
    """The 75 s cap no longer applies to Wayback, and the typed error is preserved for the caller."""
    from app.core.config import settings

    router = EnhancedArchiveServiceRouter(EnhancedRoutingConfig())
    seen = {}

    class Strategy:
        async def query_archive(self, *a, **kw):
            raise CDXRateLimited("Rate limited: 429", status_code=429, retry_after=60.0)

        def get_error_type(self, exc):
            return "wayback_rate_limit"

        def is_retriable_error(self, exc):
            return True

    real_wait_for = asyncio.wait_for

    async def spy_wait_for(coro, timeout):
        seen.setdefault("timeouts", []).append(timeout)
        return await real_wait_for(coro, timeout)

    monkeypatch.setattr(asyncio, "wait_for", spy_wait_for)
    router.strategies["wayback_machine"] = Strategy()
    from app.services.archive_service_router import ArchiveSource

    with pytest.raises(AllSourcesFailedException) as excinfo:
        await router.query_archive_unified("example.nl", "20160101", "20160131", ArchiveSource.WAYBACK_MACHINE)

    assert seen["timeouts"] == [settings.WAYBACK_CDX_DISCOVERY_TIMEOUT]
    assert settings.WAYBACK_CDX_DISCOVERY_TIMEOUT > 75
    assert isinstance(excinfo.value.__cause__, CDXRateLimited)
    # internet_archive is the same client + limiter: it must not be tried after wayback_machine
    assert len(excinfo.value.args[1]) == 1
