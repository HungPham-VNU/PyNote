# Makefile alternative to the Justfile — for users who prefer GNU Make
# (Git Bash on Windows usually has it; verify with `make --version`).
# Recipes are identical to the Justfile so you can switch freely.

SHELL := bash
.SHELLFLAGS := -uc
.DEFAULT_GOAL := help

.PHONY: help setup setup-python setup-web env up down reset logs migrate downgrade psql \
        dev api worker web test test-smoke lint fmt typecheck check doctor clean

help: ## Show this list
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- Setup ---------------------------------------------------------------

setup: setup-python setup-web  ## Install Python + web deps
	@echo "✅ Setup complete. Next: make env, make up, make migrate, make dev."

setup-python:  ## Install Python workspace
	uv sync
	uv pip install -e packages/core -e apps/api -e apps/worker

setup-web:  ## Install web deps
	cd apps/web && pnpm install

env:  ## Copy .env templates (won't overwrite)
	@[ -f .env ] || (cp .env.example .env && echo "Created .env")
	@[ -f apps/web/.env.local ] || (cp apps/web/.env.example apps/web/.env.local && echo "Created apps/web/.env.local")

# ---- Local services ------------------------------------------------------

up:  ## Start Postgres + Redis + MinIO
	docker compose -f docker-compose.dev.yml up -d

down:  ## Stop services (keeps data)
	docker compose -f docker-compose.dev.yml down

reset:  ## Wipe services AND data volumes
	docker compose -f docker-compose.dev.yml down -v

logs:  ## Tail compose logs
	docker compose -f docker-compose.dev.yml logs -f --tail=100

# ---- Database ------------------------------------------------------------

migrate:  ## Apply migrations
	uv run alembic upgrade head

# Usage: make makemigration m="add source table"
makemigration:  ## Generate migration (m="message")
	uv run alembic revision --autogenerate -m "$(m)"

downgrade:  ## Roll back one migration
	uv run alembic downgrade -1

psql:  ## Open psql shell
	docker exec -it pynote-postgres psql -U pynote -d pynote

# ---- Dev -----------------------------------------------------------------

dev:  ## Run api+worker+web in one terminal (needs mprocs)
	mprocs --config mprocs.yaml

api:  ## Run only the API
	uv run uvicorn pynote_api.main:app --reload --port 8000

worker:  ## Run only the worker
	uv run arq pynote_worker.main.WorkerSettings

web:  ## Run only the web app
	cd apps/web && pnpm dev

# ---- Quality gates -------------------------------------------------------

test:  ## Run pytest
	uv run pytest -q

test-smoke:  ## Run live-LLM smoke test (needs ANTHROPIC_API_KEY)
	uv run pytest packages/core/tests/test_llm_factory.py::test_smoke_chat_ping -v

lint:  ## ruff check + format check
	uv run ruff check .
	uv run ruff format --check .

fmt:  ## ruff auto-fix + format
	uv run ruff check . --fix
	uv run ruff format .

typecheck:  ## mypy on core
	uv run mypy packages/core/src

check: lint typecheck test  ## Full CI gate
	cd apps/web && pnpm typecheck && pnpm lint

# ---- Maintenance ---------------------------------------------------------

doctor:  ## Show installed tool versions
	@printf "uv:     "; uv     --version 2>/dev/null || echo "not installed"
	@printf "node:   "; node   --version 2>/dev/null || echo "not installed"
	@printf "pnpm:   "; pnpm   --version 2>/dev/null || echo "not installed"
	@printf "docker: "; docker --version 2>/dev/null || echo "not installed"
	@printf "just:   "; just   --version 2>/dev/null || echo "not installed"
	@printf "mprocs: "; mprocs --version 2>/dev/null || echo "not installed"
	@printf "make:   "; make   --version 2>/dev/null | head -1 || echo "not installed"

clean:  ## Remove caches and build artifacts
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache -o -name .next -o -name dist \) \
		-not -path './.venv/*' -not -path './node_modules/*' -prune -exec rm -rf {} + 2>/dev/null || true
