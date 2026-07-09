FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Cap native thread pools (onnxruntime/OpenBLAS/OMP) so they don't size to
    # the host CPU count and allocate a per-thread arena — the 512MB worker OOM.
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    # Pin the HuggingFace cache to a fixed in-image path so the model baked at
    # build time is found at runtime (default cache differs → re-download on
    # every cold boot, DEPLOY.md §2.4 landmine #6).
    HF_HOME=/app/hf

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml ./
COPY packages/core ./packages/core
COPY apps/worker ./apps/worker

RUN uv pip install --system --no-cache \
      ./packages/core \
      ./apps/worker

# Bake BGE-small into the image so fastembed doesn't re-download ~130MB to an
# ephemeral disk on every cold boot (DEPLOY.md §2.4/§4 landmine #6).
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

# Run via `python -m pynote_worker` (not the arq CLI) so the entrypoint binds
# the $PORT health server and the Windows-loop policy (DEPLOY.md §2.3).
CMD ["python", "-m", "pynote_worker"]
