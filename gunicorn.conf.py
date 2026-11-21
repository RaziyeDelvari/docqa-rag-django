"""gunicorn settings.

The local embedding model takes several hundred MB of RAM and every worker holds its own copy,
so the default is one worker with several threads: the model is loaded once and ONNX Runtime
is thread-safe. --preload would not help because the model is loaded lazily after the fork.
"""
import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("GUNICORN_WORKERS", "1"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"
timeout = 180  # requests can wait a long time for the LLM


def post_worker_init(worker):
    """Load the embedding model at worker start so the first request is not slow."""
    if os.environ.get("WARMUP_EMBEDDINGS", "1") == "0":
        return
    try:
        from documents.services.llm_factory import get_embeddings

        get_embeddings().load()
    except Exception as exc:  # a missing model must not stop the server from starting
        worker.log.warning("Embedding warm-up failed: %s", exc)
