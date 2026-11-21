from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from documents.models import Document
from documents.services.docx_parser import extract_text
from documents.services.ingestion import reindex

SAMPLES = {
    "company_policy_fa.docx": "آیین‌نامه منابع انسانی شرکت نمونه",
    "technical_guide_en.docx": "Orion API Gateway - Technical Guide",
}


class Command(BaseCommand):
    help = "اسناد نمونه پوشه sample_data را (اگر قبلا اضافه نشده‌اند) ثبت و ایندکس می‌کند."

    def handle(self, *args, **options):
        for filename, title in SAMPLES.items():
            if Document.objects.filter(title=title).exists():
                self.stdout.write(f"موجود است: {title}")
                continue
            path = Path(settings.BASE_DIR) / "sample_data" / filename
            with path.open("rb") as fh:
                doc = Document(title=title, content=extract_text(fh))
                fh.seek(0)
                doc.file.save(filename, File(fh), save=False)
                doc.save()
            ok, error = reindex(doc)
            self.stdout.write(self.style.SUCCESS(f"ثبت شد: {title}") if ok else self.style.ERROR(f"{title}: {error}"))
