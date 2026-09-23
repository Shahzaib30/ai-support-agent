import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lightweight tokenizer shared by BM25 indexing and querying."""
    return _TOKEN_RE.findall(text.lower())
