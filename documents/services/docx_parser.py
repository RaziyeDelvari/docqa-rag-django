"""Extracts text from docx: paragraphs and tables in document order."""
from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from .errors import DocxError
from .text import normalize_text


def _table_to_lines(table: Table) -> list[str]:
    rows = []
    for row in table.rows:
        cells, seen = [], set()
        for cell in row.cells:
            if id(cell._tc) in seen:  # merged cells are returned several times
                continue
            seen.add(id(cell._tc))
            cells.append(" ".join(cell.text.split()))
        rows.append(cells)
    if not rows:
        return []

    header = rows[0]
    has_header = len(rows) > 1 and all(header) and len(set(header)) == len(header)
    if not has_header:
        return [" | ".join(c for c in r if c) for r in rows if any(r)]
    # write each row with its column names so it stays meaningful after chunking
    lines = []
    for r in rows[1:]:
        parts = [f"{h}: {v}" for h, v in zip(header, r) if v]
        if parts:
            lines.append(" | ".join(parts))
    return lines


def extract_text(file) -> str:
    """file: a path or file-like object. Raises DocxError if it cannot be parsed."""
    try:
        doc = DocxDocument(file)
        lines = []
        for block in doc.iter_inner_content():
            if isinstance(block, Paragraph):
                lines.append(block.text)
            elif isinstance(block, Table):
                lines.extend(_table_to_lines(block))
    except Exception as exc:
        raise DocxError("فایل ارسالی یک فایل docx معتبر نیست.") from exc
    return normalize_text("\n".join(lines))
