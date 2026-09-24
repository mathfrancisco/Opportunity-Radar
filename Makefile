.DEFAULT_GOAL := help

.PHONY: help bootstrap dev up up-cpu down restart status logs migrate test test-integration check doctor soak import-companies enable-sources collect backup restore-check

help:
	@echo "Targets: bootstrap dev up up-cpu down restart status logs migrate import-companies enable-sources collect"
	@echo "Operations: doctor soak backup restore-check eval-analysis export-eval-cases"
	@echo "Validation (run only when requested): test test-integration check"

bootstrap:
	@test -f .env || cp .env.example .env
	@docker compose config

dev: up
	@docker compose logs --follow --tail=100

up:
	@docker compose up --build -d

up-cpu:
	@docker compose -f compose.yaml -f compose.cpu.yaml up --build -d

down:
	@docker compose down

restart:
	@docker compose down
	@docker compose up --build -d

status:
	@docker compose ps

logs:
	@docker compose logs --follow --tail=100

migrate:
	@docker compose run --rm migrate

test:
	@docker compose run --rm api pytest -q -p no:cacheprovider

test-integration:
	@docker compose run --rm -e RUN_DATABASE_INTEGRATION=1 api pytest -q -p no:cacheprovider -m integration

check:
	@docker compose run --rm api sh -c "ruff check --no-cache . && mypy --cache-dir=/tmp/mypy"
	@docker compose run --rm frontend npm run check

doctor:
	@docker compose ps
	@docker compose exec -T api python scripts/doctor.py

soak:
	@docker compose run --rm api python scripts/soak_gate.py $(if $(HOURS),--hours "$(HOURS)",) $(if $(JSON),--json,)

import-companies:
	@docker compose run --rm -v "$(CURDIR):/workspace" api python scripts/import_research_catalog.py $(if $(FILE),--input "/workspace/$(FILE)",--input /workspace/docs/pesquisas/auditoria-186-empresas.md --input /workspace/docs/pesquisas/empresas-adicionais.md) $(if $(DRY_RUN),--dry-run,) $(if $(RESUME),--resume,) $(if $(REPORT),--report "/workspace/$(REPORT)",)

enable-sources:
	@test "$(TERMS_REVIEWED)" = "1" || (echo "Use TERMS_REVIEWED=1 after reviewing the public source terms." && exit 2)
	@docker compose run --rm --build -v "$(CURDIR):/workspace" api python scripts/enable_sources.py --accept-terms $(if $(DRY_RUN),--dry-run,) $(if $(EXCLUDE_REMOTIVE),--exclude-remotive,) $(if $(MAX_ITEMS),--max-items "$(MAX_ITEMS)",)

backup:
	@docker compose run --rm -v "$(CURDIR)/data/backups:/app/data/backups" api python scripts/backup.py $(if $(LABEL),--label "$(LABEL)",)

restore-check:
	@docker compose run --rm -v "$(CURDIR)/data/backups:/app/data/backups" api python scripts/restore_check.py $(if $(DUMP),--dump "$(DUMP)",)

collect:
	@docker compose run --rm --build -v "$(CURDIR):/workspace" api python scripts/collect.py $(if $(SOURCE_ID),--source-id "$(SOURCE_ID)",) $(if $(SOURCE_TYPE),--source-type "$(SOURCE_TYPE)",) $(if $(KEYWORDS),--keywords "$(KEYWORDS)",) $(if $(MODE),--mode "$(MODE)",) $(if $(MAX_ITEMS),--max-items "$(MAX_ITEMS)",)

eval-analysis:
	@docker compose run --rm -v "$(CURDIR):/workspace" api python scripts/eval_analysis.py --cases /workspace/prompts/opportunity_analysis/eval/cases --output /workspace/data/evals $(if $(PROMPT),--prompt "$(PROMPT)",) $(if $(MODEL),--model "$(MODEL)",) $(if $(BASELINE),--baseline "/workspace/$(BASELINE)",)

export-eval-cases:
	@docker compose run --rm -v "$(CURDIR):/workspace" api python scripts/export_eval_cases.py --output /workspace/prompts/opportunity_analysis/eval/drafts $(if $(PER_VERDICT),--per-verdict "$(PER_VERDICT)",)

.DEFAULT:
	@echo "Target '$@' is not implemented yet."
	@exit 2
