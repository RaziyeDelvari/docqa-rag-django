"""Persian/English text normalization and a simple tokenizer for BM25."""
import re

# Arabic letter variants -> Persian, drop tatweel
_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ھ": "ه", "ہ": "ه", "ـ": ""})
# Persian and Arabic-Indic digits -> ASCII (search only)
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# control and invisible characters; ZWNJ (U+200C) is intentionally kept
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b\u200d\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_DIACRITICS = re.compile(r"[\u064b-\u065f\u0670]")
_SPACES = re.compile(r"[ \t\u00a0]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_THOUSANDS = re.compile(r"(?<=\d)[٬,](?=\d{3})")  # thousands separators between digit groups: 1,500,000 -> 1500000
_TOKEN = re.compile(r"\d+\.\d+|\w+", re.UNICODE)  # a decimal number is one token; punctuation is not tokenized


def normalize_text(text: str) -> str:
    """Normalization for stored text (gentle, does not change meaning)."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_LETTERS)
    text = _CONTROL.sub("", text)
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANK_LINES.sub("\n\n", text).strip()


def tokenize(text: str) -> list[str]:
    """BM25 tokenizer: normalize, ASCII digits, drop separators and diacritics, ZWNJ -> space, lowercase."""
    text = normalize_text(text).translate(_DIGITS).replace("٫", ".")
    text = _THOUSANDS.sub("", text)
    text = _DIACRITICS.sub("", text).replace("ۀ", "ه").replace("\u200c", " ").lower()
    return _TOKEN.findall(text)


def is_persian(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", text or ""))
