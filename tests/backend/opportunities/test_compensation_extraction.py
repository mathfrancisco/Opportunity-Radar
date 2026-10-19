from decimal import Decimal

import pytest

from opportunity_radar.opportunities.domain import (
    CompensationPeriod,
    extract_compensation,
)

M = CompensationPeriod.MONTH
Y = CompensationPeriod.YEAR


@pytest.mark.parametrize(
    ("text", "currency", "period", "minimum", "maximum"),
    [
        pytest.param(
            "Salário: R$ 5.000 a R$ 7.000 por mês", "BRL", M, 5000, 7000, id="h1-h2-h3"
        ),
        pytest.param("Remuneração R$ 8.000,00 mensal", "BRL", M, 8000, None, id="h1-h2"),
        pytest.param("R$5k-7k/mês", "BRL", M, 5000, 7000, id="h1-h2-k"),
        pytest.param("Faixa salarial: 5 a 7 mil reais", "BRL", None, 5000, 7000, id="h4"),
        pytest.param("5.000 BRL/month", "BRL", M, 5000, None, id="h3"),
        pytest.param("$120k - $150k per year", None, Y, 120000, 150000, id="control"),
    ],
)
def test_text_compensation_brl_and_portuguese(
    text, currency, period, minimum, maximum
):
    result = extract_compensation({}, text, source_type="test")

    assert result is not None
    assert result.currency == currency
    assert result.period == period
    assert result.minimum == Decimal(minimum)
    assert result.maximum == (Decimal(maximum) if maximum is not None else None)


@pytest.mark.parametrize(
    "text",
    [
        "We work a 4-day week. Salary: 120k",
        "Salary: 120k. Our team holds weekly 1:1 meetings with your lead.",
    ],
)
def test_unrelated_week_word_is_not_a_weekly_period(text):
    result = extract_compensation({}, text, source_type="test")

    assert result is not None
    assert result.period != CompensationPeriod.WEEK


def test_structured_salary_range_keeps_brl_and_month():
    result = extract_compensation(
        {
            "salaryRange": {
                "min": 5000,
                "max": 7000,
                "currency": "BRL",
                "interval": "per-month-salary",
            }
        },
        None,
        source_type="test",
    )

    assert result is not None
    assert result.currency == "BRL"
    assert result.period == CompensationPeriod.MONTH
