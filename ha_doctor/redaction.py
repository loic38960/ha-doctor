import re

SENSITIVE_KEY_RE = re.compile(
    r"(?i)(password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|secret[_-]?key|bearer|authorization)"
)

SECRET_LINE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_.-]+)\s*:\s*(?P<value>.+?)\s*$"
)


def looks_sensitive_key(key: str) -> bool:
    return bool(SENSITIVE_KEY_RE.search(str(key)))


def redact_line(line: str) -> str:
    """Redact a likely secret value while retaining enough context for a report."""
    match = SECRET_LINE_RE.match(line)
    if not match:
        return line[:240]
    key = match.group("key")
    if looks_sensitive_key(key):
        return f"{match.group('indent')}{key}: <redacted>"
    # Also redact obvious bearer/token-like strings in arbitrary evidence.
    result = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+\-/=]+", "Bearer <redacted>", line)
    result = re.sub(r"\b[A-Fa-f0-9]{40,}\b", "<redacted-hex>", result)
    return result[:240]
