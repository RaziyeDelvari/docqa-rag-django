"""Builds the LLM and embedding clients: the only place that talks to external models."""
import threading
from functools import lru_cache

from django.conf import settings
from langchain_core.embeddings import Embeddings

from .errors import LLMConfigError


class LocalEmbeddings(Embeddings):
    """LangChain Embeddings interface on top of fastembed (ONNX, multilingual, offline).

    E5-family models need prefixes to work properly: "passage: " when indexing and "query: " when
    searching. Other models get no prefix.
    """

    def __init__(self, model_name: str, cache_dir: str):
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()
        is_e5 = "e5" in model_name.lower().split("/")[-1]
        self.doc_prefix = "passage: " if is_e5 else ""
        self.query_prefix = "query: " if is_e5 else ""

    def load(self):
        with self._lock:  # stop concurrent threads from loading the model twice
            if self._model is None:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)
        return self._model

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self.load().embed(texts, batch_size=32)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed([self.doc_prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self.query_prefix + text])[0]


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    return LocalEmbeddings(settings.EMBEDDING_MODEL, settings.EMBEDDING_CACHE_DIR)


@lru_cache(maxsize=1)
def get_llm():
    """Build the chat model for the configured LLM_PROVIDER (gemini or openrouter)."""
    provider = settings.LLM_PROVIDER
    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            raise LLMConfigError("کلید GEMINI_API_KEY در فایل .env تنظیم نشده است.")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0,
            timeout=settings.LLM_TIMEOUT,
            max_retries=2,
        )
    if provider == "openrouter":
        if not settings.OPENROUTER_API_KEY:
            raise LLMConfigError("کلید OPENROUTER_API_KEY در فایل .env تنظیم نشده است.")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            temperature=0,
            timeout=settings.LLM_TIMEOUT,
            max_retries=2,
        )
    raise LLMConfigError(f"مقدار LLM_PROVIDER نامعتبر است: «{provider}». فقط gemini یا openrouter.")
