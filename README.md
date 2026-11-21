# DocQA | Document Question Answering System

A system for registering documents (text or `docx` files), searching through them, and answering questions with a language model — **only** based on the content of those same documents. Both questions and documents can be in Persian or English (even a Persian question about an English document).

**Stack:** Django 5 + Django Admin (UI) + Django REST Framework (API and Swagger) + LangChain (RAG chain) + PostgreSQL with pgvector + Docker. The default language model is Gemini (Google AI Studio), and it can be switched to OpenRouter by changing `.env`.

## Running with Docker

Prerequisite: Docker and Docker Compose.

```bash
cp .env.example .env
# In the .env file, replace the GEMINI_API_KEY value with a free key from Google AI Studio
docker compose up --build
```

The first build takes a few minutes because the Embedding model (about 220 MB) is downloaded into the image. After that:

| Address                           | Purpose                                                                |
| --------------------------------- | ---------------------------------------------------------------------- |
| http://localhost:8000/admin/      | Admin panel (user `admin`, password `admin12345` from the `.env` file) |
| http://localhost:8000/api/docs/   | Interactive Swagger documentation                                      |
| http://localhost:8000/api/schema/ | OpenAPI schema (saved version: `docs/openapi.yaml`)                    |

On the first run, two sample documents (`sample_data/`) are automatically registered and indexed (disable with `LOAD_SAMPLE_DATA=0`). To register manually: `docker compose exec web python manage.py load_sample_data`

### Selecting and changing the language model

In `.env`, this is determined by `LLM_PROVIDER`:

| Provider         | Settings                                                                                                                 |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Gemini (default) | `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-4-hydrogen`, `GEMINI_API_KEY=...` (key from https://aistudio.google.com/apikey) |
| OpenRouter       | `LLM_PROVIDER=openrouter`, `LLM_MODEL=openrouter/free` (or one of the free models), `OPENROUTER_API_KEY=...`             |

After changing `.env`, just run `docker compose up -d`; no code changes are needed. If one service hits a rate limit while serving, you can switch to the other within seconds. If you leave `LLM_MODEL` empty, `gemini-4-hydrogen` is used for gemini and `openrouter/free` for openrouter.

## Usage

### From the admin panel

- **Documents → Add:** provide a title and upload a `docx` file (or type the text directly). The document is automatically extracted and indexed on save, and you see a success or error message. At the bottom of the document page, the indexed chunks are displayed.
- **"Reindex" action** in the documents list.
- **Question & Answer History → Add:** just write the question; the answer and sources are generated and saved automatically.

### From the API

| Method               | Path                                     | Action                                                       |
| -------------------- | ---------------------------------------- | ------------------------------------------------------------ |
| GET                  | `/api/documents/`                        | List documents (`?search=` and `?is_indexed=`)               |
| POST                 | `/api/documents/`                        | Add a document (`docx` file or `content`)                    |
| GET/PUT/PATCH/DELETE | `/api/documents/{id}/`                   | View, edit, delete                                           |
| POST                 | `/api/documents/{id}/reindex/`           | Reindex                                                      |
| POST                 | `/api/ask/`                              | Ask a question, get a sourced answer, and save it to history |
| GET                  | `/api/history/` and `/api/history/{id}/` | Question history (newest first)                              |

```bash
# Add a docx file
curl -F "title=Guide" -F "file=@sample_data/company_policy_fa.docx" http://localhost:8000/api/documents/

# Add text
curl -X POST http://localhost:8000/api/documents/ -H "Content-Type: application/json" \
  -d '{"title":"Note","content":"The weekly meeting is every Sunday at 10 AM."}'

# Ask a question
curl -X POST http://localhost:8000/api/ask/ -H "Content-Type: application/json" \
  -d '{"question":"How many days is marriage leave?"}'

# Persian question about an English document
curl -X POST http://localhost:8000/api/ask/ -H "Content-Type: application/json" \
  -d '{"question":"What is the maximum requests per minute for the Pro plan?"}'
```

Sample `/api/ask/` response: fields `answer`, `sources` (document title, chunk number, chunk text, and scores), `model_used`, and `created_at`.
Errors: `400` invalid input or file, `502` language model/Embedding error, `503` missing API key.
By default the API has no authentication to make testing easy; with `API_REQUIRE_AUTH=True`, login (Basic/Session) is required.

### Suggested testing scenario

1. "What are the official working hours?" (Persian document, paragraph)
2. "How many days is marriage leave?" (answer is inside a docx **table**)
3. "What does ERR-4290 mean?" (exact code; keyword search helps)
4. "What is the manager's favorite food?" (should say there is not enough information)

## Architecture

```
 Admin / Swagger / curl
          │
   Django + DRF  ──►  services/ingestion   (docx → text → chunks → Embedding)
          │                    │
          │                    ▼
          │      PostgreSQL + pgvector  (Document ─< DocumentChunk(vector), QuestionHistory)
          │                    ▲
          └──►  services/qa_chain (LCEL)
                  retrieve ─► prompt ─► LLM ─► answer
                    │
          HybridRetriever: vector (cosine) + BM25 ──► RRF
```

Indexing flow: extract paragraphs and tables with `python-docx` (each table row is written together with the column names) ← Persian normalization (`ي`/`ك`, invisible characters; the ZWNJ is preserved) ← chunking with `RecursiveCharacterTextSplitter` (600 characters, 100 overlap) ← local Embedding ← stored in the `DocumentChunk` table.

Answer flow: hybrid retrieval ← building numbered context ← anti-hallucination prompt (only from context, same language as the question, cite chunk numbers) ← answer ← saved in `QuestionHistory`.

## Technical decisions (and their rationale)

- **PostgreSQL + pgvector instead of a separate vector database:** document text, chunks, vectors, and history are all in one database. Editing and deleting documents is atomic (`CASCADE`), and there is no need to synchronize two systems. We have only two containers.
- **Hybrid retrieval (vector + BM25 + RRF):** vector search understands synonyms and cross-lingual questions, while BM25 handles codes, numbers, and exact names. RRF only looks at ranks, so there is no need to normalize the scores of the two methods to a common scale.
- **Local Embedding with fastembed (ONNX):** no key and no separate rate limit, no PyTorch (lightweight image), and multilingual (`paraphrase-multilingual-MiniLM-L12-v2` supports Persian and English; a test matches the model name and dimensions against the official fastembed list). If a model from the E5 family is chosen (e.g. `intfloat/multilingual-e5-large`, 1024 dimensions), the `passage: ` prefixes are applied automatically during indexing and `query: ` during search. The model is stored in a fixed path `FASTEMBED_CACHE_PATH=/opt/models` inside the image. The default model is 384-dimensional; for more accuracy you can set `paraphrase-multilingual-mpnet-base-v2` (768 dimensions): change `EMBEDDING_MODEL` and `EMBEDDING_DIM` and create a new migration.
- **Language model abstraction layer (`llm_factory.py`):** based on `LLM_PROVIDER`, either `ChatGoogleGenerativeAI` (Gemini) or `ChatOpenAI` with the OpenRouter address is created. The rest of the code works only with the standard LangChain interface, so switching is just configuration.
- **Chunk size of 600 characters:** lightweight multilingual Embedding models are trained on short sequences; very long chunks lower quality.
- **The document title is added to the Embedding/BM25 text** so that chunks make sense even without their parent document.
- **`is_indexed` status:** if Embedding fails, the document is saved but excluded from retrieval (so answers don't come from stale chunks), and it is retried with the `reindex` action/endpoint.
- **Persian normalization for BM25 (`services/text.py`):** `ي`/`ك`/`ى` to `ی`/`ک`, removal of tatweel and diacritics, conversion of Persian and Arabic digits to English, removal of the thousands separator (`۱٬۵۰۰٬۰۰۰` is one token), the decimal separator `٫`, removal of invisible characters and punctuation (`؟ ، ؛ « »`). The ZWNJ is preserved in the stored text; it is converted to a space only during tokenization so that "می‌خواهم" and "می خواهم" become the same.
- **RAM usage in gunicorn:** the Embedding model takes several hundred megabytes of RAM and each worker has its own copy; therefore the default is one worker with 4 threads (`GUNICORN_WORKERS`, `GUNICORN_THREADS`), and the model is loaded at startup. `--preload` didn't help because the model is loaded lazily after the fork.
- **Retrieval runs in the same thread:** `RunnableParallel` runs branches in a separate thread, and each thread opened a database connection; therefore the chain is written sequentially.
- **Admin:** submitting a question also works in the admin, and errors are shown inside the form; the history is read-only.

## Limitations and future development

- Indexing happens during upload and concurrently with the request (a few seconds for normal documents). For large files, it can be moved to Celery + Redis.
- BM25 is built in memory over all chunks; it's fine up to a few thousand chunks. For larger scale, you should move to PostgreSQL's own full-text search or a search engine.
- Each question is answered independently (no conversation memory). Adding conversation history to the chain is straightforward.
- Old `doc` files, PDFs, and images are not supported; text inside images in docx is not extracted.
- Free model responses may be slow or rate-limited. With one worker, heavy processing (such as indexing a large document) and requests run on the same worker's threads; for more load you need more workers or more RAM.

## Project structure

```
config/                settings, urls
gunicorn.conf.py       gunicorn configuration
documents/
  models.py            Document, DocumentChunk, QuestionHistory
  services/            text, docx_parser, llm_factory, indexer, ingestion, retriever, qa_chain
  serializers.py views.py urls.py   (API)
  admin.py             admin panel
  tests.py             38 tests (on real PostgreSQL + pgvector; fake Embedding and LLM)
sample_data/           two sample documents + the script that builds them
docs/                  openapi.yaml and the screenshots folder
```

## Testing

```bash
docker compose run --rm web python manage.py test documents --noinput
```

The tests (38 tests) run without internet. The database user must have permission to create the test database and the `vector` extension (the default compose user does).
