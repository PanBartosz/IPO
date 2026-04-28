from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Iterable


ALLOWED_SCORE_VALUES: tuple[Decimal, ...] = (
    Decimal("1"),
    Decimal("2"),
    Decimal("3"),
    Decimal("4"),
    Decimal("5"),
    Decimal("6"),
    Decimal("7"),
    Decimal("7.5"),
    Decimal("8"),
    Decimal("8.5"),
    Decimal("9"),
    Decimal("9.5"),
    Decimal("10"),
)

SCORE_VALIDATION_MESSAGE = (
    "Score must be one of: 1, 2, 3, 4, 5, 6, 7, 7.5, 8, 8.5, 9, 9.5, 10."
)


def format_score_value(value: Decimal | float | int | str | None) -> str:
    if value is None:
        return ""
    decimal_value = Decimal(str(value))
    if decimal_value == decimal_value.to_integral_value():
        return str(decimal_value.quantize(Decimal("1")))
    return str(decimal_value.normalize())


def score_choices(*, include_blank: bool = True) -> list[tuple[str, str]]:
    choices = [(format_score_value(value), format_score_value(value)) for value in ALLOWED_SCORE_VALUES]
    if include_blank:
        return [("", "Select score")] + choices
    return choices


def parse_score_value(raw_value: Decimal | float | int | str | None) -> tuple[Decimal | None, str | None]:
    if raw_value is None:
        return None, None
    if isinstance(raw_value, str) and raw_value.strip() == "":
        return None, None

    try:
        score = Decimal(str(raw_value).strip())
    except (InvalidOperation, ValueError):
        return None, SCORE_VALIDATION_MESSAGE

    if score not in ALLOWED_SCORE_VALUES:
        return None, SCORE_VALIDATION_MESSAGE
    return score, None


def closest_allowed_score(
    raw_value: float | int | Decimal,
    *,
    min_score: float | int | Decimal | None = None,
    max_score: float | int | Decimal | None = None,
) -> float:
    value = Decimal(str(raw_value))
    candidates: Iterable[Decimal] = ALLOWED_SCORE_VALUES
    if min_score is not None:
        min_value = Decimal(str(min_score))
        candidates = [score for score in candidates if score >= min_value]
    if max_score is not None:
        max_value = Decimal(str(max_score))
        candidates = [score for score in candidates if score <= max_value]

    candidate_list = list(candidates)
    if not candidate_list:
        raise ValueError("No statutory score values are available in the requested range.")
    return float(min(candidate_list, key=lambda score: (abs(score - value), score)))
