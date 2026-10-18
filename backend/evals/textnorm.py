"""Shared text normalization for dedup fingerprinting and scoring.

Both the near-duplicate detector and the extraction scorer must see the *same*
view of a text, otherwise "identical body, different whitespace" counts as a
difference in one place and not the other. Keep every normalization decision
in this module.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Iterator

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Unicode NFKC, casefold, collapse all whitespace runs to single spaces."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()
    return _WS_RE.sub(" ", text).strip()


def tokenize(text: str) -> list[str]:
    """Word tokens (\\w+ runs) of the normalized text.

    Punctuation-insensitive on purpose: smart quotes, dashes and entity
    variants between snapshots of the same article must not register as
    content differences.
    """
    return _WORD_RE.findall(normalize_text(text))


def shingles(tokens: Iterable[str], n: int) -> Iterator[str]:
    """Sliding word n-grams joined with spaces.

    Texts shorter than ``n`` tokens yield one shingle with all tokens, so very
    short documents still produce a non-empty feature set.
    """
    toks = list(tokens)
    if not toks:
        return
    if len(toks) < n:
        yield " ".join(toks)
        return
    for i in range(len(toks) - n + 1):
        yield " ".join(toks[i : i + n])


def shingle_counts(text: str, n: int) -> Counter[str]:
    return Counter(shingles(tokenize(text), n))


def body_key(text: str) -> str:
    """Exact-duplicate key: sha256 over the normalized token stream.

    Two bodies that differ only in whitespace, case or unicode form get the
    same key. This is the first (cheap, exact) dedup tier; SimHash handles the
    near-identical tier.
    """
    joined = " ".join(tokenize(text))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
