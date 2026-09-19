.DEFAULT_GOAL := help

.PHONY: help bootstrap dev up down restart status logs migrate test test-integration check doctor import-companies collect backup restore-check

help:
	@echo "Targets: bootstrap dev up down restart status logs migrate import-companies"
	@echo "Operations: doctor backup restore-check"
	@echo "Validation (run only when requested): test test-integration check"
	@echo "Planned: collect"

bootstrap:
	@test -f .env || cp .env.example .env
	@docker compose config

dev: up
	@docker compose logs --follow --tail=100

up:
	@docker compose up --build -d

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

import-companies:
	@docker compose run --rm -v "$(CURDIR):/workspace" api python scripts/import_research_catalog.py $(if $(FILE),--input "/workspace/$(FILE)",--input /workspace/docs/pesquisas/auditoria-186-empresas.md --input /workspace/docs/pesquisas/empresas-adicionais.md) $(if $(DRY_RUN),--dry-run,) $(if $(RESUME),--resume,) $(if $(REPORT),--report "/workspace/$(REPORT)",)

backup:
	@docker compose run --rm -v "$(CURDIR)/data/backups:/app/data/backups" api python scripts/backup.py $(if $(LABEL),--label "$(LABEL)",)

restore-check:
	@docker compose run --rm -v "$(CURDIR)/data/backups:/app/data/backups" api python scripts/restore_check.py $(if $(DUMP),--dump "$(DUMP)",)

collect:
	@echo "Target '$@' belongs to a later MVP phase and is not implemented yet."
	@exit 2

.DEFAULT:
	@echo "Target '$@' is not implemented yet."
	@exit 2
