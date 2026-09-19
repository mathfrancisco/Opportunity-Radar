"""Write the analysis output schema from the validator that enforces it.

`matching.analysis.OUTPUT_SCHEMA` is the single source of truth: it is the schema sent to
Ollama in `format` and the shape `parse_analysis` rejects deviations from. This script
projects it onto the versioned prompt artifact so the two cannot drift.

    python scripts/export_prompt_schema.py            # rewrite the artifact
    python scripts/export_prompt_schema.py --check    # fail if it is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from opportunity_radar.matching.analysis import OUTPUT_SCHEMA
from opportunity_radar.matching.prompts import (
    DEFAULT_PROMPT_NAME,
    PROMPT_FAMILY,
    prompts_root,
)

SCHEMA_FILE = "output.schema.json"


def _rendered() -> str:
    return json.dumps(OUTPUT_SCHEMA, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT_NAME)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when the artifact differs instead of rewriting it",
    )
    args = parser.parse_args(argv)

    target = (args.root or prompts_root()) / PROMPT_FAMILY / args.prompt / SCHEMA_FILE
    rendered = _rendered()
    if args.check:
        current = target.read_text(encoding="utf-8") if target.is_file() else ""
        if current != rendered:
            print(f"{target} is stale; run scripts/export_prompt_schema.py", file=sys.stderr)
            return 1
        print(f"{target} matches OUTPUT_SCHEMA")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
