"""Structural feature extraction from raw HTML — stdlib only.

Built on the ``html.parser`` event stream instead of a DOM tree on purpose:
the corpus spans 1994–2026, and early-web tag soup (unclosed ``<p>``,
framesets, uppercase tags, unquoted attributes) defeats strict tree builders.
Counting signals from the token stream works on anything.

Three outputs per page:

* ``PageFeatures`` — shallow numeric/boolean signals (link density, text
  blocks, legacy-markup counts, framework markers …) consumed by the era and
  page-type classifiers. Link/text density features follow Kohlschütter et
  al. (WSDM 2010), which showed shallow text features rival DOM-aware methods.
* a structure *fingerprint* — parent>child tag bigrams and class tokens,
  feature-hashed into a signed 64-dim vector. Cosine similarity between
  fingerprints measures *layout* similarity independent of text, which the
  corpus report uses to check we actually collected structurally diverse
  sites (and to group unknown sites by template).
* ``first_text`` / ``title`` snippets for cheap error-page sniffing.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

MAX_PARSE_BYTES = 5 * 1024 * 1024
FINGERPRINT_DIMS = 64

VOID_TAGS = {
    "area", "base", "basefont", "br", "col", "embed", "frame", "hr", "img",
    "input", "isindex", "link", "meta", "param", "source", "spacer", "track", "wbr",
}
BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "center", "dd", "div", "dl",
    "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2",
    "h3", "h4", "h5", "h6", "header", "li", "main", "nav", "ol", "p", "pre",
    "section", "table", "td", "th", "tr", "ul",
}
# Tags whose opening implicitly closes a still-open sibling (tag-soup reality
# of pre-XHTML pages: <p> and <li> were rarely closed).
IMPLICIT_CLOSE = {
    "p": {"p"},
    "li": {"li"},
    "dd": {"dd", "dt"},
    "dt": {"dd", "dt"},
    "td": {"td", "th"},
    "th": {"td", "th"},
    "tr": {"tr", "td", "th"},
    "option": {"option"},
}
HTML5_SEMANTIC_TAGS = {
    "article", "aside", "figcaption", "figure", "footer", "header", "main",
    "nav", "section", "time",
}
LEGACY_TAGS = {
    "applet", "basefont", "big", "blink", "center", "font", "frame",
    "frameset", "isindex", "layer", "marquee", "noframes", "spacer", "tt",
}
LEGACY_ATTRS = {"bgcolor", "background", "vlink", "alink", "leftmargin", "topmargin"}
SEARCH_INPUT_NAMES = {"q", "s", "query", "search", "keywords", "zoekterm"}
PAGINATION_TEXT = {
    "next", "previous", "prev", "older", "newer", "more", "last", "first",
    "next page", "older posts", "newer posts", "»", "›", "«", "‹",
    "volgende", "vorige",  # frequent in the Dutch-language target corpus
}

# Client-side framework / hydration markers, matched on the raw HTML string.
FRAMEWORK_MARKERS = {
    "nextjs": re.compile(r"__NEXT_DATA__"),
    "react": re.compile(r"data-react(root|id|-helmet)"),
    "angular": re.compile(r"\bng-(app|version|controller)"),
    "vue": re.compile(r"\bdata-v-[0-9a-f]{8}\b|__NUXT__"),
    "gatsby": re.compile(r"___gatsby"),
    "svelte": re.compile(r"\bsvelte-[0-9a-z]{6}\b"),
    "ember": re.compile(r"\bid=\"ember\d+\""),
    "turbo": re.compile(r"\bdata-turbo\b"),
}
# CMS/platform path fingerprints — strong category hints (blog/forum/wiki).
PLATFORM_MARKERS = {
    "wordpress": re.compile(r"/wp-(content|includes)/"),
    "blogger": re.compile(r"blogger\.com|blogspot\.\w+/feeds", re.I),
    "mediawiki": re.compile(r"/skins/(monobook|vector)|mw-content-text"),
    "phpbb": re.compile(r"viewtopic\.php|phpbb", re.I),
    "vbulletin": re.compile(r"vbulletin", re.I),
    "drupal": re.compile(r"/sites/(default|all)/(files|themes|modules)/"),
    "typepad": re.compile(r"typepad\.com", re.I),
    "livejournal": re.compile(r"livejournal\.com", re.I),
    "geocities": re.compile(r"geocities", re.I),
}

_CHARSET_RE = re.compile(rb"""charset\s*=\s*["']?\s*([a-zA-Z0-9_\-]+)""")


def decode_html(raw: bytes) -> str:
    """Decode raw page bytes: declared charset first, then utf-8, then
    windows-1252 (the de-facto encoding of the 1990s web), never raising."""
    head = raw[:4096]
    match = _CHARSET_RE.search(head)
    encodings = []
    if match:
        encodings.append(match.group(1).decode("ascii", "ignore"))
    encodings += ["utf-8", "windows-1252"]
    for enc in encodings:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


@dataclass
class PageFeatures:
    """Shallow structural signals for one HTML document."""

    # Text mass
    total_text_chars: int = 0
    anchor_text_chars: int = 0
    table_text_chars: int = 0
    li_text_chars: int = 0
    script_chars: int = 0
    # Blocks (contiguous text runs between block-level boundaries)
    n_blocks: int = 0
    largest_block_chars: int = 0
    blocks_over_200: int = 0
    # Element counts
    n_anchors: int = 0
    n_images: int = 0
    n_forms: int = 0
    n_inputs: int = 0
    search_inputs: int = 0
    p_count: int = 0
    li_count: int = 0
    h1_count: int = 0
    h2_count: int = 0
    h3_count: int = 0
    table_count: int = 0
    div_count: int = 0
    script_count: int = 0
    # Era markers
    doctype: str = ""
    legacy_tag_count: int = 0
    legacy_attr_count: int = 0
    font_count: int = 0
    has_frameset: bool = False
    frame_count: int = 0
    html5_tag_count: int = 0
    stylesheet_links: int = 0
    style_tags: int = 0
    style_attr_count: int = 0
    meta_viewport: bool = False
    meta_generator: str = ""
    meta_og_type: str = ""
    has_og_title: bool = False
    framework_markers: list[str] = field(default_factory=list)
    platform_markers: list[str] = field(default_factory=list)
    # Repetition / navigation signals
    repeated_block_class_max: int = 0
    pagination_hints: int = 0
    rel_next: bool = False
    # Snippets
    title: str = ""
    first_h1: str = ""
    first_text: str = ""
    # Bookkeeping
    parse_error: bool = False
    # Layout fingerprint (signed feature hashing over tag bigrams + classes)
    fingerprint: list[float] = field(default_factory=list)

    @property
    def link_density(self) -> float:
        return self.anchor_text_chars / self.total_text_chars if self.total_text_chars else 0.0

    @property
    def table_text_ratio(self) -> float:
        return self.table_text_chars / self.total_text_chars if self.total_text_chars else 0.0

    @property
    def li_text_ratio(self) -> float:
        return self.li_text_chars / self.total_text_chars if self.total_text_chars else 0.0

    @property
    def script_ratio(self) -> float:
        denominator = self.script_chars + self.total_text_chars
        return self.script_chars / denominator if denominator else 0.0

    def to_dict(self) -> dict:
        data = dict(self.__dict__)
        data["link_density"] = round(self.link_density, 4)
        data["table_text_ratio"] = round(self.table_text_ratio, 4)
        data["li_text_ratio"] = round(self.li_text_ratio, 4)
        data["script_ratio"] = round(self.script_ratio, 4)
        return data


class _FeatureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.features = PageFeatures()
        self.structure_bag: Counter[str] = Counter()
        self._stack: list[str] = []
        self._raw_depth = 0  # inside script/style/noscript
        self._anchor_depth = 0
        self._table_depth = 0
        self._li_depth = 0
        self._in_title = False
        self._h1_open = False
        self._title_parts: list[str] = []
        self._h1_parts: list[str] = []
        self._anchor_parts: list[str] = []
        self._block_len = 0
        self._block_class_counts: Counter[str] = Counter()

    # -- block bookkeeping ---------------------------------------------------

    def _flush_block(self) -> None:
        if self._block_len <= 0:
            return
        f = self.features
        f.n_blocks += 1
        f.largest_block_chars = max(f.largest_block_chars, self._block_len)
        if self._block_len >= 200:
            f.blocks_over_200 += 1
        self._block_len = 0

    # -- parser events ---------------------------------------------------------

    def handle_decl(self, decl: str) -> None:
        if not self.features.doctype:
            self.features.doctype = decl.strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        f = self.features
        for closer in IMPLICIT_CLOSE.get(tag, ()):
            if self._stack and self._stack[-1] == closer:
                self._leave(self._stack[-1])
        parent = self._stack[-1] if self._stack else "^"
        self.structure_bag[f"t:{parent}>{tag}"] += 1

        attr_map: dict[str, str] = {}
        for name, value in attrs:
            if name and name not in attr_map:
                attr_map[name] = value or ""

        self._count_tag(tag, attr_map)

        if tag in BLOCK_TAGS:
            self._flush_block()
            for token in attr_map.get("class", "").split():
                self.structure_bag[f"c:{token}"] += 1
                self._block_class_counts[token] += 1
        if "style" in attr_map:
            f.style_attr_count += 1
        if attr_map.keys() & LEGACY_ATTRS:
            f.legacy_attr_count += 1

        if tag not in VOID_TAGS:
            self._stack.append(tag)
            if tag in ("script", "style", "noscript"):
                self._raw_depth += 1
            elif tag == "a":
                self._anchor_depth += 1
                self._anchor_parts = []
            elif tag == "table":
                self._table_depth += 1
            elif tag == "li":
                self._li_depth += 1
            elif tag == "title":
                self._in_title = True
            elif tag == "h1":
                self._h1_open = f.h1_count == 1  # capture only the first h1

    def _count_tag(self, tag: str, attr_map: dict[str, str]) -> None:
        f = self.features
        if tag == "a":
            f.n_anchors += 1
            if attr_map.get("rel", "").lower() == "next":
                f.rel_next = True
        elif tag == "img":
            f.n_images += 1
        elif tag == "form":
            f.n_forms += 1
        elif tag == "input":
            f.n_inputs += 1
            name = attr_map.get("name", "").lower()
            if name in SEARCH_INPUT_NAMES or attr_map.get("type", "").lower() == "search":
                f.search_inputs += 1
        elif tag == "p":
            f.p_count += 1
        elif tag == "li":
            f.li_count += 1
        elif tag == "h1":
            f.h1_count += 1
        elif tag == "h2":
            f.h2_count += 1
        elif tag == "h3":
            f.h3_count += 1
        elif tag == "table":
            f.table_count += 1
        elif tag == "div":
            f.div_count += 1
        elif tag == "script":
            f.script_count += 1
        elif tag == "style":
            f.style_tags += 1
        elif tag == "frameset":
            f.has_frameset = True
        elif tag == "frame":
            f.frame_count += 1
        elif tag == "link":
            if "stylesheet" in attr_map.get("rel", "").lower():
                f.stylesheet_links += 1
        elif tag == "meta":
            self._count_meta(attr_map)
        if tag == "font":
            f.font_count += 1
        if tag in LEGACY_TAGS:
            f.legacy_tag_count += 1
        if tag in HTML5_SEMANTIC_TAGS:
            f.html5_tag_count += 1

    def _count_meta(self, attr_map: dict[str, str]) -> None:
        f = self.features
        key = (attr_map.get("name") or attr_map.get("property") or "").lower()
        content = attr_map.get("content", "")
        if key == "viewport":
            f.meta_viewport = True
        elif key == "generator" and not f.meta_generator:
            f.meta_generator = content[:80]
        elif key == "og:type" and not f.meta_og_type:
            f.meta_og_type = content[:40].lower()
        elif key == "og:title":
            f.has_og_title = True

    def _leave(self, tag: str) -> None:
        if tag in self._stack:
            # Pop up to and including the nearest matching open tag.
            while self._stack:
                popped = self._stack.pop()
                self._on_close(popped)
                if popped == tag:
                    break

    def _on_close(self, tag: str) -> None:
        f = self.features
        if tag in ("script", "style", "noscript"):
            self._raw_depth = max(0, self._raw_depth - 1)
        elif tag == "a":
            self._anchor_depth = max(0, self._anchor_depth - 1)
            text = " ".join("".join(self._anchor_parts).split()).lower()
            if text and (text in PAGINATION_TEXT or (text.isdigit() and len(text) <= 3)):
                f.pagination_hints += 1
        elif tag == "table":
            self._table_depth = max(0, self._table_depth - 1)
        elif tag == "li":
            self._li_depth = max(0, self._li_depth - 1)
        elif tag == "title":
            self._in_title = False
            if not f.title:
                f.title = " ".join("".join(self._title_parts).split())[:300]
        elif tag == "h1":
            if self._h1_open and not f.first_h1:
                f.first_h1 = " ".join("".join(self._h1_parts).split())[:300]
            self._h1_open = False
        if tag in BLOCK_TAGS:
            self._flush_block()

    def handle_endtag(self, tag: str) -> None:
        self._leave(tag)

    def handle_data(self, data: str) -> None:
        f = self.features
        if self._raw_depth:
            f.script_chars += len(data)
            return
        if self._in_title:
            self._title_parts.append(data)
            return
        text = " ".join(data.split())
        if not text:
            return
        n = len(text)
        f.total_text_chars += n
        if self._anchor_depth:
            f.anchor_text_chars += n
            self._anchor_parts.append(data)
        if self._table_depth:
            f.table_text_chars += n
        if self._li_depth:
            f.li_text_chars += n
        if self._h1_open:
            self._h1_parts.append(data)
        self._block_len += n
        if len(f.first_text) < 400:
            f.first_text = (f.first_text + " " + text).strip()[:400]

    def close(self) -> None:
        super().close()
        self._flush_block()
        counts = self._block_class_counts
        if counts:
            self.features.repeated_block_class_max = max(counts.values())


def _hash_bucket(key: str) -> tuple[int, int]:
    import hashlib

    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    bucket = value % FINGERPRINT_DIMS
    sign = 1 if (value >> 63) & 1 else -1
    return bucket, sign


def structure_fingerprint(bag: Counter, dims: int = FINGERPRINT_DIMS) -> list[float]:
    """Signed feature hashing of the structure bag, L2-normalized.

    Log-damped counts so one 500-row table doesn't drown the rest of the
    layout signature.
    """
    vector = [0.0] * dims
    for key, count in bag.items():
        bucket, sign = _hash_bucket(key)
        vector[bucket % dims] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [round(v / norm, 5) for v in vector]
    return vector


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def extract_features(html: str | bytes) -> PageFeatures:
    """Parse HTML into PageFeatures (never raises; sets parse_error instead)."""
    if isinstance(html, bytes):
        html = decode_html(html)
    if len(html) > MAX_PARSE_BYTES:
        logger.warning("html_features: truncating oversized document (%d chars)", len(html))
        html = html[:MAX_PARSE_BYTES]

    parser = _FeatureParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # html.parser almost never raises, but never crash an eval run
        logger.exception("html_features: parser failed, returning partial features")
        parser.features.parse_error = True

    features = parser.features
    for name, pattern in FRAMEWORK_MARKERS.items():
        if pattern.search(html):
            features.framework_markers.append(name)
    for name, pattern in PLATFORM_MARKERS.items():
        if pattern.search(html):
            features.platform_markers.append(name)
    features.fingerprint = structure_fingerprint(parser.structure_bag)
    return features
