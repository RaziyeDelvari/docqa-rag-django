"""Chunking, embedding and atomic storage of chunks in pgvector."""
import logging

from django.conf import settings
from django.db import transaction
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ..models import Document, DocumentChunk
from .errors import IndexingError
from .llm_factory import get_embeddings

logger = logging.getLogger(__name__)

SEPARATORS = ["\n\n", "\n", ".", "؟", "?", "!", "؛", ";", "،", ",", " ", ""]


def split_text(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=SEPARATORS,
    )
    return [p.strip() for p in splitter.split_text(text) if p.strip()]


def chunk_search_text(title: str, content: str) -> str:
    """Text that is embedded and BM25-indexed: the title gives each chunk context."""
    return f"{title}\n{content}"


def index_document(doc: Document) -> int:
    """Replace the document's chunks with fresh ones and return how many there are.

    Embedding runs outside the transaction, so a failure leaves the existing data untouched.
    """
    pieces = split_text(doc.content)
    try:
        vectors = get_embeddings().embed_documents([chunk_search_text(doc.title, p) for p in pieces]) if pieces else []
    except Exception as exc:
        logger.exception("Embedding failed for document %s", doc.pk)
        raise IndexingError(f"ساخت Embedding ناموفق بود: {exc}") from exc

    with transaction.atomic():
        doc.chunks.all().delete()
        DocumentChunk.objects.bulk_create(
            [
                DocumentChunk(document=doc, chunk_index=i, content=p, embedding=v)
                for i, (p, v) in enumerate(zip(pieces, vectors))
            ]
        )
        Document.objects.filter(pk=doc.pk).update(is_indexed=True, index_error="")
    doc.is_indexed, doc.index_error = True, ""
    return len(pieces)
