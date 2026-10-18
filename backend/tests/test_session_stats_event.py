"""The discovery-time session stats broadcast must be a valid SessionStatsEvent."""
from types import SimpleNamespace

from app.models.scraping import ScrapePageStatus, SessionStatsEvent
from app.services import websocket_service
from app.tasks.firecrawl_scraping import _discovery_session_stats


def pages(*statuses):
    return [SimpleNamespace(status=s) for s in statuses]


def test_discovery_stats_validate_against_the_event_schema():
    created = pages(
        ScrapePageStatus.PENDING, ScrapePageStatus.PENDING, ScrapePageStatus.COMPLETED,
        ScrapePageStatus.FILTERED_LIST_PAGE,
    )
    payload = _discovery_session_stats(29, created, discovered=10, already_known=6)

    event = SessionStatsEvent(**payload)  # raised "10 validation errors" before

    assert event.scrape_session_id == 29
    assert event.total_urls == 10
    assert (event.pending_urls, event.completed_urls, event.skipped_urls) == (2, 1, 1)
    assert event.progress_percentage == 20.0
    assert event.performance_metrics == {"already_known_urls": 6}


def test_empty_discovery_does_not_divide_by_zero():
    event = SessionStatsEvent(**_discovery_session_stats(1, [], discovered=0, already_known=0))
    assert event.total_urls == 0 and event.progress_percentage == 0.0


def test_broadcaster_publishes_the_discovery_stats_without_logging_an_error(monkeypatch, caplog):
    published = []
    monkeypatch.setattr(websocket_service, "_publish_event", lambda session_id, message: published.append((session_id, message)))

    with caplog.at_level("ERROR"):
        websocket_service.broadcast_session_stats_sync(
            _discovery_session_stats(29, pages(ScrapePageStatus.PENDING), discovered=1, already_known=0)
        )

    assert "Failed to broadcast session stats" not in caplog.text
    assert published and published[0][0] == 29
    assert published[0][1]["type"] == "session_stats" and published[0][1]["data"]["total_urls"] == 1
