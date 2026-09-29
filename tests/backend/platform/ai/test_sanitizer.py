"""No personal data or secret reaches the Groq payload (F20-15, SPEC 43 section 8.3)."""

from __future__ import annotations

from opportunity_radar.platform.ai.sanitizer import PII_KEYS, sanitize_for_llm


def test_pii_keys_are_removed_wherever_they_appear() -> None:
    payload = {
        "name": "Maria Souza",
        "profile": {"email": "maria@example.com", "skills": ["python"]},
    }
    sanitized = sanitize_for_llm(payload)
    assert "name" not in sanitized
    assert "email" not in sanitized["profile"]
    assert sanitized["profile"]["skills"] == ["python"]


def test_pii_key_nested_in_a_list_is_removed() -> None:
    payload = {
        "experiences": [
            {"title": "Engenheiro", "email": "a@b.com", "skills": ["go"]},
            {"title": "Analista", "phone": "11999998888"},
        ]
    }
    sanitized = sanitize_for_llm(payload)
    for experience in sanitized["experiences"]:
        assert "email" not in experience
        assert "phone" not in experience
    assert sanitized["experiences"][0]["title"] == "Engenheiro"


def test_email_pattern_masked_in_free_text() -> None:
    text = "Contato: maria.souza@example.com para mais detalhes."
    assert "maria.souza@example.com" not in sanitize_for_llm(text)
    assert "[email]" in sanitize_for_llm(text)


def test_cpf_pattern_masked_in_free_text() -> None:
    text = "CPF: 123.456.789-01"
    result = sanitize_for_llm(text)
    assert "123.456.789-01" not in result
    assert "[documento]" in result


def test_cpf_without_punctuation_masked() -> None:
    text = "documento 12345678901"
    result = sanitize_for_llm(text)
    assert "12345678901" not in result
    assert "[documento]" in result


def test_phone_pattern_masked_in_free_text() -> None:
    text = "Ligue para +55 11 91234-5678 em horário comercial."
    result = sanitize_for_llm(text)
    assert "91234-5678" not in result
    assert "[telefone]" in result


def test_linkedin_url_masked() -> None:
    text = "Perfil: https://www.linkedin.com/in/mariasouza"
    result = sanitize_for_llm(text)
    assert "linkedin.com" not in result
    assert "[url-pessoal]" in result


def test_github_url_masked() -> None:
    text = "Código em https://github.com/mariasouza"
    result = sanitize_for_llm(text)
    assert "github.com" not in result
    assert "[url-pessoal]" in result


def test_groq_key_masked() -> None:
    text = "chave gsk_ABCDEFGHIJ1234567890KLMN vazou no log"
    result = sanitize_for_llm(text)
    assert "gsk_" not in result
    assert "[segredo]" in result


def test_openai_style_key_masked() -> None:
    text = "sk-ABCDEFGHIJ1234567890KLMNOPQR"
    result = sanitize_for_llm(text)
    assert "sk-ABCDEFGHIJ1234567890KLMNOPQR" not in result
    assert "[segredo]" in result


def test_tavily_key_masked() -> None:
    text = "tvly-ABCDEFGHIJ1234567890KLMN"
    result = sanitize_for_llm(text)
    assert "tvly-ABCDEFGHIJ1234567890KLMN" not in result
    assert "[segredo]" in result


def test_bearer_token_masked() -> None:
    text = "Authorization: Bearer abc123.def456.ghi789"
    result = sanitize_for_llm(text)
    assert "abc123.def456.ghi789" not in result
    assert "[segredo]" in result


def test_original_payload_is_not_modified() -> None:
    payload = {"name": "Maria", "profile": {"email": "a@b.com"}}
    original_copy = {"name": "Maria", "profile": {"email": "a@b.com"}}
    sanitize_for_llm(payload)
    assert payload == original_copy


def test_professional_evidence_is_preserved() -> None:
    payload = {
        "experiences": [
            {
                "title": "Engenheiro de Software Sênior",
                "skills": ["python", "postgres"],
                "evidence": "Liderou a migração do serviço de pagamentos para Postgres.",
            }
        ],
        "posting": "Vaga para engenheiro backend com experiência em Python e Postgres.",
    }
    sanitized = sanitize_for_llm(payload)
    assert sanitized["experiences"][0]["title"] == "Engenheiro de Software Sênior"
    assert sanitized["experiences"][0]["skills"] == ["python", "postgres"]
    assert "migração do serviço de pagamentos" in sanitized["experiences"][0]["evidence"]
    assert sanitized["posting"] == payload["posting"]


def test_pii_keys_frozenset_matches_documented_keys() -> None:
    assert PII_KEYS == frozenset(
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
