"""Deterministic profile keyword derivation and rotation."""

from dataclasses import dataclass

from opportunity_radar.profile.domain import EmploymentPreference, Skill

_LEVEL_RANK = {
    "beginner": 0,
    "iniciante": 0,
    "basic": 0,
    "basico": 0,
    "básico": 0,
    "novice": 0,
    "intermediate": 1,
    "intermediario": 1,
    "intermediário": 1,
    "advanced": 2,
    "avancado": 2,
    "avançado": 2,
    "expert": 3,
    "especialista": 3,
}


@dataclass(frozen=True, slots=True)
class KeywordRotationState:
    block_index: int
    terms_used: tuple[str, ...]


def derive_keywords(
    preferences: EmploymentPreference, skills: tuple[Skill, ...]
) -> tuple[str, ...]:
    """Return normalized target titles and skills at the highest recorded level."""
    named_skills = tuple(
        (skill, skill.canonical_name.strip().casefold())
        for skill in skills
        if skill.canonical_name.strip()
    )
    if named_skills:
        highest_rank = max(
            _LEVEL_RANK.get((skill.level or "").strip().casefold(), -1)
            for skill, _ in named_skills
        )
        top_skills = tuple(
            name
            for skill, name in named_skills
            if _LEVEL_RANK.get((skill.level or "").strip().casefold(), -1)
            == highest_rank
        )
    else:
        top_skills = ()
    candidates = (
        *(title.strip().casefold() for title in preferences.target_titles),
        *top_skills,
    )
    return tuple(dict.fromkeys(term for term in candidates if term))


def rotate(
    terms: tuple[str, ...], *, block_index: int, block_size: int = 10
) -> tuple[str, ...]:
    """Return block at `block_index`, wrapping to first block after final block."""
    if block_size < 1:
        raise ValueError("block_size must be positive")
    if not terms:
        return ()
    block_count = (len(terms) + block_size - 1) // block_size
    offset = (block_index % block_count) * block_size
    return terms[offset : offset + block_size]
