"""Hybrid retrieval: vector search (pgvector) + BM25, merged with Reciprocal Rank Fusion."""
import logging

from django.conf import settings
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document as LCDocument
from langchain_core.retrievers import BaseRetriever
from pgvector.django import CosineDistance
from rank_bm25 import BM25Okapi

from ..models import DocumentChunk
from .errors import RetrievalError
from .indexer import chunk_search_text
from .llm_factory import get_embeddings
from .text import normalize_text, tokenize

logger = logging.getLogger(__name__)


def rrf_fuse(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion. Each ranking is a list of ids, best first."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores


def vector_ranking(query_vec, limit: int) -> list[int]:
    qs = (
        DocumentChunk.objects.filter(document__is_indexed=True)
        .annotate(distance=CosineDistance("embedding", query_vec))
        .order_by("distance")
        .values_list("id", flat=True)[:limit]
    )
    return list(qs)


def bm25_ranking(query: str, limit: int) -> tuple[list[int], dict[int, float]]:
    rows = list(
        DocumentChunk.objects.filter(document__is_indexed=True).values_list("id", "content", "document__title")
    )
    corpus = [tokenize(chunk_search_text(title, content)) for _, content, title in rows]
    query_tokens = tokenize(query)
    if not rows or not query_tokens or not any(corpus):
        return [], {}
    scores = BM25Okapi(corpus).get_scores(query_tokens)
    ranked = sorted(((s, rows[i][0]) for i, s in enumerate(scores) if s > 0), reverse=True)[:limit]
    return [cid for _, cid in ranked], {cid: float(s) for s, cid in ranked}


def hybrid_search(query: str, top_k: int | None = None) -> list[dict]:
    top_k = top_k or settings.RETRIEVAL_TOP_K
    limit = settings.RETRIEVAL_CANDIDATES
    try:
        query_vec = get_embeddings().embed_query(normalize_text(query))
        vec_ids = vector_ranking(query_vec, limit)
    except Exception as exc:
        logger.exception("Vector search failed")
        raise RetrievalError(f"جست‌وجوی معنایی ناموفق بود: {exc}") from exc
    bm25_ids, bm25_scores = bm25_ranking(query, limit)

    fused = rrf_fuse([vec_ids, bm25_ids], k=settings.RRF_K)
    if not fused:
        return []

    chunks = {
        c.id: c
        for c in DocumentChunk.objects.filter(id__in=fused)
        .select_related("document")
        .annotate(distance=CosineDistance("embedding", query_vec))
    }
    results = []
    for cid, score in sorted(fused.items(), key=lambda kv: kv[1], reverse=True):
        chunk = chunks[cid]
        similarity = 1 - chunk.distance
        # drop vector-only hits that are not similar enough to the question
        if cid not in bm25_scores and similarity < settings.RETRIEVAL_MIN_SIMILARITY:
            continue
        results.append(
            {
                "chunk": chunk,
                "rrf_score": score,
                "vector_similarity": similarity,
                "bm25_score": bm25_scores.get(cid, 0.0),
            }
        )
        if len(results) == top_k:
            break
    return results


class HybridRetriever(BaseRetriever):
    """LangChain retriever that wraps hybrid_search."""

    top_k: int = 5

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[LCDocument]:
        docs = []
        for hit in hybrid_search(query, self.top_k):
            chunk = hit["chunk"]
            docs.append(
                LCDocument(
                    page_content=chunk.content,
                    metadata={
                        "document_id": chunk.document_id,
                        "title": chunk.document.title,
                        "chunk_index": chunk.chunk_index,
                        "rrf_score": round(hit["rrf_score"], 5),
                        "vector_similarity": round(hit["vector_similarity"], 4),
                        "bm25_score": round(hit["bm25_score"], 4),
                    },
                )
            )
        return docs
