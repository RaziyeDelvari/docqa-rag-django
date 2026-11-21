from django import forms
from django.contrib import admin, messages
from django.db.models import Count
from django.utils.html import format_html

from .models import Document, DocumentChunk, QuestionHistory
from .services.errors import ServiceError
from .services.ingestion import reindex, resolve_content
from .services.qa_chain import answer_question


class ChunkInline(admin.TabularInline):
    """Read-only view of the indexed chunks."""

    model = DocumentChunk
    fields = ["chunk_index", "content"]
    readonly_fields = fields
    extra = 0
    can_delete = False
    verbose_name_plural = "قطعه‌های ایندکس‌شده"

    def has_add_permission(self, request, obj=None):
        return False


class DocumentAdminForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "file", "content"]

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        file, content = data.get("file"), data.get("content")
        file_changed = "file" in self.changed_data and bool(file)
        if file_changed or "content" in self.changed_data or not self.instance.pk:
            try:
                # skipped when neither file nor content changed (e.g. a title-only edit)
                self.resolved_content = resolve_content(file if file_changed else None, content)
            except ServiceError as exc:
                raise forms.ValidationError(str(exc))
        return data


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    form = DocumentAdminForm
    list_display = ["title", "is_indexed", "chunk_count", "updated_at"]
    list_filter = ["is_indexed"]
    search_fields = ["title", "content"]
    readonly_fields = ["is_indexed", "index_error", "created_at", "updated_at"]
    fields = ["title", "file", "content", "is_indexed", "index_error", "created_at", "updated_at"]
    inlines = [ChunkInline]
    actions = ["reindex_selected"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_chunks=Count("chunks"))

    @admin.display(description="تعداد قطعه", ordering="_chunks")
    def chunk_count(self, obj):
        return obj._chunks

    def save_model(self, request, obj, form, change):
        needs_index = not change or not obj.is_indexed
        if hasattr(form, "resolved_content"):
            obj.content = form.resolved_content
            needs_index = True
        if "title" in form.changed_data:
            needs_index = True
        super().save_model(request, obj, form, change)
        if needs_index:
            ok, error = reindex(obj)
            if ok:
                self.message_user(request, "سند ایندکس شد.", messages.SUCCESS)
            else:
                self.message_user(request, f"سند ذخیره شد ولی ایندکس نشد: {error}", messages.ERROR)

    @admin.action(description="ایندکس‌گذاری مجدد اسناد انتخاب‌شده")
    def reindex_selected(self, request, queryset):
        done = 0
        for doc in queryset:
            ok, error = reindex(doc)
            if ok:
                done += 1
            else:
                self.message_user(request, f"«{doc.title}»: {error}", messages.ERROR)
        if done:
            self.message_user(request, f"{done} سند دوباره ایندکس شد.", messages.SUCCESS)


class AskForm(forms.ModelForm):
    """Admin form for asking a question. The answer is generated during validation so that failures are shown inside the form."""

    class Meta:
        model = QuestionHistory
        fields = ["question"]

    def clean_question(self):
        question = self.cleaned_data["question"].strip()
        if not question:
            raise forms.ValidationError("پرسش نباید خالی باشد.")
        try:
            self.result = answer_question(question)
        except ServiceError as exc:
            raise forms.ValidationError(str(exc))
        return question


@admin.register(QuestionHistory)
class QuestionHistoryAdmin(admin.ModelAdmin):
    form = AskForm
    list_display = ["short_question", "short_answer", "model_used", "created_at"]
    search_fields = ["question", "answer"]
    readonly_fields = ["question", "answer", "sources_pretty", "model_used", "created_at"]

    def get_fields(self, request, obj=None):
        return ["question"] if obj is None else self.readonly_fields

    def get_readonly_fields(self, request, obj=None):
        return [] if obj is None else self.readonly_fields

    def has_change_permission(self, request, obj=None):
        return False  # history is read-only; adding a new question is still allowed

    def save_model(self, request, obj, form, change):
        obj.answer = form.result["answer"]
        obj.sources = form.result["sources"]
        obj.model_used = form.result["model_used"]
        super().save_model(request, obj, form, change)

    @admin.display(description="پرسش")
    def short_question(self, obj):
        return obj.question[:70]

    @admin.display(description="پاسخ")
    def short_answer(self, obj):
        return obj.answer[:90]

    @admin.display(description="منابع")
    def sources_pretty(self, obj):
        rows = [
            f"[{s.get('rank')}] {s.get('title')} (قطعه {s.get('chunk_index')}) - امتیاز RRF: {s.get('rrf_score')}\n{s.get('content')}"
            for s in obj.sources
        ]
        return format_html('<pre style="white-space:pre-wrap">{}</pre>', "\n\n".join(rows) or "-")
