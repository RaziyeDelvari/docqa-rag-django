from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from pgvector.django import HnswIndex, VectorField


class Document(models.Model):
    title = models.CharField("عنوان", max_length=255)
    file = models.FileField(
        "فایل docx",
        upload_to="documents/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(["docx"])],
        help_text="در صورت آپلود فایل، متن سند از روی فایل جایگزین می‌شود.",
    )
    content = models.TextField("متن کامل", blank=True)
    is_indexed = models.BooleanField("ایندکس‌شده", default=False)
    index_error = models.TextField("خطای ایندکس", blank=True)
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین ویرایش", auto_now=True)

    class Meta:
        verbose_name = "سند"
        verbose_name_plural = "اسناد"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class DocumentChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.PositiveIntegerField("شماره قطعه")
    content = models.TextField("متن قطعه")
    embedding = VectorField(dimensions=settings.EMBEDDING_DIM)

    class Meta:
        verbose_name = "قطعه"
        verbose_name_plural = "قطعه‌ها"
        ordering = ["document_id", "chunk_index"]
        constraints = [models.UniqueConstraint(fields=["document", "chunk_index"], name="uniq_chunk_per_doc")]
        indexes = [
            HnswIndex(
                name="chunk_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]

    def __str__(self):
        return f"{self.document_id}#{self.chunk_index}"


class QuestionHistory(models.Model):
    question = models.TextField("پرسش")
    answer = models.TextField("پاسخ", blank=True)
    sources = models.JSONField("منابع", default=list, blank=True)
    model_used = models.CharField("مدل", max_length=200, blank=True)
    created_at = models.DateTimeField("زمان", auto_now_add=True)

    class Meta:
        verbose_name = "پرسش و پاسخ"
        verbose_name_plural = "تاریخچه پرسش و پاسخ"
        ordering = ["-created_at"]

    def __str__(self):
        return self.question[:60]


@receiver(post_delete, sender=Document)
def delete_file_with_document(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
