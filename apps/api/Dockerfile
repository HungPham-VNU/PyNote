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

EXPOSE 8000
CMD ["uvicorn", "pynote_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
