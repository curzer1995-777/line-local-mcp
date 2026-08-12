from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SECRET_LABEL = re.compile(
    r"(?i)(\bpassword\b|\bpasswd\b|\bpwd\b|密碼|密码|驗證碼|验证码)"
    r"(\s*[:：=]\s*)([^\s,，;；]+)"
)
_URL = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_SECRET_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "key",
    "password",
    "passwd",
    "pwd",
    "secret",
    "sig",
    "signature",
    "token",
}


def _redact_url(match: re.Match[str]) -> str:
    raw = match.group(0)
    trailing = ""
    while raw and raw[-1] in ".,，;；!?！？":
        trailing = raw[-1] + trailing
        raw = raw[:-1]
    try:
        parts = urlsplit(raw)
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        changed = False
        safe_pairs: list[tuple[str, str]] = []
        for key, value in pairs:
            if key.lower() in _SECRET_QUERY_KEYS:
                value = "[REDACTED]"
                changed = True
            safe_pairs.append((key, value))
        if not changed:
            return match.group(0)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe_pairs), parts.fragment)) + trailing
    except ValueError:
        return "[REDACTED_URL]" + trailing


def redact_text(text: str) -> tuple[str, bool]:
    redacted = _SECRET_LABEL.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    redacted = _URL.sub(_redact_url, redacted)
    return redacted, redacted != text
