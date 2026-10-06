from ragbook.cache import SemanticAnswerCache
from ragbook.corpus import Section
from ragbook.indexing import Document

QUESTION = "Ile kosztuje wdrożenie modelu wewnętrznego?"


def test_does_not_serve_an_answer_to_a_reader_with_other_groups(embedder):
    cache = SemanticAnswerCache(embedder, threshold=0.95)
    cache.put(QUESTION, "internal answer", groups=["public", "internal"])

    hit, _ = cache.lookup(QUESTION, groups=["public"])

    assert hit is None


def test_serves_an_answer_to_a_reader_with_the_same_groups_in_any_order(embedder):
    cache = SemanticAnswerCache(embedder, threshold=0.95)
    cache.put(QUESTION, "internal answer", groups=["public", "internal"])

    hit, score = cache.lookup(QUESTION, groups=["internal", "public"])

    assert hit is not None and hit.answer == "internal answer"
    assert score > 0.99


def test_prefers_the_entry_written_for_the_reader_groups(embedder):
    cache = SemanticAnswerCache(embedder, threshold=0.95)
    cache.put(QUESTION, "internal answer", groups=["internal"])
    cache.put(QUESTION, "public answer", groups=["public"])

    hit, _ = cache.lookup(QUESTION, groups=["public"])

    assert hit is not None and hit.answer == "public answer"


def test_cached_answer_expires_when_a_cited_document_changes_groups(embedder):
    doc = Document("08-rag.md", [Section(8, "RAG", "Koszty", "Cennik wdrożeń.", "08-rag.md")],
                   groups=("public",))
    cache = SemanticAnswerCache(embedder, threshold=0.95)
    cache.put(QUESTION, "public answer", groups=["public"], doc_hashes=(doc.version_hash,))

    doc.groups = ("internal",)
    hit, _ = cache.lookup(QUESTION, groups=["public"], live_hashes={doc.doc_id: doc.version_hash})

    assert hit is None
