"""Local text embeddings with fastembed (ONNX on CPU). Free, no key; the model downloads once."""

import asyncio

from fastembed import TextEmbedding

from src.errors import EmbedderMismatch

EMBEDDER_DIMS = "{model} returns {dims}-dim vectors but EMBED_DIMS={expected}"
EMBEDDER_NOT_STARTED = "Embedder.start() was not awaited"


class Embedder:
    def __init__(self, model_name: str, dims: int) -> None:
        self._model_name = model_name
        self._dims = dims
        self._model: TextEmbedding | None = None

    async def start(self) -> None:
        """Loads the model and checks it returns vectors the facts table can hold."""
        self._model = await asyncio.to_thread(TextEmbedding, self._model_name)
        probe = await self.embed("dimension probe")
        if len(probe) != self._dims:
            raise EmbedderMismatch(
                EMBEDDER_DIMS.format(model=self._model_name, dims=len(probe), expected=self._dims)
            )

    async def embed(self, text: str) -> list[float]:
        if self._model is None:
            raise RuntimeError(EMBEDDER_NOT_STARTED)
        model = self._model
        vector = await asyncio.to_thread(lambda: next(iter(model.embed([text]))))
        return [float(value) for value in vector]


def vector_literal(values: list[float]) -> str:
    """The pgvector text form, cast with `::vector` in SQL."""
    return "[" + ",".join(f"{value:.7f}" for value in values) + "]"
