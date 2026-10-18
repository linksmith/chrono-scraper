"""Corpus storage: content-addressed blob store + SQLite catalog.

Design rationale (the "how do we store this efficiently" answer):

* Raw snapshot payloads and extracted bodies are stored once per unique
  content in a content-addressed store (CAS): ``objects/ab/cd/<sha256>.gz``.
  The Wayback Machine re-crawls byte-identical pages constantly, so keying
  storage by content hash gives raw-level dedup for free; body-level dedup
  falls out the same way after extraction, because near-identical snapshots
  normalize to the same body text and therefore the same blob.
* Everything relational (which URL, which timestamp, which archive, which
  extractor produced which body, classifier labels, dup clusters) lives in a
  single SQLite file — stdlib, transactional, one file to copy around. At
  corpus scale (10^2–10^5 documents) SQLite is comfortably sufficient; the
  documented upgrade path for orders of magnitude more is WARC + zstd
  dictionaries + parquet, not a rewrite of this schema.

Gzip via stdlib keeps the harness dependency-free; compression choice is
recorded per-object nothing prevents adding zstd later.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY,
    site_key TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,              -- 'wayback' | 'commoncrawl'
    timestamp TEXT NOT NULL,           -- 14-digit archive timestamp
    cdx_digest TEXT,                   -- archive-reported SHA-1 (base32)
    status_code INTEGER,
    mime TEXT,
    fetch_url TEXT,                    -- exact URL / WARC coords used to fetch
    raw_sha256 TEXT,                   -- CAS key of raw payload (NULL until fetched)
    raw_bytes INTEGER,
    fetched_at TEXT,
    fetch_error TEXT,
    UNIQUE (source, url, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_site ON snapshots (site_key);
CREATE INDEX IF NOT EXISTS idx_snapshots_raw ON snapshots (raw_sha256);

CREATE TABLE IF NOT EXISTS extractions (
    id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots (id) ON DELETE CASCADE,
    extractor TEXT NOT NULL,           -- 'pipeline' | 'trafilatura' | ...
    title TEXT,
    author TEXT,
    date_published TEXT,               -- ISO date if known
    language TEXT,
    body_sha256 TEXT,                  -- CAS key of extracted body text
    body_key TEXT,                     -- normalized-token sha256 (exact-dup key)
    simhash TEXT,                      -- 16 hex chars (SimHash64)
    n_tokens INTEGER,
    extraction_method TEXT,
    confidence REAL,
    error TEXT,
    created_at TEXT,
    UNIQUE (snapshot_id, extractor)
);
CREATE INDEX IF NOT EXISTS idx_extractions_extractor ON extractions (extractor);
CREATE INDEX IF NOT EXISTS idx_extractions_body_key ON extractions (body_key);

CREATE TABLE IF NOT EXISTS features (
    snapshot_id INTEGER PRIMARY KEY REFERENCES snapshots (id) ON DELETE CASCADE,
    json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS labels (
    snapshot_id INTEGER NOT NULL REFERENCES snapshots (id) ON DELETE CASCADE,
    kind TEXT NOT NULL,                -- 'era' | 'page_type' | 'dup_group' | ...
    value TEXT NOT NULL,
    source TEXT NOT NULL,              -- 'classifier' | 'manifest' | 'human' | 'app_filter'
    detail TEXT,                       -- JSON: confidence, fired signals, ...
    PRIMARY KEY (snapshot_id, kind, source)
);

CREATE TABLE IF NOT EXISTS clusters (
    extractor TEXT NOT NULL,
    extraction_id INTEGER NOT NULL REFERENCES extractions (id) ON DELETE CASCADE,
    cluster_id TEXT NOT NULL,
    PRIMARY KEY (extractor, extraction_id)
);
CREATE INDEX IF NOT EXISTS idx_clusters_cluster ON clusters (extractor, cluster_id);
"""


class BlobStore:
    """Content-addressed, gzip-compressed object store."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, sha: str) -> Path:
        return self.root / sha[:2] / sha[2:4] / f"{sha}.gz"

    def put(self, data: bytes) -> tuple[str, bool]:
        """Store bytes, return (sha256, was_new). Idempotent; atomic write.

        Writes to a per-writer unique temp file (not a shared ``<sha>.tmp``) so
        two processes storing the same bytes can't interleave into a corrupt
        blob, then atomically renames. gzip mtime is pinned to 0 so identical
        content always produces byte-identical blobs (reproducibility).
        """
        sha = hashlib.sha256(data).hexdigest()
        path = self._path(sha)
        if path.exists():
            return sha, False
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as raw, gzip.GzipFile(
                fileobj=raw, mode="wb", compresslevel=6, mtime=0
            ) as fh:
                fh.write(data)
            os.replace(tmp_name, path)
        except BaseException:
            # Never leave a stray temp file behind on error/interrupt.
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise
        return sha, True

    def put_text(self, text: str) -> tuple[str, bool]:
        return self.put(text.encode("utf-8"))

    def get(self, sha: str) -> bytes:
        with gzip.open(self._path(sha), "rb") as fh:
            return fh.read()

    def get_text(self, sha: str) -> str:
        return self.get(sha).decode("utf-8")

    def has(self, sha: str) -> bool:
        return self._path(sha).exists()

    def stats(self) -> dict:
        count = 0
        compressed = 0
        for path in self.root.rglob("*.gz"):
            count += 1
            compressed += path.stat().st_size
        return {"objects": count, "compressed_bytes": compressed}


@dataclass(frozen=True)
class SnapshotRef:
    """What the collector knows about one archive capture before fetching."""

    site_key: str
    url: str
    source: str
    timestamp: str
    cdx_digest: str | None = None
    status_code: int | None = None
    mime: str | None = None
    fetch_url: str | None = None


class Catalog:
    """SQLite catalog of snapshots, extractions, features, labels, clusters."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 30s busy timeout so concurrent writers (e.g. collector + an analysis
        # query) block-and-retry instead of raising "database is locked"; WAL +
        # NORMAL keeps that safe and fast.
        self.conn = sqlite3.connect(str(self.path), timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Catalog":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- snapshots -----------------------------------------------------------

    def upsert_snapshot(self, ref: SnapshotRef) -> int:
        row = self.conn.execute(
            """
            INSERT INTO snapshots (site_key, url, source, timestamp, cdx_digest,
                                   status_code, mime, fetch_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source, url, timestamp) DO UPDATE SET
                site_key = excluded.site_key,
                cdx_digest = COALESCE(excluded.cdx_digest, snapshots.cdx_digest),
                status_code = COALESCE(excluded.status_code, snapshots.status_code),
                mime = COALESCE(excluded.mime, snapshots.mime),
                fetch_url = COALESCE(excluded.fetch_url, snapshots.fetch_url)
            RETURNING id
            """,
            (
                ref.site_key, ref.url, ref.source, ref.timestamp, ref.cdx_digest,
                ref.status_code, ref.mime, ref.fetch_url,
            ),
        ).fetchone()
        self.conn.commit()
        return int(row["id"])

    def mark_fetched(
        self, snapshot_id: int, raw_sha256: str, raw_bytes: int, fetched_at: str
    ) -> None:
        self.conn.execute(
            "UPDATE snapshots SET raw_sha256=?, raw_bytes=?, fetched_at=?, fetch_error=NULL"
            " WHERE id=?",
            (raw_sha256, raw_bytes, fetched_at, snapshot_id),
        )
        self.conn.commit()

    def mark_fetch_error(self, snapshot_id: int, error: str) -> None:
        self.conn.execute(
            "UPDATE snapshots SET fetch_error=? WHERE id=?", (error[:500], snapshot_id)
        )
        self.conn.commit()

    def snapshots(
        self, *, site_key: str | None = None, fetched_only: bool = False
    ) -> list[sqlite3.Row]:
        clauses, params = [], []
        if site_key:
            clauses.append("site_key = ?")
            params.append(site_key)
        if fetched_only:
            clauses.append("raw_sha256 IS NOT NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.conn.execute(
            f"SELECT * FROM snapshots {where} ORDER BY site_key, timestamp", params
        ).fetchall()

    def snapshot_by_id(self, snapshot_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()

    # -- extractions -----------------------------------------------------------

    def upsert_extraction(self, snapshot_id: int, extractor: str, **fields) -> int:
        allowed = {
            "title", "author", "date_published", "language", "body_sha256",
            "body_key", "simhash", "n_tokens", "extraction_method",
            "confidence", "error", "created_at",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown extraction fields: {sorted(unknown)}")
        columns = sorted(fields)
        assignments = ", ".join(f"{c} = excluded.{c}" for c in columns)
        placeholders = ", ".join("?" for _ in columns)
        row = self.conn.execute(
            f"""
            INSERT INTO extractions (snapshot_id, extractor{''.join(', ' + c for c in columns)})
            VALUES (?, ?{', ' if columns else ''}{placeholders})
            ON CONFLICT (snapshot_id, extractor) DO UPDATE SET {assignments or 'extractor = excluded.extractor'}
            RETURNING id
            """,
            (snapshot_id, extractor, *[fields[c] for c in columns]),
        ).fetchone()
        self.conn.commit()
        return int(row["id"])

    def extractions(self, extractor: str, *, with_bodies_only: bool = False) -> list[sqlite3.Row]:
        where = "AND body_sha256 IS NOT NULL" if with_bodies_only else ""
        return self.conn.execute(
            f"""
            SELECT e.*, s.site_key, s.url, s.timestamp, s.source
            FROM extractions e JOIN snapshots s ON s.id = e.snapshot_id
            WHERE e.extractor = ? {where}
            ORDER BY s.site_key, s.timestamp
            """,
            (extractor,),
        ).fetchall()

    # -- features / labels -----------------------------------------------------

    def set_features(self, snapshot_id: int, features: dict) -> None:
        self.conn.execute(
            "INSERT INTO features (snapshot_id, json) VALUES (?, ?)"
            " ON CONFLICT (snapshot_id) DO UPDATE SET json = excluded.json",
            (snapshot_id, json.dumps(features, ensure_ascii=False)),
        )
        self.conn.commit()

    def get_features(self, snapshot_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT json FROM features WHERE snapshot_id=?", (snapshot_id,)
        ).fetchone()
        return json.loads(row["json"]) if row else None

    def set_label(
        self, snapshot_id: int, kind: str, value: str, source: str, detail: dict | None = None
    ) -> None:
        self.conn.execute(
            "INSERT INTO labels (snapshot_id, kind, value, source, detail) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT (snapshot_id, kind, source) DO UPDATE SET"
            " value = excluded.value, detail = excluded.detail",
            (
                snapshot_id, kind, value, source,
                json.dumps(detail, ensure_ascii=False) if detail else None,
            ),
        )
        self.conn.commit()

    def labels(self, kind: str, source: str | None = None) -> dict[int, str]:
        if source:
            rows = self.conn.execute(
                "SELECT snapshot_id, value FROM labels WHERE kind=? AND source=?",
                (kind, source),
            )
        else:
            rows = self.conn.execute(
                "SELECT snapshot_id, value FROM labels WHERE kind=?", (kind,)
            )
        return {int(r["snapshot_id"]): r["value"] for r in rows}

    # -- clusters ---------------------------------------------------------------

    def replace_clusters(self, extractor: str, mapping: dict[int, str]) -> None:
        """mapping: extraction_id -> cluster_id (full replacement per extractor)."""
        with self.conn:
            self.conn.execute("DELETE FROM clusters WHERE extractor=?", (extractor,))
            self.conn.executemany(
                "INSERT INTO clusters (extractor, extraction_id, cluster_id) VALUES (?, ?, ?)",
                [(extractor, eid, cid) for eid, cid in mapping.items()],
            )

    def clusters(self, extractor: str) -> dict[int, str]:
        rows = self.conn.execute(
            "SELECT extraction_id, cluster_id FROM clusters WHERE extractor=?",
            (extractor,),
        )
        return {int(r["extraction_id"]): r["cluster_id"] for r in rows}

    # -- summary ------------------------------------------------------------------

    def summary(self) -> dict:
        one = lambda sql, *p: self.conn.execute(sql, p).fetchone()[0]  # noqa: E731
        return {
            "snapshots": one("SELECT COUNT(*) FROM snapshots"),
            "fetched": one("SELECT COUNT(*) FROM snapshots WHERE raw_sha256 IS NOT NULL"),
            "fetch_errors": one("SELECT COUNT(*) FROM snapshots WHERE fetch_error IS NOT NULL"),
            "unique_raw_blobs": one(
                "SELECT COUNT(DISTINCT raw_sha256) FROM snapshots WHERE raw_sha256 IS NOT NULL"
            ),
            "sites": one("SELECT COUNT(DISTINCT site_key) FROM snapshots"),
            "extractions": one("SELECT COUNT(*) FROM extractions"),
            "extractors": [
                r[0]
                for r in self.conn.execute(
                    "SELECT DISTINCT extractor FROM extractions ORDER BY 1"
                )
            ],
            "labels": {
                r[0]: r[1]
                for r in self.conn.execute(
                    "SELECT kind || '/' || source, COUNT(*) FROM labels GROUP BY 1"
                )
            },
        }
