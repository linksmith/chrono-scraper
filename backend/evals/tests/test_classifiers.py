from evals.classify_era import classify_era, doctype_flavor
from evals.classify_page_type import classify_page_type
from evals.html_features import extract_features
from evals.tests.fixtures import (
    HTML_1996_PERSONAL,
    HTML_2003_TABLE_NEWS,
    HTML_2007_BLOG,
    HTML_2020_ARTICLE,
    HTML_ERROR_404,
    HTML_FORUM_THREAD,
    HTML_FRAMESET,
    HTML_LIST_CATEGORY,
    HTML_PORTAL_HOME,
    HTML_SEARCH_RESULTS,
    HTML_SPA_SHELL,
)


def _era(html, year=None):
    return classify_era(extract_features(html), snapshot_year=year)


def _page_type(html, url=""):
    return classify_page_type(extract_features(html), url)


# --- era ---------------------------------------------------------------------

def test_doctype_flavor():
    assert doctype_flavor("DOCTYPE html") == "html5"
    assert doctype_flavor('DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"') == "html4"
    assert doctype_flavor('DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"') == "xhtml"
    assert doctype_flavor("") == "none"


def test_era_1996_personal():
    assert _era(HTML_1996_PERSONAL).label == "early_static"


def test_era_frameset():
    assert _era(HTML_FRAMESET).label == "early_static"


def test_era_2003_table_layout_despite_stylesheet():
    assert _era(HTML_2003_TABLE_NEWS).label == "table_layout"


def test_era_2007_css_layout():
    assert _era(HTML_2007_BLOG).label == "css_layout"


def test_era_2020_html5():
    assert _era(HTML_2020_ARTICLE).label == "html5_semantic"


def test_era_spa_shell():
    result = _era(HTML_SPA_SHELL)
    assert result.label == "spa_hydrated"
    assert result.confidence >= 0.9  # framework marker is near-conclusive


def test_era_by_structure_not_capture_year():
    # A 1996-style page captured in 2020 must still classify early_static.
    assert _era(HTML_1996_PERSONAL, year=2020).label == "early_static"


# --- page type -------------------------------------------------------------------

def test_article_pages_classify_article():
    assert _page_type(HTML_2020_ARTICLE, "https://news.example.com/2020/05/12/archive-web").label == "article"
    assert _page_type(HTML_2003_TABLE_NEWS, "http://news.example.com/1234567.stm").label == "article"
    assert _page_type(HTML_2007_BLOG, "http://blog.example.com/2007/06/why-i-switched-to-linux/").label == "article"


def test_1996_essay_classifies_article_without_url_hints():
    assert _page_type(HTML_1996_PERSONAL, "http://www.geocities.com/Area51/1234/canyon.html").label == "article"


def test_category_page_classifies_list():
    result = _page_type(HTML_LIST_CATEGORY, "https://news.example.com/category/news/?page=2")
    assert result.label == "list"


def test_list_detected_even_without_url_signal():
    result = _page_type(HTML_LIST_CATEGORY, "")
    assert result.label == "list"


def test_search_results_classify_search():
    result = _page_type(HTML_SEARCH_RESULTS, "https://example.com/search?q=space+jam")
    assert result.label == "search"


def test_error_page():
    assert _page_type(HTML_ERROR_404, "https://example.com/gone").label == "error"


def test_spa_shell_is_other():
    assert _page_type(HTML_SPA_SHELL, "https://twitter.com/user/status/123").label == "other"


def test_portal_home():
    result = _page_type(HTML_PORTAL_HOME, "https://portal.example.com/")
    assert result.label in ("home", "list")  # portal fronts sit on this boundary
    assert result.label != "article"


def test_forum_thread_classifies_article_via_prose_signal():
    # Discussion pages are canonical content even though they have repeated
    # post blocks; the substantial-prose signal must recover them.
    result = _page_type(HTML_FORUM_THREAD, "https://forum.example.com/viewtopic.php?t=42")
    assert result.label == "article"
    assert any("substantial_prose" in s for s in result.signals)


def test_forum_thread_article_even_without_url_hint():
    assert _page_type(HTML_FORUM_THREAD, "").label == "article"


def test_hackernews_and_slashdot_url_patterns_vote_article():
    # A modest-prose page whose URL is a known content permalink should get an
    # article URL vote (regression for the added HN/Slashdot patterns).
    for url in (
        "https://news.ycombinator.com/item?id=13136823",
        "http://slashdot.org/article.pl?05/16/1155232",
    ):
        result = _page_type(HTML_2003_TABLE_NEWS, url)
        assert any("article_url_pattern" in s for s in result.signals)


def test_prose_signal_does_not_flip_real_list_pages():
    # Precision guard: link-dominated list pages must stay 'list' despite the
    # new prose signal (their link density is above the guard).
    assert _page_type(HTML_LIST_CATEGORY, "https://news.example.com/category/news/?page=2").label == "list"
    assert _page_type(HTML_SEARCH_RESULTS, "https://example.com/search?q=x").label == "search"


def test_scores_and_signals_are_exposed():
    result = _page_type(HTML_LIST_CATEGORY, "https://news.example.com/category/news/")
    assert set(result.scores) == {"article", "list", "search", "home", "error", "other"}
    assert any("list:" in s for s in result.signals)
