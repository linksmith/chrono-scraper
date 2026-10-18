"""
Typed archive fetch failures shared by the fetch layer and the scrape tasks.

The fetch layer (wayback_machine / content_extraction_service / archive_rate_limiter)
raises these; the scrape tasks catch them and record ``error_type`` honestly on the
ScrapePage instead of mislabelling fetch failures as ``insufficient_content``.
``retryable`` failures are re-queued later at a low rate rather than retried inline.
"""
from typing import Optional


class ArchiveFetchError(Exception):
    """Base class. ``error_type`` is the value stored on ScrapePage.error_type."""

    error_type = "fetch_error"
    retryable = True

    def __init__(self, message: str, *, url: Optional[str] = None, status_code: Optional[int] = None,
                 retry_after: Optional[float] = None):
        super().__init__(message)
        self.url = url
        self.status_code = status_code
        self.retry_after = retry_after


class ArchiveRateLimited(ArchiveFetchError):
    """A real 429 / 503 (or rate-limit page) from the archive: counts as an attempt."""

    error_type = "rate_limited"


class ArchiveDeferred(ArchiveFetchError):
    """
    The shared limiter refused the request (Wayback paused, or no token / in-flight
    slot within WAYBACK_ACQUIRE_TIMEOUT). No request was sent, so this is NOT an
    attempt: callers re-queue the work at ``retry_after`` without consuming a retry.
    """

    error_type = "deferred"


class ArchiveConnectionError(ArchiveFetchError):
    """Connection refused/reset/timeout — on archive.org this is the firewall block after ignored 429s."""

    error_type = "connection_error"


class ArchiveHTTPError(ArchiveFetchError):
    """Non-retryable HTTP status (404, 410, ...) or a capture that redirects nowhere useful."""

    error_type = "http_error"
    retryable = False


class ArchiveBlockPage(ArchiveFetchError):
    """A 200 response whose body is an error/block/blank page, never to be stored as content."""

    error_type = "block_page"


class ArchiveDiscoveryFailed(Exception):
    """
    CDX discovery for a domain could not be completed (rate limit, pause, timeout, 5xx).

    Never an empty result: the scrape task marks the domain/session failed with this
    message and, when ``retryable``, re-runs itself after ``retry_after`` seconds.
    """

    def __init__(self, message: str, *, retryable: bool = True, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after
