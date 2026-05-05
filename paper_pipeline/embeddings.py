from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from .config import LMStudioConfig


@dataclass(frozen=True)
class EmbeddingStatus:
    status: str
    warning: str = ""


class LMStudioEmbeddingClient:
    def __init__(self, config: LMStudioConfig) -> None:
        self.config = config

    def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.config.embedding_model, "input": texts}
        response = requests.post(
            self.config.embeddings_endpoint,
            json=payload,
            timeout=self.config.embedding_timeout_seconds,
        )
        response.raise_for_status()
        parsed = response.json()
        return [item["embedding"] for item in parsed.get("data", [])]


def embedding_status(config: LMStudioConfig) -> EmbeddingStatus:
    if not config.embeddings_enabled:
        return EmbeddingStatus(status="disabled")
    if not config.embedding_model.strip():
        return EmbeddingStatus(status="lexical_only", warning="embedding_model is empty")
    return EmbeddingStatus(status="configured")


def enrich_index_with_embeddings(index: dict[str, Any], config: LMStudioConfig, client: Any | None = None) -> tuple[dict[str, Any], EmbeddingStatus]:
    status = embedding_status(config)
    if status.status != "configured":
        index["embedding_status"] = status.status
        return index, status
    client = client or LMStudioEmbeddingClient(config)
    try:
        texts = [str(note.get("text", "")) for note in index.get("notes", [])]
        vectors = client.embed(texts)
        for note, vector in zip(index.get("notes", []), vectors, strict=False):
            note["embedding"] = vector
        index["embedding_status"] = "embeddings_ready"
        return index, EmbeddingStatus(status="embeddings_ready")
    except Exception as exc:
        index["embedding_status"] = "embedding_degraded"
        return index, EmbeddingStatus(status="embedding_degraded", warning=str(exc))
