# PyNote command runner. Install just: https://github.com/casey/just
#   Git Bash / WSL / Linux / macOS:  uses bash for all recipes.
#   PowerShell users: install Git for Windows so `bash.exe` is on PATH;
#   `just` will find it automatically via this `set shell` directive.
#
# Run `just` (no args) to see this list.

set shell       := ["bash", "-uc"]
set dotenv-load := true

# Show available commands.
default:
    @just --list --unsorted

# ---- Setup ---------------------------------------------------------------

# One-shot bootstrap: install Python + web deps.
setup: setup-python setup-web
    @echo "✅ Setup complete. Next: 'just env' then 'just up' then 'just migrate' then 'just dev'."

setup-python:
    uv sync
    uv pip install -e packages/core -e apps/api -e apps/worker

setup-web:
    cd apps/web && pnpm install

# Copy env templates without overwriting.
env:
    @[ -f .env ] || (cp .env.example .env && echo "Created .env")
    @[ -f apps/web/.env.local ] || (cp apps/web/.env.example apps/web/.env.local && echo "Created apps/web/.env.local")

# ---- Local services ------------------------------------------------------

# Start Postgres + Redis + MinIO.
up:
    docker compose -f docker-compose.dev.yml up -d

# Stop services (keeps data).
down:
    docker compose -f docker-compose.dev.yml down

# Wipe services AND data volumes (clean slate).
reset:
    docker compose -f docker-compose.dev.yml down -v

# Tail compose logs.
logs:
    docker compose -f docker-compose.dev.yml logs -f --tail=100

# ---- Database ------------------------------------------------------------

migrate:
    uv run alembic upgrade head

# Generate a new migration: `just makemigration "add source table"`
makemigration message:
    uv run alembic revision --autogenerate -m "{{message}}"

downgrade:
    uv run alembic downgrade -1

# Open psql against the local Postgres.
psql:
    docker exec -it pynote-postgres psql -U pynote -d pynote

# ---- Dev: run the app ----------------------------------------------------

# Run api + worker + web in one terminal (requires mprocs).
dev:
    mprocs --config mprocs.yaml

# Just the API. Uses the programmatic entrypoint so the Windows SelectorEventLoop
# policy is installed before the loop starts (psycopg3 async needs it).
api:
    uv run python -m pynote_api

# Just the worker. Uses the programmatic entrypoint so the Windows
# SelectorEventLoop policy is set before arq creates its loop.
worker:
    uv run python -m pynote_worker

# Just the web.
web:
    cd apps/web && pnpm dev

# ---- Quality gates -------------------------------------------------------

test:
    uv run pytest -q

# Retrieval-stage eval (recall@k / MRR, no LLM). Usage:
#   just eval-retrieval NOTEBOOK_UUID [file]
eval-retrieval notebook file="eval/golden/retrieval.jsonl":
    uv run python -m eval.retrieval_eval --notebook {{notebook}} --file {{file}}

test-smoke:
    uv run pytest packages/core/tests/test_llm_factory.py::test_smoke_chat_ping -v

lint:
    uv run ruff check .
    uv run ruff format --check .

fmt:
    uv run ruff check . --fix
    uv run ruff format .

typecheck:
    uv run mypy packages/core/src

# All gates (what CI runs).
check: lint typecheck test
    cd apps/web && pnpm typecheck && pnpm lint

# ---- Maintenance ---------------------------------------------------------

# Print versions of every tool. Missing tools print "not installed".
doctor:
    @printf "uv:     "; uv     --version 2>/dev/null || echo "not installed"
    @printf "node:   "; node   --version 2>/dev/null || echo "not installed"
    @printf "pnpm:   "; pnpm   --version 2>/dev/null || echo "not installed"
    @printf "docker: "; docker --version 2>/dev/null || echo "not installed"
    @printf "just:   "; just   --version 2>/dev/null || echo "not installed"
    @printf "mprocs: "; mprocs --version 2>/dev/null || echo "not installed"
    @printf "make:   "; make   --version 2>/dev/null | head -1 || echo "not installed"

# Remove caches and build artifacts (keeps deps and DB data).
clean:
    find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache -o -name .next -o -name dist \) \
        -not -path './.venv/*' -not -path './node_modules/*' -prune -exec rm -rf {} + 2>/dev/null || true
