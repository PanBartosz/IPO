import pytest

from ipo_app.scoring import closest_allowed_score, parse_score_value, score_choices


@pytest.mark.parametrize("raw_value", ["1", "6", "7", "7.5", "8.00", "9.5", "10"])
def test_parse_score_value_accepts_statutory_scores(raw_value):
    score, error = parse_score_value(raw_value)

    assert error is None
    assert score is not None


@pytest.mark.parametrize("raw_value", ["0", "4.5", "6.5", "7.76", "10.5", "not-a-number"])
def test_parse_score_value_rejects_non_statutory_scores(raw_value):
    score, error = parse_score_value(raw_value)

    assert score is None
    assert error is not None


def test_score_choices_use_public_statutory_grid():
    values = [value for value, _label in score_choices(include_blank=False)]

    assert values == ["1", "2", "3", "4", "5", "6", "7", "7.5", "8", "8.5", "9", "9.5", "10"]


def test_closest_allowed_score_uses_statutory_grid():
    assert closest_allowed_score(7.76, min_score=1, max_score=10) == 8.0
    assert closest_allowed_score(4.7, min_score=4.5, max_score=9.5) == 5.0
