from django.conf import settings
from rest_framework import serializers

from .models import Document, QuestionHistory
from .services.errors import ServiceError
from .services.ingestion import reindex, resolve_content


class DocumentListSerializer(serializers.ModelSerializer):
    chunk_count = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["id", "title", "is_indexed", "chunk_count", "created_at", "updated_at"]

    def get_chunk_count(self, obj) -> int:
        count = getattr(obj, "chunk_count", None)
        return obj.chunks.count() if count is None else count


class DocumentSerializer(DocumentListSerializer):
    class Meta(DocumentListSerializer.Meta):
        fields = ["id", "title", "file", "content", "is_indexed", "index_error", "chunk_count", "created_at", "updated_at"]
        read_only_fields = ["is_indexed", "index_error"]
        extra_kwargs = {
            "content": {"required": False, "help_text": "متن سند. اگر file ارسال شود از روی فایل پر می‌شود."},
            "file": {"required": False, "help_text": "فایل docx (حداکثر طبق MAX_UPLOAD_MB)."},
        }

    def validate_file(self, f):
        limit = settings.MAX_UPLOAD_MB * 1024 * 1024
        if f and f.size > limit:
            raise serializers.ValidationError(f"حجم فایل بیشتر از {settings.MAX_UPLOAD_MB} مگابایت است.")
        return f

    def _resolve(self, attrs, required):
        """Build the final content from the file or the content field; service errors become 400s."""
        if not (attrs.get("file") or "content" in attrs or required):
            return
        try:
            attrs["content"] = resolve_content(attrs.get("file"), attrs.get("content"))
        except ServiceError as exc:
            raise serializers.ValidationError({"detail": str(exc)})

    def create(self, validated_data):
        self._resolve(validated_data, required=True)
        doc = super().create(validated_data)
        reindex(doc)
        return doc

    def update(self, instance, validated_data):
        self._resolve(validated_data, required=False)
        needs_index = (
            not instance.is_indexed
            or ("content" in validated_data and validated_data["content"] != instance.content)
            or ("title" in validated_data and validated_data["title"] != instance.title)
        )
        instance = super().update(instance, validated_data)
        if needs_index:
            reindex(instance)
        return instance


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000, help_text="متن پرسش (فارسی یا انگلیسی)")
    top_k = serializers.IntegerField(
        required=False, min_value=1, max_value=15, help_text="تعداد قطعه‌های بازیابی‌شده (پیش‌فرض ۵)"
    )

    def validate_question(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("پرسش نباید خالی باشد.")
        return value


class QuestionHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionHistory
        fields = ["id", "question", "answer", "sources", "model_used", "created_at"]
        read_only_fields = fields
