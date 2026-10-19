"""Domain synonyms for the Inbox full-text search (card F17-03, SPEC 37 §10).

Versioned (`SYNONYMS_VERSION`) so the dictionary can change without reindexing: it is
applied at query time, never baked into `search_document`.
"""

from __future__ import annotations

import re

SYNONYMS_VERSION = "synonyms-v2"

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


#: Above this many tokens the per-concept form is skipped (keeps the tsquery bounded).
MAX_SYNONYM_GROUPS = 8


def synonym_groups(query: str) -> tuple[list[list[str]], str] | None:
    """Split a plain query into synonym concepts plus the remaining text.

    Returns `(groups, rest)`: one group per token that has synonyms (the token plus its
    synonyms, ANDed by the caller), and the other tokens joined in their original order
    (`rest`, parsed by the caller in each dictionary so each drops its own stopwords).
    This lets `desenvolvedor dados` match "Data Developer".

    Returns `None` when no token has synonyms, or the query has quotes, a negated token
    (`-word`), an `OR`, or more than `MAX_SYNONYM_GROUPS` tokens; the caller then keeps
    the `synonym_variants` path so `websearch_to_tsquery` semantics are preserved.
    """
    if '"' in query:
        return None
    tokens = query.split()
    if not tokens or len(tokens) > MAX_SYNONYM_GROUPS:
        return None
    if any(token.startswith("-") or token.lower() == "or" for token in tokens):
        return None
    groups: list[list[str]] = []
    rest: list[str] = []
    for token in tokens:
        synonyms = _TERM_TO_SYNONYMS.get(token.lower())
        if synonyms:
            groups.append([token, *sorted(s for s in synonyms if s != token.lower())])
        else:
            rest.append(token)
    if not groups:
        return None
    return groups, " ".join(rest)


__all__ = ["SYNONYMS_VERSION", "synonym_groups", "synonym_variants"]
