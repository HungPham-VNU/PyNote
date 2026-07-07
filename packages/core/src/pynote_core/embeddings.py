"""Embeddings factory.

Free-tier default: fastembed + BAAI/bge-small-en-v1.5 (~130MB ONNX, 384-dim).
First call downloads the model to the user's HF cache (~30s on a typical link).

Other providers (bge-m3-local, voyage) wire in here as new branches when
needed. Swap requires an Alembic migration if the dim changes.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from pynote_core.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import Iterable


class Embedder:
    """Thin protocol — async embed_many → list[list[float]]."""

    dim: int

    async def embed_many(self, texts: Iterable[str]) -> list[list[float]]:  # pragma: no cover
        raise NotImplementedError

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed_many([text]))[0]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a *search query*. Symmetric models fall back to embed_one;
        asymmetric models (BGE) override to apply their query instruction."""
        return await self.embed_one(text)


class _FastembedBGE(Embedder):
    """Local ONNX inference via fastembed.

    fastembed batches efficiently and runs CPU-only by default; no torch.
    """

    def __init__(self, model_name: str, dim: int) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)
        self.dim = dim

    async def embed_many(self, texts: Iterable[str]) -> list[list[float]]:
        import asyncio

        items = list(texts)
        if not items:
            return []
        # fastembed.embed is sync; run in a thread so the event loop stays free.
        vectors = await asyncio.to_thread(lambda: list(self._model.embed(items)))
        return [list(map(float, v)) for v in vectors]

    async def embed_query(self, text: str) -> list[float]:
        """BGE is asymmetric: queries need the instruction prefix. fastembed's
        query_embed applies it; document vectors are unaffected (no migration)."""
        import asyncio

        vectors = await asyncio.to_thread(lambda: list(self._model.query_embed([text])))
        return [float(x) for x in vectors[0]]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    settings = get_settings()
    if settings.embedding_provider in ("bge-small-local", "bge-m3-local"):
        return _FastembedBGE(settings.embedding_model, settings.embedding_dim)
    raise NotImplementedError(
        f"embedding_provider={settings.embedding_provider!r} not wired yet — "
        "stay on bge-small-local for M2 or add a branch in embeddings.py.",
    )


def reset_embedder_cache() -> None:
    """Test hook."""
    get_embedder.cache_clear()
