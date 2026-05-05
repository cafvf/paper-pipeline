from paper_pipeline.config import LMStudioConfig
from paper_pipeline.embeddings import embedding_status, enrich_index_with_embeddings


class FakeEmbeddingClient:
    def __init__(self, fail=False):
        self.fail = fail

    def embed(self, texts):
        if self.fail:
            raise RuntimeError("boom")
        return [[1.0, 0.0] for _ in texts]


def test_empty_embedding_model_uses_lexical_only():
    status = embedding_status(LMStudioConfig(embedding_model=""))
    assert status.status == "lexical_only"


def test_enrich_index_with_embeddings_when_configured():
    index = {"notes": [{"text": "hello"}]}
    enriched, status = enrich_index_with_embeddings(index, LMStudioConfig(embedding_model="model"), FakeEmbeddingClient())
    assert status.status == "embeddings_ready"
    assert enriched["notes"][0]["embedding"] == [1.0, 0.0]


def test_embedding_failure_degrades_to_lexical():
    index = {"notes": [{"text": "hello"}]}
    enriched, status = enrich_index_with_embeddings(index, LMStudioConfig(embedding_model="model"), FakeEmbeddingClient(fail=True))
    assert status.status == "embedding_degraded"
    assert enriched["embedding_status"] == "embedding_degraded"
