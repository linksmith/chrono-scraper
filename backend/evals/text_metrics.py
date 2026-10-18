"""Scoring metrics for extracted content vs gold annotations.

Two complementary body metrics, following the two benchmarks that dominate
the field:

* ``token_f1`` — order-free multiset F1 over word tokens (the WCXB /
  word-bag convention). Robust to paragraph reordering and whitespace noise.
* ``shingle_f1`` — F1 over word 4-gram shingles (the Zyte/scrapinghub
  article-extraction-benchmark convention). Sensitive to local word order,
  so it penalizes scrambled or interleaved extractions that token F1 forgives.

Title/author are scored as separate fields with partial credit; dates are
matched with a small tolerance and reported with coverage (a missing date is
"not scored", not "wrong", so extractors that never emit dates show up as low
coverage instead of dragging accuracy).

Empty-text convention follows SQuAD: both empty -> perfect, one empty -> zero.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher

from evals.textnorm import normalize_text, shingle_counts, tokenize

BODY_SHINGLE_N = 4  # matches the scrapinghub benchmark's 4-gram shingles


@dataclass(frozen=True)
class PRF:
    precision: float
    recall: float
    f1: float

    @classmethod
    def from_counts(cls, tp: float, pred_total: float, gold_total: float) -> "PRF":
        if gold_total == 0 and pred_total == 0:
            return cls(1.0, 1.0, 1.0)
        if gold_total == 0 or pred_total == 0:
            return cls(0.0, 0.0, 0.0)
        precision = tp / pred_total
        recall = tp / gold_total
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        return cls(precision, recall, f1)


def _multiset_prf(gold: Counter, pred: Counter) -> PRF:
    tp = sum((gold & pred).values())
    return PRF.from_counts(tp, sum(pred.values()), sum(gold.values()))


def token_f1(gold_text: str, pred_text: str) -> PRF:
    return _multiset_prf(Counter(tokenize(gold_text)), Counter(tokenize(pred_text)))


def shingle_f1(gold_text: str, pred_text: str, n: int = BODY_SHINGLE_N) -> PRF:
    return _multiset_prf(shingle_counts(gold_text, n), shingle_counts(pred_text, n))


@dataclass(frozen=True)
class FieldScore:
    """Score for a short metadata field (title, author)."""

    exact: bool
    similarity: float  # SequenceMatcher ratio on normalized strings, 0..1
    token_f1: float


def field_score(gold: str | None, pred: str | None) -> FieldScore:
    g = normalize_text(gold or "")
    p = normalize_text(pred or "")
    if not g and not p:
        return FieldScore(exact=True, similarity=1.0, token_f1=1.0)
    if not g or not p:
        return FieldScore(exact=False, similarity=0.0, token_f1=0.0)
    return FieldScore(
        exact=g == p,
        similarity=SequenceMatcher(None, g, p).ratio(),
        token_f1=token_f1(g, p).f1,
    )


def _coerce_date(value: str | datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    # Tolerate full ISO datetimes, trailing Z, and bare dates.
    candidate = text.removesuffix("Z")
    for parser_input in (candidate, candidate[:10]):
        try:
            parsed = datetime.fromisoformat(parser_input)
            return parsed.date()
        except ValueError:
            continue
    return None


def date_match(
    gold: str | datetime | date | None,
    pred: str | datetime | date | None,
    tolerance_days: int = 1,
) -> bool | None:
    """True/False if both dates are present and parseable, else None
    (= not scorable; callers report this as coverage, not as an error)."""
    g = _coerce_date(gold)
    p = _coerce_date(pred)
    if g is None or p is None:
        return None
    return abs((g - p).days) <= tolerance_days


@dataclass(frozen=True)
class SampleScore:
    """Full comparison of one extraction against one gold document."""

    body_token: PRF
    body_shingle: PRF
    title: FieldScore
    author: FieldScore
    date_ok: bool | None
    gold_tokens: int
    pred_tokens: int


def score_sample(
    *,
    gold_body: str,
    pred_body: str,
    gold_title: str | None = None,
    pred_title: str | None = None,
    gold_author: str | None = None,
    pred_author: str | None = None,
    gold_date: str | datetime | date | None = None,
    pred_date: str | datetime | date | None = None,
    date_tolerance_days: int = 1,
) -> SampleScore:
    return SampleScore(
        body_token=token_f1(gold_body, pred_body),
        body_shingle=shingle_f1(gold_body, pred_body),
        title=field_score(gold_title, pred_title),
        author=field_score(gold_author, pred_author),
        date_ok=date_match(gold_date, pred_date, date_tolerance_days),
        gold_tokens=len(tokenize(gold_body)),
        pred_tokens=len(tokenize(pred_body)),
    )
