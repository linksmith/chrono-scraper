"""
A scrape session spans several domains, each finished by its own Celery task. One
domain's failure must survive another domain completing later (session 30 showed
status "completed" with a "discovery failed" error_message).
"""
from app.models.project import ScrapeSession, ScrapeSessionStatus
from app.tasks.firecrawl_scraping import (
    clear_domain_failure,
    finish_domain_status,
    record_domain_failure,
)


def session() -> ScrapeSession:
    return ScrapeSession(project_id=1, status=ScrapeSessionStatus.RUNNING)


def test_failure_then_other_domain_completing_keeps_the_session_failed():
    s = session()
    record_domain_failure(s, "bitsoffreedom.nl", "Archive discovery failed (deferred)")
    assert s.status == ScrapeSessionStatus.FAILED
    assert finish_domain_status(s) == ScrapeSessionStatus.FAILED
    assert s.error_message == "[bitsoffreedom.nl] Archive discovery failed (deferred)"


def test_session_without_failures_completes():
    assert finish_domain_status(session()) == ScrapeSessionStatus.COMPLETED


def test_each_domain_keeps_its_own_line_and_a_repeat_replaces_it():
    s = session()
    record_domain_failure(s, "a.nl", "first")
    record_domain_failure(s, "b.nl", "multi\nline   message")
    record_domain_failure(s, "a.nl", "second")
    assert s.error_message.splitlines() == ["[b.nl] multi line message", "[a.nl] second"]


def test_rerun_clears_only_its_own_domain():
    s = session()
    record_domain_failure(s, "a.nl", "boom")
    record_domain_failure(s, "b.nl", "boom")
    clear_domain_failure(s, "a.nl")
    assert s.error_message == "[b.nl] boom"
    assert finish_domain_status(s) == ScrapeSessionStatus.FAILED
    clear_domain_failure(s, "b.nl")
    assert s.error_message is None
    assert finish_domain_status(s) == ScrapeSessionStatus.COMPLETED


def test_clearing_a_legacy_unprefixed_message_keeps_it():
    """An error_message written before this format stays visible (and keeps the session failed)."""
    s = session()
    s.error_message = "Archive discovery failed for x.nl"
    clear_domain_failure(s, "y.nl")
    assert s.error_message == "Archive discovery failed for x.nl"
