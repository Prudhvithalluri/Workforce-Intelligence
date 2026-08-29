import hashlib


def safe_id(value: str | None) -> str:
    """Return a short identifier that cannot reveal the original value."""
    if not value:
        return "none"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]