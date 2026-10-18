"""Extractor adapters: run content extractors over stored raw HTML.

Adapters normalize every engine to one ``ExtractedDoc`` shape so scoring and
dedup are engine-agnostic:

* ``pipeline``    — the app's own ``IntelligentContentExtractor`` (the system
                    under test). Imported lazily: it needs the backend
                    environment, and the rest of the harness must keep
                    working without it.
* ``trafilatura`` / ``readability`` / ``newspaper`` — the individual
  libraries, as competitive baselines (benchmark practice: never evaluate a
  system without baselines on the same corpus).

All adapters are wrapped so scoring never crashes: failures come back as an
``ExtractedDoc`` with ``error`` set and an empty body, which scores 0 — an
extractor that dies on 1996 tag soup *should* pay for it in the report.
"""

from __future__ import annotations

import html as html_module
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from datetime import timezone as dt_timezone

from evals.config import EvalConfig
from evals.dedup import simhash64
from evals.html_features import decode_html
from evals.storage import BlobStore, Catalog
from evals.textnorm import body_key, tokenize

logger = logging.getLogger(__name__)

EXTRACTOR_NAMES = ["pipeline", "trafilatura", "readability", "newspaper"]


@dataclass(frozen=True)
class ExtractedDoc:
    title: str
    body: str
    author: str | None = None
    date_published: str | None = None  # ISO date string
    language: str | None = None
    method: str = "unknown"
    confidence: float | None = None
    error: str | None = None


def _iso(value) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value:
        return str(value)
    return None


_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_ANY_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_text(fragment: str) -> str:
    """Cheap tag-stripper for the mostly-clean HTML readability returns."""
    text = _TAG_RE.sub(" ", fragment)
    text = _ANY_TAG_RE.sub(" ", text)
    return " ".join(html_module.unescape(text).split())


# --------------------------------------------------------------------------
# Adapters (lazy imports; never raise)
# --------------------------------------------------------------------------

def extract_trafilatura(html: str, url: str) -> ExtractedDoc:
    import trafilatura

    body = trafilatura.extract(
        html, url=url, include_comments=False, include_tables=True
    ) or ""
    title = author = published = None
    try:
        meta = trafilatura.extract_metadata(html, default_url=url)
        if meta is not None:
            title = getattr(meta, "title", None)
            author = getattr(meta, "author", None)
            published = getattr(meta, "date", None)
    except Exception as exc:  # metadata failure must not void the body
        logger.debug("trafilatura metadata failed for %s: %s", url, exc)
    return ExtractedDoc(
        title=title or "", body=body, author=author,
        date_published=_iso(published), method="trafilatura",
    )


def extract_readability(html: str, url: str) -> ExtractedDoc:
    from readability import Document

    doc = Document(html)
    return ExtractedDoc(
        title=doc.short_title() or "",
        body=_html_to_text(doc.summary(html_partial=True)),
        method="readability",
    )


def extract_newspaper(html: str, url: str) -> ExtractedDoc:
    from newspaper import Article

    article = Article(url or "http://localhost/eval-input")
    article.download(input_html=html)
    article.parse()
    return ExtractedDoc(
        title=article.title or "",
        body=article.text or "",
        author=", ".join(article.authors) if article.authors else None,
        date_published=_iso(article.publish_date),
        method="newspaper3k",
    )


def extract_pipeline(html: str, url: str) -> ExtractedDoc:
    """The system under test: chrono-scraper's own extraction stack."""
    from app.services.intelligent_content_extractor import get_intelligent_extractor

    result = get_intelligent_extractor().extract(html, url or None)
    meta = result.metadata
    return ExtractedDoc(
        title=result.title or "",
        body=result.text or "",
        author=meta.author,
        date_published=_iso(meta.publication_date),
        language=meta.language,
        method=f"pipeline/{result.extraction_method}",
        confidence=result.confidence_score,
    )


_ADAPTERS = {
    "pipeline": extract_pipeline,
    "trafilatura": extract_trafilatura,
    "readability": extract_readability,
    "newspaper": extract_newspaper,
}


def available_extractors() -> dict[str, str]:
    """name -> 'ok' or the import error keeping it unavailable."""
    probes = {
        "pipeline": "app.services.intelligent_content_extractor",
        "trafilatura": "trafilatura",
        "readability": "readability",
        "newspaper": "newspaper",
    }
    status = {}
    for name, module in probes.items():
        try:
            __import__(module)
            status[name] = "ok"
        except Exception as exc:  # ImportError or app-settings failures
            status[name] = f"unavailable: {exc.__class__.__name__}: {exc}"
    return status


def run_extractor(name: str, html: str, url: str) -> ExtractedDoc:
    if name not in _ADAPTERS:
        raise ValueError(f"unknown extractor '{name}' (choose from {EXTRACTOR_NAMES})")
    try:
        return _ADAPTERS[name](html, url)
    except Exception as exc:
        logger.warning("extract[%s]: failed on %s: %s", name, url, exc)
        return ExtractedDoc(title="", body="", method=name, error=f"{exc.__class__.__name__}: {exc}")


# ------------------------------------------------------------------------------
# Catalog integration
# ------------------------------------------------------------------------------

def extract_snapshot(
    catalog: Catalog,
    store: BlobStore,
    cfg: EvalConfig,
    snapshot,  # sqlite3.Row from Catalog.snapshots()
    extractor: str,
    force: bool = False,
) -> int | None:
    """Run one extractor over one fetched snapshot; persist body + fingerprint."""
    existing = catalog.conn.execute(
        "SELECT id, body_sha256 FROM extractions WHERE snapshot_id=? AND extractor=?",
        (snapshot["id"], extractor),
    ).fetchone()
    if existing and existing["body_sha256"] and not force:
        return int(existing["id"])
    if not snapshot["raw_sha256"]:
        return None

    html = decode_html(store.get(snapshot["raw_sha256"]))
    doc = run_extractor(extractor, html, snapshot["url"])
    body_sha, _ = store.put_text(doc.body)
    tokens = tokenize(doc.body)
    return catalog.upsert_extraction(
        snapshot["id"],
        extractor,
        title=doc.title,
        author=doc.author,
        date_published=doc.date_published,
        language=doc.language,
        body_sha256=body_sha,
        body_key=body_key(doc.body),
        simhash=format(simhash64(doc.body, cfg.dedup.shingle_size), "016x"),
        n_tokens=len(tokens),
        extraction_method=doc.method,
        confidence=doc.confidence,
        error=doc.error,
        created_at=datetime.now(dt_timezone.utc).isoformat(timespec="seconds"),
    )


def extract_all(
    catalog: Catalog,
    store: BlobStore,
    cfg: EvalConfig,
    extractors: list[str],
    site_filter: str | None = None,
    force: bool = False,
) -> dict:
    """Run the requested extractors over every fetched snapshot."""
    status = available_extractors()
    runnable = []
    for name in extractors:
        if status.get(name) == "ok":
            runnable.append(name)
        else:
            logger.error("extract: skipping '%s' — %s", name, status.get(name))
    stats = {name: {"done": 0, "errors": 0} for name in runnable}
    snapshots = catalog.snapshots(site_key=site_filter, fetched_only=True)
    logger.info("extract: %d snapshots x %s", len(snapshots), runnable)
    for snapshot in snapshots:
        for name in runnable:
            extraction_id = extract_snapshot(catalog, store, cfg, snapshot, name, force=force)
            if extraction_id is None:
                continue
            row = catalog.conn.execute(
                "SELECT error FROM extractions WHERE id=?", (extraction_id,)
            ).fetchone()
            stats[name]["errors" if row and row["error"] else "done"] += 1
    return stats
