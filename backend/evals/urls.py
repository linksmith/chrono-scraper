"""URL canonicalization — stdlib only, shared by collector and scorer.

Kept dependency-free (no httpx) so the offline scoring/dedup core can import
it without the collection stack.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def canonicalize_url(url: str) -> str:
    """Collapse URL variants that address the same resource.

    CDX ``original`` values for one page appear under several spellings —
    default ports (``:80``/``:443``) and ``#fragment`` anchors especially. If
    left distinct, captures of a single article scatter one-per-variant and
    the near-dup layer never sees them as the same page. Canonicalizing here
    groups them so a stable page yields many comparable captures.

    Deliberately conservative: scheme, host, path and query are preserved
    (``article.pl?sid=`` and ``item?id=`` are real identity), only the default
    port and the fragment are stripped, and the host is lowercased.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    netloc = parts.netloc.lower()
    if parts.scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif parts.scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    # Collapse a trailing slash (except the bare root) — "/TR/spec" and
    # "/TR/spec/" address the same document, and only a query makes them differ.
    path = parts.path
    if len(path) > 1 and path.endswith("/") and not parts.query:
        path = path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, netloc, path, parts.query, ""))
