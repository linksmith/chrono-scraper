from evals.textnorm import body_key, normalize_text, shingle_counts, shingles, tokenize


def test_normalize_collapses_whitespace_and_case():
    assert normalize_text("Hello\n\n  WORLD\t!") == "hello world !"


def test_normalize_nfkc():
    # full-width characters normalize to ASCII under NFKC
    assert normalize_text("ＨＥＬＬＯ") == "hello"


def test_tokenize_ignores_punctuation():
    assert tokenize("Hello, World! It's 1996.") == ["hello", "world", "it", "s", "1996"]


def test_body_key_invariant_to_formatting():
    a = body_key("Hello,   World!\n\nThis is FINE.")
    b = body_key("hello world this is fine")
    assert a == b


def test_body_key_differs_for_different_content():
    assert body_key("some article text") != body_key("other article text")


def test_shingles_short_text_yields_single_shingle():
    assert list(shingles(["a", "b"], 4)) == ["a b"]


def test_shingles_sliding_window():
    assert list(shingles(["a", "b", "c", "d"], 2)) == ["a b", "b c", "c d"]


def test_shingle_counts_multiset():
    counts = shingle_counts("a b a b a b", 2)
    assert counts["a b"] == 3
    assert counts["b a"] == 2
