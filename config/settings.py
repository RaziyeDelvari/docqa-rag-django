"""Project settings. Every value can be overridden through environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return str(env(name, str(default))).lower() in ("1", "true", "yes", "on")


SECRET_KEY = env("SECRET_KEY", "dev-only-change-me")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", "*").split(",")]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "documents",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "docqa_db"),
        "USER": env("POSTGRES_USER", "docqa"),
        "PASSWORD": env("POSTGRES_PASSWORD", "docqa_pass"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = env("LANGUAGE_CODE", "fa")
TIME_ZONE = env("TIME_ZONE", "Asia/Tehran")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
MAX_UPLOAD_MB = int(env("MAX_UPLOAD_MB", "10"))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024

# ---------------------------------------------------------------- DRF / Swagger
# The API is open by default to keep testing simple; API_REQUIRE_AUTH=True requires Basic/Session auth.
_require_auth = env_bool("API_REQUIRE_AUTH", False)
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated"
        if _require_auth
        else "rest_framework.permissions.AllowAny"
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}
SPECTACULAR_SETTINGS = {
    "TITLE": "DocQA API",
    "DESCRIPTION": "سامانه پرسش از اسناد: مدیریت اسناد، پرسش و پاسخ مبتنی بر RAG و تاریخچه.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ---------------------------------------------------------------- AI
# LLM provider: gemini (Google AI Studio) or openrouter
LLM_PROVIDER = env("LLM_PROVIDER", "gemini").lower()
LLM_MODEL = env("LLM_MODEL", "gemini-4-hydrogen" if LLM_PROVIDER == "gemini" else "openrouter/free")
LLM_TIMEOUT = int(env("LLM_TIMEOUT", "60"))
GEMINI_API_KEY = env("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Local multilingual embeddings (fastembed / ONNX): no API key, no PyTorch
EMBEDDING_MODEL = env("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
EMBEDDING_DIM = int(env("EMBEDDING_DIM", "384"))  # must match the model above
EMBEDDING_CACHE_DIR = env("FASTEMBED_CACHE_PATH", str(BASE_DIR / ".model_cache"))

# Chunking and retrieval
CHUNK_SIZE = int(env("CHUNK_SIZE", "600"))
CHUNK_OVERLAP = int(env("CHUNK_OVERLAP", "100"))
RETRIEVAL_TOP_K = int(env("RETRIEVAL_TOP_K", "5"))
RETRIEVAL_CANDIDATES = int(env("RETRIEVAL_CANDIDATES", "20"))
RETRIEVAL_MIN_SIMILARITY = float(env("RETRIEVAL_MIN_SIMILARITY", "0.2"))
RRF_K = int(env("RRF_K", "60"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
