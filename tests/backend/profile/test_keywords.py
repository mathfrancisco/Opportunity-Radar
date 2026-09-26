from opportunity_radar.profile.domain import EmploymentPreference, Skill
from opportunity_radar.profile.keywords import derive_keywords, rotate


def test_derive_keywords_combines_target_titles_and_top_skills() -> None:
    preferences = EmploymentPreference(
        target_titles=(" Backend Engineer ", "backend engineer", "Engenheiro de Software")
    )
    skills = (
        Skill("Python", level="advanced"),
        Skill("React", level="intermediate"),
        Skill("PostgreSQL", level="advanced"),
    )

    assert derive_keywords(preferences, skills) == (
        "backend engineer",
        "engenheiro de software",
        "python",
        "postgresql",
    )


def test_rotate_wraps_around_after_last_block() -> None:
    terms = tuple(f"term-{index}" for index in range(12))

    assert rotate(terms, block_index=0) == tuple(f"term-{index}" for index in range(10))
    assert rotate(terms, block_index=1) == ("term-10", "term-11")
    assert rotate(terms, block_index=2) == tuple(f"term-{index}" for index in range(10))
