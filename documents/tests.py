"""Tests run against a real PostgreSQL + pgvector; only embeddings and the LLM are faked (no network)."""
import hashlib
import io
import math
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from docx import Document as DocxDocument
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from rest_framework.test import APIClient

from documents.models import Document, DocumentChunk, QuestionHistory
from documents.services.docx_parser import extract_text
from documents.services.errors import DocxError
from documents.services.retriever import rrf_fuse
from documents.services.text import normalize_text, tokenize


class FakeEmbeddings(Embeddings):
    """Deterministic hash-based embeddings: texts sharing words get similar vectors."""

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)

    @staticmethod
    def _vec(text, dim=384):
        v = [0.0] * dim
        for tok in tokenize(text):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]


def make_docx(paragraphs=(), table=None) -> bytes:
    d = DocxDocument()
    for p in paragraphs:
        d.add_paragraph(p)
    if table:
        t = d.add_table(rows=len(table), cols=len(table[0]))
        for i, row in enumerate(table):
            for j, val in enumerate(row):
                t.cell(i, j).text = val
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def upload(name, data):
    return SimpleUploadedFile(name, data, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


FAKE_EMB = FakeEmbeddings()
EMB_PATCHES = ("documents.services.indexer.get_embeddings", "documents.services.retriever.get_embeddings")


class BaseCase(TestCase):
    def setUp(self):
        self.patchers = [patch(p, return_value=FAKE_EMB) for p in EMB_PATCHES]
        for p in self.patchers:
            p.start()
            self.addCleanup(p.stop)
        self.client = APIClient()

    def create_doc(self, title="سند تست", content="مرخصی استحقاقی سالانه ۲۶ روز است.\n\nخطای ERR-4721 یعنی توکن نامعتبر."):
        r = self.client.post("/api/documents/", {"title": title, "content": content}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()


class TextTests(TestCase):
    def test_normalize_arabic_letters_and_control_chars(self):
        self.assertEqual(normalize_text("كتاب  يك\u200b\u200f"), "کتاب یک")

    def test_normalize_keeps_zwnj(self):
        self.assertIn("\u200c", normalize_text("می\u200cخواهم"))

    def test_tokenize_persian_digits_and_case(self):
        self.assertEqual(tokenize("ERR-۴۷۲۱ مرخصی"), ["err", "4721", "مرخصی"])

    def test_rrf_prefers_items_found_by_both(self):
        scores = rrf_fuse([[1, 2, 3], [3, 4, 1]], k=60)
        self.assertEqual(max(scores, key=scores.get), 1)
        self.assertGreater(scores[3], scores[2])


class PersianNormalizationTests(TestCase):
    def test_arabic_letters_equal_persian_in_search(self):
        self.assertEqual(tokenize("كتاب يك"), tokenize("کتاب یک"))

    def test_zwnj_and_punctuation(self):
        self.assertEqual(tokenize("«می\u200cخواهم»، آیا؟"), ["می", "خواهم", "آیا"])

    def test_thousand_separators_and_decimals(self):
        self.assertEqual(tokenize("۱٬۵۰۰٬۰۰۰ و 2,000 و ۳٫۵"), ["1500000", "و", "2000", "و", "3.5"])

    def test_diacritics_and_tatweel_removed(self):
        self.assertEqual(tokenize("مَرخَصـی"), tokenize("مرخصی"))


class EmbeddingTests(TestCase):
    def test_default_model_is_multilingual_and_dim_matches(self):
        from django.conf import settings
        from fastembed import TextEmbedding

        info = {m["model"]: m for m in TextEmbedding.list_supported_models()}
        self.assertIn(settings.EMBEDDING_MODEL, info)
        self.assertIn("multilingual", settings.EMBEDDING_MODEL.lower())
        self.assertEqual(info[settings.EMBEDDING_MODEL]["dim"], settings.EMBEDDING_DIM)

    def _fake_model(self, seen):
        import numpy as np

        class M:
            def embed(self, texts, batch_size=32):
                seen.extend(texts)
                return (np.zeros(3) for _ in texts)

        return M()

    def test_e5_models_get_passage_and_query_prefixes(self):
        from documents.services.llm_factory import LocalEmbeddings

        seen = []
        emb = LocalEmbeddings("intfloat/multilingual-e5-large", "/tmp")
        emb._model = self._fake_model(seen)
        emb.embed_documents(["الف"])
        emb.embed_query("ب")
        self.assertEqual(seen, ["passage: الف", "query: ب"])

    def test_non_e5_models_get_no_prefix(self):
        from documents.services.llm_factory import LocalEmbeddings

        seen = []
        emb = LocalEmbeddings("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "/tmp")
        emb._model = self._fake_model(seen)
        emb.embed_documents(["الف"])
        emb.embed_query("ب")
        self.assertEqual(seen, ["الف", "ب"])


class LLMFactoryTests(TestCase):
    def setUp(self):
        from documents.services import llm_factory

        llm_factory.get_llm.cache_clear()
        self.addCleanup(llm_factory.get_llm.cache_clear)
        self.get_llm = llm_factory.get_llm

    def test_gemini_provider_builds_google_client(self):
        with override_settings(LLM_PROVIDER="gemini", LLM_MODEL="gemini-4-hydrogen", GEMINI_API_KEY="k"):
            llm = self.get_llm()
        self.assertEqual(type(llm).__name__, "ChatGoogleGenerativeAI")
        self.assertEqual(llm.model, "gemini-4-hydrogen")

    def test_openrouter_provider_builds_openai_compatible_client(self):
        with override_settings(LLM_PROVIDER="openrouter", LLM_MODEL="openrouter/free", OPENROUTER_API_KEY="k"):
            llm = self.get_llm()
        self.assertEqual(type(llm).__name__, "ChatOpenAI")
        self.assertIn("openrouter.ai", llm.openai_api_base)

    def test_missing_key_per_provider(self):
        from documents.services.errors import LLMConfigError

        for provider, msg in (("gemini", "GEMINI_API_KEY"), ("openrouter", "OPENROUTER_API_KEY")):
            with override_settings(LLM_PROVIDER=provider, GEMINI_API_KEY="", OPENROUTER_API_KEY=""):
                with self.assertRaisesMessage(LLMConfigError, msg):
                    self.get_llm()

    def test_unknown_provider(self):
        from documents.services.errors import LLMConfigError

        with override_settings(LLM_PROVIDER="foo"):
            with self.assertRaises(LLMConfigError):
                self.get_llm()


class DocxTests(TestCase):
    def test_extracts_paragraphs_and_table_with_headers(self):
        data = make_docx(["مقدمه"], table=[["پلن", "حد"], ["Pro", "600"], ["Free", "60"]])
        text = extract_text(io.BytesIO(data))
        self.assertIn("مقدمه", text)
        self.assertIn("پلن: Pro | حد: 600", text)

    def test_invalid_file_raises(self):
        with self.assertRaises(DocxError):
            extract_text(io.BytesIO(b"not a docx"))


class DocumentApiTests(BaseCase):
    def test_create_from_text_indexes(self):
        doc = self.create_doc()
        self.assertTrue(doc["is_indexed"])
        self.assertGreaterEqual(doc["chunk_count"], 1)

    def test_create_from_docx_file(self):
        data = make_docx(["قانون شماره یک"], table=[["نوع", "مدت"], ["ازدواج", "۷ روز"]])
        r = self.client.post("/api/documents/", {"title": "فایل", "file": upload("a.docx", data)}, format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        detail = self.client.get(f"/api/documents/{r.json()['id']}/").json()
        self.assertIn("نوع: ازدواج | مدت: ۷ روز", detail["content"])
        self.assertTrue(detail["is_indexed"])

    def test_invalid_docx_returns_400(self):
        r = self.client.post("/api/documents/", {"title": "x", "file": upload("a.docx", b"junk")}, format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Document.objects.count(), 0)

    def test_wrong_extension_returns_400(self):
        r = self.client.post("/api/documents/", {"title": "x", "file": upload("a.txt", b"hi")}, format="multipart")
        self.assertEqual(r.status_code, 400)

    def test_empty_document_rejected(self):
        r = self.client.post("/api/documents/", {"title": "x"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_update_content_replaces_chunks(self):
        doc = self.create_doc()
        old_ids = set(DocumentChunk.objects.filter(document_id=doc["id"]).values_list("id", flat=True))
        r = self.client.patch(f"/api/documents/{doc['id']}/", {"content": "متن کاملا جدید درباره دورکاری"}, format="json")
        self.assertEqual(r.status_code, 200)
        chunks = DocumentChunk.objects.filter(document_id=doc["id"])
        self.assertFalse(old_ids & set(chunks.values_list("id", flat=True)))
        self.assertIn("دورکاری", chunks.first().content)

    def test_title_only_update_keeps_content(self):
        doc = self.create_doc()
        r = self.client.put(f"/api/documents/{doc['id']}/", {"title": "عنوان جدید"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Document.objects.get(pk=doc["id"]).title, "عنوان جدید")
        self.assertTrue(Document.objects.get(pk=doc["id"]).content)

    def test_delete_cascades_chunks(self):
        doc = self.create_doc()
        self.assertEqual(self.client.delete(f"/api/documents/{doc['id']}/").status_code, 204)
        self.assertEqual(DocumentChunk.objects.count(), 0)

    def test_list_search_and_filter(self):
        self.create_doc("الف", "گربه")
        self.create_doc("ب", "سگ")
        r = self.client.get("/api/documents/?search=گربه").json()
        self.assertEqual(r["count"], 1)
        self.assertEqual(self.client.get("/api/documents/?is_indexed=false").json()["count"], 0)

    def test_embedding_failure_keeps_document_and_flags_error(self):
        with patch("documents.services.indexer.get_embeddings", side_effect=RuntimeError("down")):
            r = self.client.post("/api/documents/", {"title": "x", "content": "متن"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertFalse(r.json()["is_indexed"])
        self.assertIn("down", r.json()["index_error"])
        # once the cause is fixed, reindex works
        r2 = self.client.post(f"/api/documents/{r.json()['id']}/reindex/")
        self.assertTrue(r2.json()["is_indexed"])


@override_settings(LLM_MODEL="fake-model")
class AskApiTests(BaseCase):
    def ask(self, question, answer="پاسخ تستی [1]"):
        fake = FakeListChatModel(responses=[answer])
        with patch("documents.services.qa_chain.get_llm", return_value=fake):
            return self.client.post("/api/ask/", {"question": question}, format="json")

    def test_ask_returns_answer_sources_and_saves_history(self):
        self.create_doc("سیاست", "مرخصی استحقاقی سالانه ۲۶ روز است.")
        r = self.ask("مرخصی استحقاقی چند روز است؟")
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertEqual(body["answer"], "پاسخ تستی [1]")
        self.assertEqual(body["model_used"], "fake-model")
        self.assertEqual(body["sources"][0]["title"], "سیاست")
        self.assertEqual(QuestionHistory.objects.count(), 1)

    def test_exact_code_found_by_bm25(self):
        self.create_doc("A", "این سند درباره غذا و آشپزی است. " * 20)
        self.create_doc("B", "Error ERR-4721 means the token is invalid. Rotate your key.")
        r = self.ask("What is ERR-4721?").json()
        self.assertEqual(r["sources"][0]["title"], "B")
        self.assertGreater(r["sources"][0]["bm25_score"], 0)

    def test_no_documents_skips_llm(self):
        with patch("documents.services.qa_chain.get_llm", side_effect=AssertionError("LLM must not be called")):
            r = self.client.post("/api/ask/", {"question": "سلام؟"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertIn("اطلاعات کافی", r.json()["answer"])
        self.assertEqual(r.json()["sources"], [])

    def test_english_question_without_docs_gets_english_message(self):
        r = self.client.post("/api/ask/", {"question": "hello?"}, format="json")
        self.assertIn("do not contain", r.json()["answer"])

    def test_missing_api_key_gives_503_and_no_history(self):
        self.create_doc()
        with override_settings(LLM_PROVIDER="gemini", GEMINI_API_KEY=""):
            from documents.services import llm_factory

            llm_factory.get_llm.cache_clear()
            r = self.client.post("/api/ask/", {"question": "مرخصی استحقاقی چند روز است؟"}, format="json")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(QuestionHistory.objects.count(), 0)

    def test_llm_error_gives_502(self):
        self.create_doc()
        with patch("documents.services.qa_chain.get_llm", side_effect=RuntimeError("429 rate limit")):
            r = self.client.post("/api/ask/", {"question": "مرخصی استحقاقی چند روز است؟"}, format="json")
        self.assertEqual(r.status_code, 502)
        self.assertEqual(QuestionHistory.objects.count(), 0)

    def test_validation(self):
        self.assertEqual(self.client.post("/api/ask/", {"question": "  "}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/ask/", {}, format="json").status_code, 400)

    def test_history_endpoints(self):
        self.create_doc()
        self.ask("مرخصی استحقاقی چند روز است؟")
        lst = self.client.get("/api/history/").json()
        self.assertEqual(lst["count"], 1)
        detail = self.client.get(f"/api/history/{lst['results'][0]['id']}/").json()
        self.assertTrue(detail["sources"])


@override_settings(LLM_MODEL="fake-model")
class AdminTests(BaseCase):
    def setUp(self):
        super().setUp()
        get_user_model().objects.create_superuser("admin", "a@a.com", "pass")
        self.client.login(username="admin", password="pass")

    def test_admin_upload_docx_indexes(self):
        data = make_docx(["متن ادمین"])
        r = self.client.post(
            "/admin/documents/document/add/",
            {"title": "ادمین", "file": upload("x.docx", data), "content": "", "chunks-TOTAL_FORMS": 0, "chunks-INITIAL_FORMS": 0},
            format="multipart",
        )
        self.assertEqual(r.status_code, 302, getattr(r, "content", b"")[:500])
        doc = Document.objects.get()
        self.assertTrue(doc.is_indexed)
        self.assertIn("متن ادمین", doc.content)

    def test_admin_changelists_load(self):
        for url in ("/admin/documents/document/", "/admin/documents/questionhistory/"):
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_admin_ask_question_generates_answer(self):
        Document.objects.create(title="d", content="مرخصی ۲۶ روز است")
        from documents.services.ingestion import reindex

        reindex(Document.objects.get())
        fake = FakeListChatModel(responses=["۲۶ روز [1]"])
        with patch("documents.services.qa_chain.get_llm", return_value=fake):
            r = self.client.post("/admin/documents/questionhistory/add/", {"question": "مرخصی چند روز است"})
        self.assertEqual(r.status_code, 302, getattr(r, "content", b"")[:500])
        self.assertEqual(QuestionHistory.objects.get().answer, "۲۶ روز [1]")
