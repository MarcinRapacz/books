"""Dense index on Qdrant in-memory. Returns Chunk objects with the score attached in `meta["score"]`."""
from __future__ import annotations

import numpy as np
from qdrant_client import QdrantClient, models

from .corpus import Chunk
from .embed import Embedder


class DenseIndex:
    def __init__(self, embedder: Embedder, chunks: list[Chunk], collection: str = "chunks"):
        self.embedder = embedder
        self.chunks = chunks
        self.collection = collection
        self.client = QdrantClient(":memory:")
        vecs = embedder.embed_passages([c.text for c in chunks])
        self.client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(size=vecs.shape[1], distance=models.Distance.COSINE),
        )
        self.client.upload_points(
            collection_name=collection,
            points=[
                models.PointStruct(id=i, vector=vecs[i].tolist(),
                                   payload={"chapter": c.chapter, "section": c.section, **c.meta})
                for i, c in enumerate(chunks)
            ],
        )

    def search(self, query: str, k: int = 5, query_filter: models.Filter | None = None) -> list[Chunk]:
        qv = self.embedder.embed_queries([query])[0]
        res = self.client.query_points(collection_name=self.collection, query=qv.tolist(),
                                       limit=k, query_filter=query_filter).points
        out = []
        for p in res:
            c = self.chunks[int(p.id)]
            out.append(Chunk(c.id, c.chapter, c.section, c.text, {**c.meta, "score": float(p.score)}))
        return out
