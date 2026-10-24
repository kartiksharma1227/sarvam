"""Text embeddings for icon search (OpenAI, cut to EMBEDDING_DIMENSIONS)."""

from typing import Protocol

import numpy as np
from openai import AsyncOpenAI
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.agents.llm import Usage, is_transient
from app.config import settings


class Embedder(Protocol):
    dimensions: int

    async def embed(self, texts: list[str], usage: Usage) -> np.ndarray:
        """One L2-normalised row per text."""
        ...


def normalise(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class OpenAIEmbedder:
    def __init__(self, client: AsyncOpenAI | None = None):
        self.client = client or AsyncOpenAI(
            api_key=settings.openai_api_key, timeout=30, max_retries=0
        )
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions

    @retry(
        retry=retry_if_exception(is_transient),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=20),
        reraise=True,
    )
    async def embed(self, texts: list[str], usage: Usage) -> np.ndarray:
        response = await self.client.embeddings.create(
            model=self.model, input=texts, dimensions=self.dimensions
        )
        if response.usage:
            usage.add(self.model, response.usage.prompt_tokens, 0)
        rows = sorted(response.data, key=lambda d: d.index)
        return normalise(np.array([r.embedding for r in rows], dtype=np.float32))
