import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"\b(?:0\d{9}|04\d{8})\b")


def scan_output(text: str) -> str:
    """Redact contact details on the way out of a model, before save or show."""
    text = _EMAIL.sub("[redacted-email]", text)
    text = _PHONE.sub("[redacted-phone]", text)
    return text
