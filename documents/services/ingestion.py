"""Logic shared by the API and the admin: extract the document text and (re)index it."""
import logging

from ..models import Document
from .docx_parser import extract_text
from .errors import EmptyDocumentError, ServiceError
from .indexer import index_document
from .text import normalize_text

logger = logging.getLogger(__name__)


def resolve_content(file=None, content=None) -> str:
    """Content comes from the file if one is given, otherwise from the text."""
    text = extract_text(file) if file else normalize_text(content or "")
    if not text.strip():
        raise EmptyDocumentError("سند باید فایل docx یا متن غیرخالی داشته باشد.")
    return text


def reindex(doc: Document) -> tuple[bool, str]:
    """Index a document. On failure the document is kept with is_indexed=False and the error is stored."""
    try:
        index_document(doc)
        return True, ""
    except ServiceError as exc:
        msg = str(exc)
    except Exception as exc:  # an unexpected error must not break saving the document
        logger.exception("Unexpected indexing error")
        msg = f"خطای غیرمنتظره: {exc}"
    Document.objects.filter(pk=doc.pk).update(is_indexed=False, index_error=msg)
    doc.is_indexed, doc.index_error = False, msg
    return False, msg
