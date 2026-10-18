"""Gold-annotation workflow: draft → human review → approved.

Hand-writing gold bodies from scratch is prohibitively slow, so the standard
benchmark shortcut applies: auto-draft each gold document from the best
available extraction, then a human *reviews and corrects* it (fixing missed
paragraphs, deleting leaked boilerplate) and flips ``review_status`` to
``approved``. Only approved documents are ever scored against — drafts carry
the bias of whichever extractor produced them, which would rig the benchmark
in that extractor's favor.

Gold documents are YAML files in ``evals/gold/`` (checked into git — they are
curated artifacts, unlike the bulky corpus data).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from evals.classify_page_type import PAGE_TYPES
from evals.config import EvalConfig
from evals.storage import BlobStore, Catalog

logger = logging.getLogger(__name__)

REVIEW_STATUSES = {"draft", "approved", "rejected"}
DRAFT_PRIORITY = ("trafilatura", "pipeline", "readability", "newspaper")


@dataclass(frozen=True)
class GoldDoc:
    sample_id: str
    snapshot_id: int
    url: str
    timestamp: str
    source: str
    page_type: str
    title: str
    body: str
    author: str | None = None
    date_published: str | None = None
    language: str | None = None
    review_status: str = "draft"
    drafted_from: str = ""
    drafted_at: str = ""
    notes: str = ""


class _GoldDumper(yaml.SafeDumper):
    """SafeDumper with literal blocks for multiline strings (readable bodies)."""


def _str_representer(dumper: yaml.Dumper, data: str):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_GoldDumper.add_representer(str, _str_representer)


def gold_path(gold_dir: Path, sample_id: str) -> Path:
    return Path(gold_dir) / f"{sample_id}.yaml"


def save_gold(gold_dir: Path, doc: GoldDoc) -> Path:
    path = gold_path(gold_dir, doc.sample_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(
            asdict(doc), fh, Dumper=_GoldDumper,
            sort_keys=False, allow_unicode=True, width=100,
        )
    return path


def load_gold(gold_dir: Path, only_approved: bool = True) -> list[GoldDoc]:
    docs = []
    for path in sorted(Path(gold_dir).glob("*.yaml")):
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        problems = _problems(raw, path.name)
        if problems:
            raise ValueError(f"invalid gold file {path}: {problems}")
        doc = GoldDoc(**raw)
        if only_approved and doc.review_status != "approved":
            continue
        docs.append(doc)
    return docs


def _problems(raw, name: str) -> list[str]:
    problems = []
    if not isinstance(raw, dict):
        return [f"{name}: not a mapping"]
    known = set(GoldDoc.__dataclass_fields__)
    for required in ("sample_id", "snapshot_id", "url", "page_type", "title", "body", "review_status"):
        if raw.get(required) in (None, "") and required != "title":
            problems.append(f"missing field '{required}'")
    unknown = set(raw) - known
    if unknown:
        problems.append(f"unknown fields {sorted(unknown)}")
    if raw.get("review_status") not in REVIEW_STATUSES:
        problems.append(f"review_status must be one of {sorted(REVIEW_STATUSES)}")
    if raw.get("page_type") not in PAGE_TYPES:
        problems.append(f"page_type must be one of {PAGE_TYPES}")
    return problems


def validate_gold(gold_dir: Path) -> dict:
    """Check every gold file; returns counts and per-file problems."""
    result = {"files": 0, "approved": 0, "draft": 0, "rejected": 0, "problems": {}}
    for path in sorted(Path(gold_dir).glob("*.yaml")):
        result["files"] += 1
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        problems = _problems(raw, path.name)
        if problems:
            result["problems"][path.name] = problems
            continue
        result[raw["review_status"]] += 1
    return result


# --------------------------------------------------------------------------
# Drafting
# --------------------------------------------------------------------------

def _best_extraction(catalog: Catalog, snapshot_id: int, from_engine: str | None = None):
    priority = (from_engine,) if from_engine else DRAFT_PRIORITY
    for extractor in priority:
        row = catalog.conn.execute(
            "SELECT * FROM extractions WHERE snapshot_id=? AND extractor=?"
            " AND body_sha256 IS NOT NULL AND error IS NULL AND n_tokens > 0",
            (snapshot_id, extractor),
        ).fetchone()
        if row:
            return row
    return None


def draft_gold(
    catalog: Catalog,
    store: BlobStore,
    cfg: EvalConfig,
    per_site: int = 1,
    site_filter: str | None = None,
    from_engine: str | None = None,
) -> list[Path]:
    """Draft gold docs for the best article-candidates of each site.

    Candidate ranking: manifest/human page_type label 'article' first, then
    classifier-predicted articles, longest extracted body first. Existing
    gold files are never overwritten (human edits are sacred).

    ``from_engine`` forces drafts to come from ONE named extractor. Draft from
    an engine NOT under primary test (e.g. readability) so the gold isn't
    authored by the system you most want to measure — otherwise that system
    scores ~1.0 by construction. The human review step is what turns a draft
    into real ground truth regardless.
    """
    manifest_types = catalog.labels("page_type", "manifest")
    human_types = catalog.labels("page_type", "human")
    classifier_types = catalog.labels("page_type", "classifier")
    written: list[Path] = []

    by_site: dict[str, list] = {}
    for snapshot in catalog.snapshots(site_key=site_filter, fetched_only=True):
        by_site.setdefault(snapshot["site_key"], []).append(snapshot)

    for site_key, snapshots in sorted(by_site.items()):
        candidates = []
        for snapshot in snapshots:
            sid = snapshot["id"]
            label = human_types.get(sid) or manifest_types.get(sid) or classifier_types.get(sid)
            extraction = _best_extraction(catalog, sid, from_engine)
            if extraction is None:
                continue
            rank = 0 if (human_types.get(sid) or manifest_types.get(sid)) == "article" else (
                1 if label == "article" else 2
            )
            candidates.append((rank, -int(extraction["n_tokens"] or 0), snapshot, extraction, label))
        candidates.sort(key=lambda c: (c[0], c[1]))

        drafted = 0
        for _, _, snapshot, extraction, label in candidates:
            if drafted >= per_site:
                break
            sample_id = f"{site_key}--{snapshot['id']}"
            path = gold_path(cfg.gold_dir, sample_id)
            if path.exists():
                drafted += 1  # counts toward per-site quota; do not overwrite
                continue
            doc = GoldDoc(
                sample_id=sample_id,
                snapshot_id=int(snapshot["id"]),
                url=snapshot["url"],
                timestamp=snapshot["timestamp"],
                source=snapshot["source"],
                page_type=label or "article",
                title=extraction["title"] or "",
                body=store.get_text(extraction["body_sha256"]),
                author=extraction["author"],
                date_published=extraction["date_published"],
                language=extraction["language"],
                review_status="draft",
                drafted_from=extraction["extractor"],
                drafted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                notes="REVIEW ME: correct title/body against the archived page, then set review_status: approved",
            )
            written.append(save_gold(cfg.gold_dir, doc))
            drafted += 1
            logger.info("gold: drafted %s from %s (%s tokens)", sample_id, extraction["extractor"], extraction["n_tokens"])
    return written
