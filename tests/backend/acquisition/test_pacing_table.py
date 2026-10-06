"""F52-08: the pacing table in docs/17-fontes-coletores.md covers every collector type and
no hourly ceiling in code sits below the peak measured there.

`docs/` is not part of the test image, so the tests that read it skip when the file is
absent, the same gate `test_content_rule_activation.py` uses for the gold file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.scheduling import DEFAULT_HOST_REQUESTS_CEILING
from opportunity_radar.acquisition.service import DEFAULT_HOST_CEILING_BY_SOURCE_TYPE
from opportunity_radar.platform.config import Settings

DOC = Path(__file__).resolve().parents[3] / "docs" / "17-fontes-coletores.md"
needs_doc = pytest.mark.skipif(not DOC.exists(), reason="docs/ is not part of the test image")

#: Workday stays as it is whatever the numbers say (SPEC 52, F52-08): its measured peak is
#: reported in the table and in the card, not pinned here.
EXEMPT_FROM_PEAK_CHECK = frozenset({"workday"})


def _pacing_rows(text: str) -> dict[str, dict[str, str]]:
    """Rows of the table under `### 6.3 Ritmo por fornecedor`, keyed by source type."""
    section = text.split("### 6.3 Ritmo por fornecedor", 1)[1]
    lines = [line.strip() for line in section.splitlines()]
    header = next(line for line in lines if line.startswith("| Tipo |"))
    names = [cell.strip() for cell in header.strip("|").split("|")]
    rows: dict[str, dict[str, str]] = {}
    for line in lines[lines.index(header) + 2 :]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        match = re.fullmatch(r"`([a-z_]+)`", cells[0])
        assert match, f"first cell is not a source type: {cells[0]!r}"
        rows[match.group(1)] = dict(zip(names, cells, strict=True))
    return rows


def _as_int(cell: str) -> int | None:
    return None if cell == "—" else int(cell)


def _collector_types() -> set[str]:
    registry = build_collector_registry(greenhouse_base_url="http://unused")
    return set(registry._collectors)  # noqa: SLF001 - no public listing of the types


def _code_ceiling(source_type: str) -> int:
    return Settings().host_request_ceiling_map.get(source_type, DEFAULT_HOST_REQUESTS_CEILING)


@needs_doc
def test_every_collector_type_has_a_pacing_row() -> None:
    rows = _pacing_rows(DOC.read_text(encoding="utf-8"))

    assert _collector_types() - set(rows) == set()
    assert set(rows) - _collector_types() == set()


@needs_doc
def test_pacing_table_ceiling_matches_the_code() -> None:
    rows = _pacing_rows(DOC.read_text(encoding="utf-8"))

    for source_type, row in rows.items():
        documented = _as_int(row["Teto por hora"])
        if documented is None:
            assert source_type == "manual"
            continue
        assert documented == _code_ceiling(source_type), source_type


@needs_doc
def test_ceiling_is_not_below_the_documented_measured_peak() -> None:
    rows = _pacing_rows(DOC.read_text(encoding="utf-8"))

    for source_type, row in rows.items():
        peak = _as_int(row["Pico medido (req/h)"])
        if peak is None or source_type in EXEMPT_FROM_PEAK_CHECK:
            continue
        assert _code_ceiling(source_type) >= peak, source_type
        service_default = DEFAULT_HOST_CEILING_BY_SOURCE_TYPE.get(
            source_type, DEFAULT_HOST_REQUESTS_CEILING
        )
        assert service_default >= peak, f"{source_type} (service default)"


@needs_doc
def test_every_row_says_what_the_provider_asks_and_where() -> None:
    rows = _pacing_rows(DOC.read_text(encoding="utf-8"))

    for source_type, row in rows.items():
        assert row["O que o fornecedor pede (fonte)"], source_type
        assert row["Base da medição"], source_type


def test_service_default_ceilings_match_settings_for_typed_ceilings() -> None:
    """Both places that name a per-type ceiling in code agree."""
    assert DEFAULT_HOST_CEILING_BY_SOURCE_TYPE == Settings().host_request_ceiling_map
