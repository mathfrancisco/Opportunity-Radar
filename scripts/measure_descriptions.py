"""Measure how long the collection's descriptions are, before and after cleaning.

    python scripts/measure_descriptions.py                 # Markdown report on stdout
    python scripts/measure_descriptions.py --json          # same numbers, machine-readable

Card F16-05: the prompt budget is sized from the collection, not from a guess. The report
goes to `docs/pesquisas/`. Read-only; nothing is written to the database.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.matching.text import (
    CLEANER_VERSION,
    DEFAULT_TOKENS_PER_CHAR,
    clean_description,
    estimate_tokens,
    prompt_budget,
)
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine

_PERCENTILES = (50, 75, 90, 95, 99)


def _distribution(lengths: Sequence[int]) -> dict[str, int]:
    if not lengths:
        return {}
    ordered = sorted(lengths)
    cuts = statistics.quantiles(ordered, n=100, method="inclusive") if len(ordered) > 1 else []
    result = {f"p{p}": round(cuts[p - 1]) if cuts else ordered[0] for p in _PERCENTILES}
    result["max"] = ordered[-1]
    return result


def measure(session: Session, *, num_ctx: int, num_predict: int) -> dict[str, Any]:
    descriptions = list(
        session.scalars(
            select(OpportunityModel.description).where(
                OpportunityModel.lifecycle_status != "REJECTED"
            )
        )
    )
    present = [text for text in descriptions if text]
    raw = [len(text) for text in present]
    cleaned = [len(clean_description(text)) for text in present]
    budget = prompt_budget(num_ctx, num_predict)
    tokens = [estimate_tokens(chars, DEFAULT_TOKENS_PER_CHAR) for chars in cleaned]
    return {
        "measured_at": datetime.now(UTC).isoformat(),
        "cleaner_version": CLEANER_VERSION,
        "opportunities": len(descriptions),
        "with_description": len(present),
        "raw_chars": _distribution(raw),
        "clean_chars": _distribution(cleaned),
        "clean_tokens_estimate": _distribution(tokens),
        "tokens_per_char": DEFAULT_TOKENS_PER_CHAR,
        "prompt_budget_tokens": budget,
        "over_budget_alone": sum(1 for count in tokens if count > budget),
        "saved_by_cleaning": 1 - sum(cleaned) / sum(raw) if sum(raw) else None,
    }


def _markdown(report: dict[str, Any]) -> str:
    rows = ["| Medida | " + " | ".join(f"p{p}" for p in _PERCENTILES) + " | máx |"]
    rows.append("| --- |" + " ---: |" * (len(_PERCENTILES) + 1))
    for key, label in (
        ("raw_chars", "Caracteres, bruto"),
        ("clean_chars", "Caracteres, limpo"),
        ("clean_tokens_estimate", "Tokens estimados, limpo"),
    ):
        values = report[key]
        cells = [str(values.get(f"p{p}", "—")) for p in _PERCENTILES] + [
            str(values.get("max", "—"))
        ]
        rows.append(f"| {label} | " + " | ".join(cells) + " |")
    saved = report["saved_by_cleaning"]
    return "\n".join(
        [
            "# Tamanho das descrições do acervo",
            "",
            f"Medido em {report['measured_at']} com `{report['cleaner_version']}` e razão "
            f"inicial de {report['tokens_per_char']} token/caractere.",
            "",
            f"- Oportunidades não rejeitadas: {report['opportunities']}",
            f"- Com descrição: {report['with_description']}",
            f"- Orçamento do prompt: {report['prompt_budget_tokens']} tokens",
            f"- Descrições que sozinhas passam do orçamento: {report['over_budget_alone']}",
            "- Redução pelo limpador: "
            + ("—" if saved is None else f"{saved * 100:.1f}% dos caracteres"),
            "",
            *rows,
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args(argv)

    settings = Settings()  # type: ignore[call-arg]  # values come from the environment
    engine = create_database_engine(settings.database_url)
    with Session(engine) as session:
        report = measure(
            session, num_ctx=settings.ollama_num_ctx, num_predict=settings.ollama_num_predict
        )
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else _markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
