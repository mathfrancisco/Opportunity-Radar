"""Write each prompt version's output schema from the validator that enforces it.

`matching.analysis.OUTPUT_SCHEMAS` is the single source of truth: each schema version
there is the schema sent to Ollama in `format` and the shape `parse_analysis` rejects
deviations from. This script projects the one a prompt declares in its metadata onto
that prompt's artifact, so the two cannot drift.

    python scripts/export_prompt_schema.py              # rewrite every prompt's artifact
    python scripts/export_prompt_schema.py --prompt v2  # rewrite one
    python scripts/export_prompt_schema.py --check      # fail if any is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from opportunity_radar.matching.analysis import OUTPUT_SCHEMAS
from opportunity_radar.matching.prompts import PROMPT_FAMILY, prompt_names, prompts_root

SCHEMA_FILE = "output.schema.json"
METADATA_FILE = "metadata.yaml"


def _rendered(schema_version: str) -> str:
    schema = OUTPUT_SCHEMAS[schema_version]
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _schema_version(directory: Path) -> str:
    metadata = yaml.safe_load((directory / METADATA_FILE).read_text(encoding="utf-8"))
    version = str(metadata.get("schema_version"))
    if version not in OUTPUT_SCHEMAS:
        raise SystemExit(f"{directory} declares unknown schema_version {version!r}")
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", help="one prompt version; every version by default")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when an artifact differs instead of rewriting it",
    )
    args = parser.parse_args(argv)

    root = args.root or prompts_root()
    names = [args.prompt] if args.prompt else prompt_names(root=root)
    stale = 0
    for name in names:
        directory = root / PROMPT_FAMILY / name
        target = directory / SCHEMA_FILE
        version = _schema_version(directory)
        rendered = _rendered(version)
        if args.check:
            current = target.read_text(encoding="utf-8") if target.is_file() else ""
            if current != rendered:
                print(f"{target} is stale; run scripts/export_prompt_schema.py", file=sys.stderr)
                stale += 1
            else:
                print(f"{target} matches {version}")
            continue
        target.write_text(rendered, encoding="utf-8")
        print(f"wrote {target} ({version})")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
