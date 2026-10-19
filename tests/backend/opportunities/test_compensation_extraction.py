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


H = CompensationPeriod.HOUR


@pytest.mark.parametrize(
    ("text", "currency", "period", "minimum", "maximum"),
    [
        ("Annual salary: $120,000", None, Y, 120000, None),
        ("Monthly salary of R$ 8.000", "BRL", M, 8000, None),
        ("Hourly rate: USD 50", "USD", H, 50, None),
        ("Salário: 5 a 7 mil por mês", None, M, 5000, 7000),
        ("Salario: 5.000,00 ao mês", None, M, 5000, None),
        ("R$ 10 por hora", "BRL", H, 10, None),
        ("R$ 5.000 ao mês", "BRL", M, 5000, None),
        ("Salary: 5-10k", None, None, 5000, 10000),
        ("Pagamos valores mensais de R$ 5.000", "BRL", M, 5000, None),
        ("Bônus anuais de R$ 5.000", "BRL", Y, 5000, None),
        ("We meet weekly. Salary: R$ 5.000", "BRL", None, 5000, None),
    ],
)
def test_period_read_from_short_prefix_and_salary_words(
    text, currency, period, minimum, maximum
):
    result = extract_compensation({}, text, source_type="test")

    assert result is not None
    assert result.currency == currency
    assert result.period == period
    assert result.minimum == Decimal(minimum)
    assert result.maximum == (Decimal(maximum) if maximum is not None else None)


def test_bare_number_range_without_salary_word_is_ignored():
    assert extract_compensation({}, "Founded 2020-2k", source_type="test") is None
