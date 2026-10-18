from evals.html_features import cosine, decode_html, extract_features
from evals.tests.fixtures import (
    HTML_1996_PERSONAL,
    HTML_2003_TABLE_NEWS,
    HTML_2020_ARTICLE,
    HTML_FRAMESET,
    HTML_LIST_CATEGORY,
    HTML_SPA_SHELL,
)


def test_link_density_computation():
    html = "<html><body><p>xxxxx yyyyy zzzzz</p><a href='#'>link</a></body></html>"
    features = extract_features(html)
    assert features.total_text_chars == 21  # 17 body chars + 4 anchor chars
    assert features.anchor_text_chars == 4
    assert 0.18 < features.link_density < 0.20


def test_legacy_markers_on_1996_page():
    features = extract_features(HTML_1996_PERSONAL)
    assert features.font_count >= 2
    assert features.legacy_attr_count >= 1
    assert features.doctype == ""
    assert features.stylesheet_links == 0
    assert features.table_text_ratio > 0.5
    assert features.title == "My Trip to the Grand Canyon"


def test_table_news_has_css_but_table_layout():
    features = extract_features(HTML_2003_TABLE_NEWS)
    assert features.stylesheet_links == 1
    assert features.table_text_ratio > 0.5
    assert features.p_count >= 3


def test_modern_article_markers():
    features = extract_features(HTML_2020_ARTICLE)
    assert features.doctype.lower() == "doctype html"
    assert features.html5_tag_count >= 4  # header/nav/main/article/footer
    assert features.meta_viewport is True
    assert features.meta_og_type == "article"
    assert features.h1_count == 1
    assert features.first_h1.startswith("Inside the Effort")
    assert features.link_density < 0.2


def test_spa_shell_detection():
    features = extract_features(HTML_SPA_SHELL)
    assert "nextjs" in features.framework_markers
    assert features.total_text_chars < 50
    assert features.script_ratio > 0.5


def test_list_page_repetition_and_pagination():
    features = extract_features(HTML_LIST_CATEGORY)
    assert features.repeated_block_class_max >= 12
    assert features.pagination_hints >= 3
    assert features.rel_next is True
    assert features.n_anchors >= 25
    assert features.link_density > 0.5


def test_frameset():
    features = extract_features(HTML_FRAMESET)
    assert features.has_frameset is True
    assert features.frame_count == 2


def test_script_content_not_counted_as_text():
    features = extract_features(HTML_SPA_SHELL)
    assert features.script_chars > 100
    # the JSON blob inside <script> must not leak into text totals
    assert features.total_text_chars < 50


def test_fingerprint_properties():
    article = extract_features(HTML_2020_ARTICLE).fingerprint
    list_page = extract_features(HTML_LIST_CATEGORY).fingerprint
    assert len(article) == 64
    assert cosine(article, article) > 0.999
    assert cosine(article, list_page) < 0.98  # different layouts differ


def test_decode_html_declared_charset():
    raw = '<html><head><meta charset="windows-1252"></head><body>caf\xe9</body></html>'.encode(
        "windows-1252"
    )
    assert "café" in decode_html(raw)


def test_decode_html_survives_garbage():
    assert decode_html(b"\xff\xfe\x00garbage\x9d") != ""


def test_parser_survives_tag_soup():
    soup = "<html><p>text<td>more</a></b><p unclosed<div>rest"
    features = extract_features(soup)
    assert features.total_text_chars > 0
