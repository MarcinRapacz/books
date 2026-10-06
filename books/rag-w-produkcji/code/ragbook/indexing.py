"""Indexing as a process: content hashes, deterministic chunk ids, incremental sync, blue/green aliases.

The unit of change is a *document* (one Markdown file of volume 1). Every document has a content hash;
every chunk has its own hash and a deterministic UUID derived from (doc_id, position). A sync compares the
hashes already in the collection with the hashes of the incoming chunks and touches only the difference.

Works the same on `QdrantClient(":memory:")`, `QdrantClient(path=...)` and `QdrantClient(url=...)`.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from qdrant_client import QdrantClient, models

from .corpus import CORPUS_DIR, Chunk, Section, load_sections

NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "ragbook.chunks")


def sha(text: str) -> str:
    """Stable short content hash (16 hex chars = 64 bits, enough for a book-sized corpus)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def chunk_point_id(doc_id: str, position: int) -> str:
    """Deterministic point id: the same (document, position) always maps to the same UUID."""
    return str(uuid.uuid5(NAMESPACE, f"{doc_id}#{position}"))


@dataclass
class Document:
    doc_id: str                 # file name, e.g. "08-rag.md"
    sections: list[Section]
    groups: tuple[str, ...] = ("all",)   # ACL: which reader groups may see this document

    @property
    def text(self) -> str:
        return "\n\n".join(f"## {s.section}\n{s.text}" for s in self.sections)

    @property
    def content_hash(self) -> str:
        return sha(self.text)


def load_documents(corpus_dir: Path = CORPUS_DIR) -> list[Document]:
    """Group the parsed sections of volume 1 back into documents (one per Markdown file)."""
    by_doc: dict[str, list[Section]] = {}
    for s in load_sections(corpus_dir):
        by_doc.setdefault(s.path, []).append(s)
    return [Document(doc_id, secs) for doc_id, secs in sorted(by_doc.items())]


def chunk_document(doc: Document, tokenizer, window: int = 128, overlap: int = 32) -> list[Chunk]:
    """Baseline chunker (fixed token window) applied per document, with production metadata attached."""
    out: list[Chunk] = []
    step = max(1, window - overlap)
    doc_hash = doc.content_hash
    position = 0
    for s in doc.sections:
        ids = tokenizer(s.text, add_special_tokens=False)["input_ids"]
        for start in range(0, max(1, len(ids)), step):
            piece = ids[start:start + window]
            if not piece:
                break
            text = tokenizer.decode(piece)
            out.append(Chunk(
                id=chunk_point_id(doc.doc_id, position),
                chapter=s.chapter, section=s.section, text=text,
                meta={"doc_id": doc.doc_id, "doc_hash": doc_hash, "position": position,
                      "chunk_hash": sha(text), "title": s.title, "groups": list(doc.groups)},
            ))
            position += 1
            if start + window >= len(ids):
                break
    return out


@dataclass
class SyncStats:
    docs_total: int = 0
    docs_changed: int = 0
    chunks_total: int = 0
    chunks_embedded: int = 0
    chunks_unchanged: int = 0
    points_deleted: int = 0
    seconds: float = 0.0

    def as_row(self, name: str) -> dict:
        return {"name": name, "docs": self.docs_changed, "embedded": self.chunks_embedded,
                "unchanged": self.chunks_unchanged, "deleted": self.points_deleted,
                "seconds": round(self.seconds, 2)}


class Index:
    """A Qdrant collection plus the sync logic that keeps it in step with the corpus."""

    def __init__(self, client: QdrantClient, collection: str, embedder, recreate: bool = False):
        self.client = client
        self.collection = collection
        self.embedder = embedder
        if recreate and client.collection_exists(collection):
            client.delete_collection(collection)
        if not client.collection_exists(collection):
            client.create_collection(
                collection_name=collection,
                vectors_config=models.VectorParams(size=embedder.dim, distance=models.Distance.COSINE),
            )
            # On a server these indexes decide whether filtering happens inside HNSW or after it.
            for field_name in ("doc_id", "chapter", "groups"):
                client.create_payload_index(collection, field_name, models.PayloadSchemaType.KEYWORD)

    def stored_state(self) -> dict[str, tuple[str, str]]:
        """{point_id: (doc_id, chunk_hash)} for everything currently in the collection."""
        state: dict[str, tuple[str, str]] = {}
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection, limit=1024, offset=offset,
                with_payload=["doc_id", "chunk_hash"], with_vectors=False,
            )
            for p in points:
                state[str(p.id)] = (p.payload["doc_id"], p.payload["chunk_hash"])
            if offset is None:
                break
        return state

    def sync(self, chunks: list[Chunk]) -> SyncStats:
        """Upsert what changed, delete what disappeared, leave the rest untouched."""
        started = time.perf_counter()
        stats = SyncStats(chunks_total=len(chunks))
        stats.docs_total = len({c.meta["doc_id"] for c in chunks})
        state = self.stored_state()

        todo, seen = [], set()
        for c in chunks:
            seen.add(c.id)
            known = state.get(c.id)
            if known is not None and known[1] == c.meta["chunk_hash"]:
                stats.chunks_unchanged += 1
            else:
                todo.append(c)
        stats.docs_changed = len({c.meta["doc_id"] for c in todo})

        if todo:
            vectors = self.embedder.embed_passages([c.text for c in todo])
            self.client.upsert(
                collection_name=self.collection,
                points=[models.PointStruct(id=c.id, vector=vectors[i].tolist(),
                                           payload={"chapter": c.chapter, "section": c.section,
                                                    "text": c.text, **c.meta})
                        for i, c in enumerate(todo)],
            )
            stats.chunks_embedded = len(todo)

        orphans = [pid for pid in state if pid not in seen]
        if orphans:
            self.client.delete(collection_name=self.collection,
                               points_selector=models.PointIdsList(points=orphans))
            stats.points_deleted = len(orphans)

        stats.seconds = time.perf_counter() - started
        return stats

    def delete_document(self, doc_id: str) -> int:
        """Remove every chunk of one document; the filter is what makes this a one-liner."""
        before = self.count()
        self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(filter=models.Filter(must=[
                models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))])),
        )
        return before - self.count()

    def count(self) -> int:
        return self.client.count(self.collection, exact=True).count

    def search(self, query: str, k: int = 5, query_filter: models.Filter | None = None,
               collection: str | None = None) -> list[Chunk]:
        qv = self.embedder.embed_queries([query])[0]
        res = self.client.query_points(collection_name=collection or self.collection,
                                       query=qv.tolist(), limit=k,
                                       query_filter=query_filter).points
        return [Chunk(str(p.id), p.payload["chapter"], p.payload["section"], p.payload["text"],
                      {**{kk: vv for kk, vv in p.payload.items() if kk != "text"}, "score": float(p.score)})
                for p in res]


def switch_alias(client: QdrantClient, alias: str, collection: str) -> None:
    """Point `alias` at `collection` in one atomic operation (blue/green switch of the whole index)."""
    ops: list[models.AliasOperations] = []
    if any(a.alias_name == alias for a in client.get_aliases().aliases):
        ops.append(models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias)))
    ops.append(models.CreateAliasOperation(
        create_alias=models.CreateAlias(collection_name=collection, alias_name=alias)))
    client.update_collection_aliases(change_aliases_operations=ops)


def alias_target(client: QdrantClient, alias: str) -> str | None:
    for a in client.get_aliases().aliases:
        if a.alias_name == alias:
            return a.collection_name
    return None


def acl_filter(groups: list[str], extra: list[models.FieldCondition] = ()) -> models.Filter:
    """Document-level access control: the reader's groups must intersect the document's groups."""
    return models.Filter(must=[
        models.FieldCondition(key="groups", match=models.MatchAny(any=groups)),
        *extra,
    ])
