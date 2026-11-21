# DocQA | Document Q&A System

A system for uploading documents (plain text or `docx` files), searching through them, and answering questions using an LLM—strictly based on the content of those documents. Both questions and documents can be in Persian or English (including asking Persian questions about English documents).

**Stack:** Django 5 + Django Admin (UI) + Django REST Framework (API & Swagger) + LangChain (RAG chain) + PostgreSQL with pgvector + Docker. The default LLM is Gemini (Google AI Studio), and you can switch to OpenRouter by updating `.env`.

## Running with Docker

Prerequisites: Docker and Docker Compose.

```bash
cp .env.example .env
# In .env, replace GEMINI_API_KEY with your free Google AI Studio key
docker compose up --build
```
