"""Domain synonyms for the Inbox full-text search (card F17-03, SPEC 37 §10).

Versioned (`SYNONYMS_VERSION`) so the dictionary can change without reindexing: it is
applied at query time, never baked into `search_document`.
"""

from __future__ import annotations

import re

SYNONYMS_VERSION = "synonyms-v1"

_GROUPS: tuple[frozenset[str], ...] = (
    frozenset(
        {
            "desenvolvedor",
            "desenvolvedora",
            "developer",
            "engineer",
            "engenheiro",
            "engenheira",
        }
    ),
    frozenset({"senior", "sênior", "sr"}),
    frozenset({"pleno", "mid", "mid-level"}),
    frozenset({"junior", "júnior", "jr"}),
    frozenset({"remoto", "remote"}),
    frozenset({"dados", "data"}),
    frozenset({"vaga", "job"}),
)

_TERM_TO_SYNONYMS: dict[str, frozenset[str]] = {
    term.lower(): group for group in _GROUPS for term in group
}

#: A quoted phrase, or a single non-space token.
_TOKEN_RE = re.compile(r'"[^"]*"|\S+')


def synonym_variants(query: str) -> list[str]:
    """`query` plus one variant per unquoted, non-negated token that has a synonym.

    Each variant substitutes exactly one token, keeping the rest of the query text —
    including `AND`/`OR` keywords, other tokens and their order — untouched. Quoted
    phrases (`"..."`) and negated tokens (`-word`) are never substituted, so
    `websearch_to_tsquery`'s phrase and NOT semantics survive (SPEC 37, "Contrato de
    consulta"). The caller ORs the resulting tsqueries together.
    """
    tokens = _TOKEN_RE.findall(query)
    variants = [query]
    seen = {query}
    for index, token in enumerate(tokens):
        if token.startswith('"') or token.startswith("-"):
            continue
        synonyms = _TERM_TO_SYNONYMS.get(token.lower())
        if not synonyms:
            continue
        for synonym in sorted(synonyms):
            if synonym == token.lower():
                continue
            candidate_tokens = list(tokens)
            candidate_tokens[index] = synonym
            candidate = " ".join(candidate_tokens)
            if candidate not in seen:
                seen.add(candidate)
                variants.append(candidate)
    return variants


__all__ = ["SYNONYMS_VERSION", "synonym_variants"]
