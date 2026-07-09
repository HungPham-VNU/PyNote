FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# uv for fast installs.
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy workspace metadata first for better layer caching.
COPY pyproject.toml ./
COPY packages/core ./packages/core
COPY apps/api ./apps/api

RUN uv pip install --system --no-cache \
      ./packages/core \
      ./apps/api

# Bake BGE-small in — the API embeds queries for hybrid search, so it hits the
# same per-cold-boot re-download as the worker (DEPLOY.md §2.4).
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

EXPOSE 8000
# Bind $PORT when the platform provides it (Render injects it), else 8000 for
# local `docker run`. Shell form so the variable expands.
CMD ["sh", "-c", "uvicorn pynote_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
