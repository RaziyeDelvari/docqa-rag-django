"""Builds two sample documents (Persian and English) with paragraphs and tables.
Run: python sample_data/generate_samples.py
"""
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

OUT = Path(__file__).parent


def rtl(paragraph):
    pPr = paragraph._p.get_or_add_pPr()
    pPr.append(OxmlElement("w:bidi"))


def add_table(doc, rows, rtl_table=False):
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            table.cell(i, j).text = val
    if rtl_table:
        tblPr = table._tbl.tblPr
        tblPr.append(OxmlElement("w:bidiVisual"))


def persian():
    d = Document()
    blocks = [
        ("h", "آیین‌نامه منابع انسانی شرکت نمونه"),
        ("p", "این سند قوانین اصلی کار در شرکت نمونه را برای همه کارکنان توضیح می‌دهد. نسخه ۱۴۰۴."),
        ("h", "ساعت کاری"),
        ("p", "ساعت کاری رسمی از شنبه تا چهارشنبه، از ساعت ۸ صبح تا ۱۶ عصر است. ورود پس از ساعت ۹ صبح تاخیر محسوب می‌شود و باید به مدیر مستقیم اطلاع داده شود."),
        ("h", "دورکاری"),
        ("p", "کارکنان پس از تایید مدیر مستقیم می‌توانند حداکثر دو روز در هفته دورکار باشند. در دوره آزمایشی سه‌ماهه، دورکاری مجاز نیست. روزهای جلسه تیمی (یکشنبه‌ها) حضور در شرکت اجباری است."),
        ("h", "انواع مرخصی"),
        ("p", "جدول زیر انواع مرخصی و شرایط هر کدام را نشان می‌دهد."),
        ("t", [
            ["نوع مرخصی", "مدت", "شرایط"],
            ["استحقاقی", "۲۶ روز در سال", "با تایید مدیر مستقیم و ثبت در سامانه حداقل ۳ روز قبل"],
            ["استعلاجی", "طبق گواهی پزشک", "ارائه گواهی پزشک معتبر تا ۴۸ ساعت پس از بازگشت"],
            ["ازدواج", "۷ روز", "ارائه سند ازدواج، یک بار در طول همکاری"],
            ["فوت بستگان درجه یک", "۳ روز", "بدون نیاز به تایید قبلی"],
        ]),
        ("h", "ماموریت و هزینه‌ها"),
        ("p", "هزینه ماموریت‌های داخل کشور شامل بلیت رفت و برگشت، اقامت و ۱٬۵۰۰٬۰۰۰ تومان کمک‌هزینه غذا برای هر روز است. تسویه هزینه‌ها باید ظرف ۱۰ روز کاری پس از بازگشت از ماموریت با ارائه اصل فاکتورها انجام شود."),
        ("h", "امنیت اطلاعات"),
        ("p", "رمز عبور حساب‌های سازمانی باید حداقل ۱۲ کاراکتر باشد و هر ۹۰ روز تغییر کند. در صورت بروز مشکل فنی با داخلی ۲۱۰۴ تماس بگیرید یا در سامانه پشتیبانی تیکت ثبت کنید."),
    ]
    for kind, val in blocks:
        if kind == "h":
            rtl(d.add_heading(val, level=1))
        elif kind == "p":
            rtl(d.add_paragraph(val))
        else:
            add_table(d, val, rtl_table=True)
    d.save(OUT / "company_policy_fa.docx")


def english():
    d = Document()
    d.add_heading("Orion API Gateway - Technical Guide", level=1)
    d.add_paragraph("Orion is an API gateway that handles authentication, rate limiting and request routing for internal services. This guide covers limits, error codes and deployment.")
    d.add_heading("Rate limits", level=2)
    d.add_paragraph("Every API key belongs to a plan. Requests above the plan limit receive HTTP 429 with the error code ERR-4290.")
    add_table(d, [
        ["Plan", "Requests per minute", "Burst"],
        ["Free", "60", "10"],
        ["Pro", "600", "100"],
        ["Enterprise", "6000", "1000"],
    ])
    d.add_heading("Error codes", level=2)
    add_table(d, [
        ["Code", "Meaning", "Recommended action"],
        ["ERR-4001", "Invalid or expired token", "Rotate the API key from the dashboard"],
        ["ERR-4290", "Rate limit exceeded", "Retry with exponential backoff"],
        ["ERR-5003", "Upstream service timeout", "Check the health of the upstream service"],
    ])
    d.add_heading("Deployment", level=2)
    d.add_paragraph("Orion ships as a Docker image. Run it with the command docker run -p 8080:8080 orion/gateway:2.4 and mount the configuration file at /etc/orion/config.yaml. The health endpoint is /healthz on port 8080.")
    d.add_heading("Logging and retention", level=2)
    d.add_paragraph("Access logs are kept for 30 days and audit logs for 365 days. Logs are stored in JSON format and never contain request bodies.")
    d.save(OUT / "technical_guide_en.docx")


if __name__ == "__main__":
    persian()
    english()
