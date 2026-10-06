from qdrant_client import QdrantClient

from ragbook.corpus import Chunk
from ragbook.indexing import Index, acl_filter, chunk_point_id, sha

TEXT = "Cennik wdrożeń wewnętrznych."


def chunk(groups: list[str]) -> Chunk:
    return Chunk(id=chunk_point_id("08-rag.md", 0), chapter=8, section="Koszty", text=TEXT,
                 meta={"doc_id": "08-rag.md", "doc_hash": "d1", "position": 0,
                       "chunk_hash": sha(TEXT), "title": "RAG", "groups": groups})


def make_index(embedder) -> Index:
    return Index(QdrantClient(":memory:"), "chunks", embedder)


def test_revoked_group_loses_access_after_sync(embedder):
    index = make_index(embedder)
    index.sync([chunk(["public"])])

    index.sync([chunk(["internal"])])

    assert index.search(TEXT, k=5, query_filter=acl_filter(["public"])) == []
    assert len(index.search(TEXT, k=5, query_filter=acl_filter(["internal"]))) == 1


def test_group_change_updates_payload_without_reembedding(embedder):
    index = make_index(embedder)
    index.sync([chunk(["public"])])
    embedded_before = embedder.passages_embedded

    stats = index.sync([chunk(["internal"])])

    assert embedder.passages_embedded == embedded_before
    assert (stats.chunks_embedded, stats.chunks_acl_updated, stats.chunks_unchanged) == (0, 1, 0)


def test_same_groups_in_other_order_count_as_unchanged(embedder):
    index = make_index(embedder)
    index.sync([chunk(["public", "internal"])])

    stats = index.sync([chunk(["internal", "public"])])

    assert (stats.chunks_acl_updated, stats.chunks_unchanged) == (0, 1)
