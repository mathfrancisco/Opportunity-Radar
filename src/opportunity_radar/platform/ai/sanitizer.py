"""Strip personal data and secrets from a payload before it leaves the machine.

SPEC 43 section 8.3: the invariant "nothing leaves the machine" no longer holds for the
analysis call, since it goes to Groq. What replaces it is `sanitize_for_llm`: it runs on
the whole payload before the prompt is rendered and before the payload hash is computed
(card F20-17), so neither the model nor the cache key ever see a name, an e-mail, a
phone number, a document number, a personal URL or a leaked credential. Professional
evidence — title, skills, project description, the posting text — passes through
unchanged; only the identifying and secret parts are removed or masked.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

#: Dict keys that never reach the model, wherever they appear in the payload's shape.
#: Matched case-insensitively so `Full_Name` and `full_name` are both removed.
PII_KEYS = frozenset(
    {
        "name",
        "full_name",
        "email",
        "phone",
        "address",
        "cpf",
        "document",
        "linkedin_url",
        "github_url",
        "website",
        "birth_date",
    }
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_PHONE_RE = re.compile(r"(?:\+?\d{2}\s?)?\(?\d{2}\)?\s?9?\d{4}-?\d{4}")
_LINKEDIN_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/\S+", re.IGNORECASE)
_GITHUB_RE = re.compile(r"https?://(?:www\.)?github\.com/\S+", re.IGNORECASE)
_GROQ_KEY_RE = re.compile(r"gsk_[A-Za-z0-9]{20,}")
_OPENAI_KEY_RE = re.compile(r"sk-[A-Za-z0-9]{20,}")
_TAVILY_KEY_RE = re.compile(r"tvly-[A-Za-z0-9]{20,}")
_BEARER_RE = re.compile(r"Bearer\s+\S+")

#: Applied in order: secrets and personal URLs first (so a masked e-mail or phone inside
#: a URL query string does not shadow the more specific pattern), then contact patterns.
_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_BEARER_RE, "[segredo]"),
    (_GROQ_KEY_RE, "[segredo]"),
    (_OPENAI_KEY_RE, "[segredo]"),
    (_TAVILY_KEY_RE, "[segredo]"),
    (_LINKEDIN_RE, "[url-pessoal]"),
    (_GITHUB_RE, "[url-pessoal]"),
    (_EMAIL_RE, "[email]"),
    (_CPF_RE, "[documento]"),
    (_PHONE_RE, "[telefone]"),
)


def _sanitize_text(value: str) -> str:
    for pattern, replacement in _TEXT_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def sanitize_for_llm(value: Any) -> Any:
    """Return a sanitized copy of `value`; the original is never modified in place.

    Recurses over `dict` and `list`/`tuple` structures. A dict key in `PII_KEYS`
    (case-insensitive) is dropped entirely — its value is never inspected, since a
    field named `email` is PII regardless of its content. Every string, wherever it
    appears, is passed through the text patterns above so an e-mail or key embedded in
    free text (a job description, a bio) is still masked.
    """
    if isinstance(value, Mapping):
        return {
            key: sanitize_for_llm(item)
            for key, item in value.items()
            if str(key).lower() not in PII_KEYS
        }
    if isinstance(value, (list, tuple)):
        sanitized = [sanitize_for_llm(item) for item in value]
        return type(value)(sanitized) if isinstance(value, tuple) else sanitized
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


__all__: Sequence[str] = ("PII_KEYS", "sanitize_for_llm")
