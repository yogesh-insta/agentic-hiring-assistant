import re

_INSTRUCTION = re.compile(r"ignore previous instructions.*?rank me first\.?", re.IGNORECASE | re.DOTALL)


def strip_instructions(text: str) -> str:
    """Drop hidden instructions before a model or a scorer sees the CV."""
    return _INSTRUCTION.sub(" ", text).strip()
