FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml ./
COPY packages/core ./packages/core
COPY apps/worker ./apps/worker

RUN uv pip install --system --no-cache \
      ./packages/core \
      ./apps/worker

CMD ["arq", "pynote_worker.main.WorkerSettings"]
