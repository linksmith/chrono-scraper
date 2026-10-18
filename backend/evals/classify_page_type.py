"""Structural page-type classification: is this a canonical content page?

Labels: ``article`` (canonical content: news story, blog/forum/social post,
wiki entry, Q&A thread), ``list`` (index/category/tag/archive/pagination),
``search`` (result pages), ``home`` (site front doors), ``error``
(404/blocked), ``other`` (shells, media pages, unclassifiable).

This is *content-based* classification (link density, text-block mass,
repeated template rows — Kohlschütter-style shallow features) with URL
patterns as one voice among several. That contrast is deliberate: the app's
production filters (``intelligent_filter``/``enhanced_intelligent_filter``)
are URL-regex-only and run before fetch, so this classifier provides the
structural ground truth the eval scores them against.

Scores for every label are returned, not just the argmax, so the report can
show *why* a page was (mis)classified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from evals.config import PageTypeConfig
from evals.html_features import PageFeatures

PAGE_TYPES = ["article", "list", "search", "home", "error", "other"]

_ARTICLE_URL_PATTERNS = [
    re.compile(r"/\d{4}/\d{1,2}/\w"),                # date-based permalinks
    re.compile(r"/(article|articles|story|stories|post|posts|news|artikel|artikelen)/", re.I),
    re.compile(r"/status(es)?/\d+"),                 # tweet permalinks
    re.compile(r"/comments/\w+/"),                   # reddit threads
    re.compile(r"/questions/\d+/"),                  # stack overflow
    re.compile(r"viewtopic\.php", re.I),             # phpBB threads
    re.compile(r"\bitem\?id=\d+", re.I),             # Hacker News item threads
    re.compile(r"\barticle\.pl\b", re.I),            # Slashdot story pages
    re.compile(r"[?&]sid=\w", re.I),                 # legacy CMS story ids
    re.compile(r"/title/tt\d+", re.I),               # IMDb title entities
    re.compile(r"/wiki/(?!(Category|Special|Talk|File|Template|Portal)([:%]))\w", re.I),
    re.compile(r"/p/[\w-]{6,}"),                     # medium/instagram permalinks
    re.compile(r"[-_][\w%]+[-_][\w%]+[-_][\w%]+"),   # long hyphenated slugs
    re.compile(r"/\d{6,}\.(html?|stm)$", re.I),      # numeric story ids (BBC .stm etc.)
]
_LIST_URL_PATTERNS = [
    re.compile(r"/(category|categories|tag|tags|topics?|archives?|section|rubriek)/", re.I),
    re.compile(r"/wiki/Category[:%]", re.I),
    re.compile(r"[?&](page|paged|start|offset|p)=\d+", re.I),
    re.compile(r"/page/\d+", re.I),
    re.compile(r"/(blog|news|articles|posts|forum|forums)/?$", re.I),
    re.compile(r"viewforum\.php", re.I),
    re.compile(r"/questions/tagged/", re.I),
    re.compile(r"/\d{4}/\d{1,2}/?$"),                # bare date archives
]
_SEARCH_URL_PATTERN = re.compile(r"/(search|zoeken)\b", re.I)
_SEARCH_QUERY_KEYS = {"q", "query", "s", "search", "keywords", "zoekterm"}

_LIST_TITLE_RE = re.compile(
    r"\b(archive|archives|category|categorie|index of|tag|overview|latest|page \d+)\b", re.I
)
_SEARCH_TITLE_RE = re.compile(r"\b(search results?|zoekresultaten|results for)\b", re.I)
_ERROR_TEXT_RE = re.compile(
    r"\b(404|not found|page cannot be found|page doesn.t exist|forbidden"
    r"|access denied|niet gevonden|robots\.txt|blocked)\b",
    re.I,
)


@dataclass(frozen=True)
class PageTypeResult:
    label: str
    confidence: float
    scores: dict[str, float]
    signals: list[str]


def _url_matches(url: str, patterns: list[re.Pattern]) -> bool:
    return any(p.search(url) for p in patterns)


def classify_page_type(
    features: PageFeatures, url: str = "", config: PageTypeConfig | None = None
) -> PageTypeResult:
    cfg = config or PageTypeConfig()
    f = features
    scores = {label: 0.0 for label in PAGE_TYPES}
    signals: list[str] = []
    parsed = urlparse(url) if url else None
    path = (parsed.path if parsed else "").rstrip("/")
    query_keys = {k.lower() for k in parse_qs(parsed.query)} if parsed and parsed.query else set()
    title_and_lead = f"{f.title} {f.first_text[:200]}"

    def vote(label: str, weight: float, signal: str) -> None:
        scores[label] += weight
        signals.append(f"{label}:{signal}(+{weight:g})")

    # --- article evidence ---------------------------------------------------
    if f.largest_block_chars >= cfg.min_article_block_chars:
        vote("article", 2.0, f"large_block={f.largest_block_chars}")
    if f.total_text_chars > 300 and f.link_density <= cfg.link_density_article_max:
        vote("article", 1.5, f"low_link_density={f.link_density:.2f}")
    if f.p_count >= 3:
        vote("article", 1.0, f"paragraphs={f.p_count}")
    if f.meta_og_type == "article":
        vote("article", 2.0, "og_type=article")
    if url and _url_matches(url, _ARTICLE_URL_PATTERNS):
        vote("article", 1.5, "article_url_pattern")
    if f.h1_count == 1:
        vote("article", 0.5, "single_h1")
    if f.blocks_over_200 >= 2:
        vote("article", 0.5, f"substantial_blocks={f.blocks_over_200}")
    # Discussion/thread pages: lots of prose spread over many small blocks
    # (comments, forum posts) rather than one big body. The link-density guard
    # keeps this off link-dominated real list pages.
    if (
        f.total_text_chars >= cfg.min_prose_chars
        and f.link_density < cfg.prose_link_density_max
        and f.blocks_over_200 >= 1
    ):
        vote("article", 1.5, f"substantial_prose(chars={f.total_text_chars},ld={f.link_density:.2f})")

    # --- list evidence --------------------------------------------------------
    if f.n_anchors >= 15 and f.link_density >= cfg.link_density_list:
        vote("list", 2.0, f"high_link_density={f.link_density:.2f}")
    if f.repeated_block_class_max >= cfg.repeated_block_threshold:
        vote("list", 1.5, f"repeated_template_rows={f.repeated_block_class_max}")
    if url and _url_matches(url, _LIST_URL_PATTERNS):
        vote("list", 2.0, "list_url_pattern")
    if f.n_anchors >= cfg.listing_anchor_count and f.largest_block_chars <= cfg.listing_max_block_chars:
        vote("list", 1.5, f"many_links_no_body(anchors={f.n_anchors})")
    if f.pagination_hints >= cfg.min_pagination_hints or f.rel_next:
        vote("list", 1.0, f"pagination(hints={f.pagination_hints},rel_next={f.rel_next})")
    if f.li_text_ratio >= 0.5 and f.li_count >= 15:
        vote("list", 1.0, f"li_dominated(count={f.li_count})")
    if _LIST_TITLE_RE.search(f.title or ""):
        vote("list", 1.0, "list_title_marker")

    # --- search evidence -------------------------------------------------------
    if query_keys & _SEARCH_QUERY_KEYS:
        vote("search", 2.5, f"search_query_param={sorted(query_keys & _SEARCH_QUERY_KEYS)}")
    if url and _SEARCH_URL_PATTERN.search(parsed.path if parsed else ""):
        vote("search", 1.5, "search_url_path")
    if _SEARCH_TITLE_RE.search(f.title or ""):
        vote("search", 2.0, "search_title_marker")
    if f.search_inputs >= 1 and scores["search"] > 0:
        vote("search", 1.0, "search_input_present")

    # --- error evidence ----------------------------------------------------------
    if _ERROR_TEXT_RE.search(title_and_lead):
        vote("error", 3.0, "error_marker_in_title_or_lead")
        if f.total_text_chars < 400:
            vote("error", 1.0, "tiny_page")

    # --- home evidence -------------------------------------------------------------
    if parsed and path in ("", "/index.html", "/index.htm", "/default.htm", "/home.html") and not parsed.query:
        vote("home", 1.5, f"root_path='{path or '/'}'")
        if f.n_anchors >= 15:
            vote("home", 1.0, "root_with_many_links")

    # --- shells / unclassifiable ------------------------------------------------------
    if f.total_text_chars < 50 and f.script_ratio > 0.5:
        vote("other", 2.5, "js_shell_no_content")
    if f.has_frameset and f.total_text_chars < 200:
        vote("other", 1.5, "frameset_shell")
    scores["other"] += 0.4  # floor: a page with no evidence at all is "other"

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    (top_label, top_score), (_, second_score) = ranked[0], ranked[1]
    margin = top_score - second_score
    if margin < cfg.decision_margin:
        confidence = 0.35 + 0.1 * margin
    else:
        confidence = min(0.95, 0.5 + 0.08 * top_score + 0.05 * margin)
    return PageTypeResult(
        label=top_label,
        confidence=round(confidence, 3),
        scores={k: round(v, 2) for k, v in scores.items()},
        signals=signals,
    )
