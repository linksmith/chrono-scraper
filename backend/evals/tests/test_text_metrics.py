import pytest

from evals.text_metrics import date_match, field_score, score_sample, shingle_f1, token_f1


def test_token_f1_partial_overlap():
    result = token_f1("a b c d", "a b c")
    assert result.precision == 1.0
    assert result.recall == 0.75
    assert result.f1 == pytest.approx(0.857, abs=1e-3)


def test_token_f1_is_multiset_aware():
    # duplicated tokens must not be double-credited
    result = token_f1("word word other", "word")
    assert result.precision == 1.0
    assert result.recall == pytest.approx(1 / 3)


def test_shingle_f1_orders_matter():
    perfect = shingle_f1("the quick brown fox jumps", "the quick brown fox jumps", n=2)
    scrambled = shingle_f1("the quick brown fox jumps", "jumps fox brown quick the", n=2)
    assert perfect.f1 == 1.0
    assert scrambled.f1 < 0.5
    # but token F1 forgives the scramble entirely
    assert token_f1("the quick brown fox jumps", "jumps fox brown quick the").f1 == 1.0


def test_empty_conventions():
    assert token_f1("", "").f1 == 1.0
    assert token_f1("something", "").f1 == 0.0
    assert token_f1("", "something").f1 == 0.0


def test_field_score_normalized_exact():
    score = field_score("The  Title", "the title")
    assert score.exact is True
    assert score.similarity == 1.0


def test_field_score_partial():
    score = field_score("Council approves bridge plan", "Council approves bridge")
    assert score.exact is False
    assert 0.5 < score.token_f1 < 1.0


def test_date_match_tolerance():
    assert date_match("2020-01-01", "2020-01-02", tolerance_days=1) is True
    assert date_match("2020-01-01", "2020-01-05", tolerance_days=1) is False
    assert date_match("2020-01-01T15:30:00Z", "2020-01-01") is True
    assert date_match(None, "2020-01-01") is None
    assert date_match("2020-01-01", "not a date") is None


def test_score_sample_end_to_end():
    result = score_sample(
        gold_body="alpha beta gamma delta epsilon zeta",
        pred_body="alpha beta gamma delta",
        gold_title="A Title",
        pred_title="A Title",
        gold_date="2021-06-01",
        pred_date="2021-06-01",
    )
    assert result.body_token.recall == pytest.approx(4 / 6)
    assert result.title.exact is True
    assert result.date_ok is True
    assert result.gold_tokens == 6
    assert result.pred_tokens == 4
