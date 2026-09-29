# Avaliação da análise — v2 × openai/gpt-oss-120b (v2-vs-v1-baseline)

Rodada em 2026-09-28T02:02:30.154666+00:00, 10 casos, conjunto `1afa75cd3102`. Provedor groq, cadeia openai/gpt-oss-120b.

Decisão pelo conjunto reservado; `não comparável` é critério que o baseline não media e exige o gabarito, não uma melhora.

| Critério | Reservado | Ajuste | Todos | Baseline (reservado) | Comparação |
| --- | ---: | ---: | ---: | ---: | --- |
| completed_rate | 0.500 | 0.500 | 0.500 | 1.000 | piora |
| fidelity | 0.000 | 0.500 | 0.400 | — | não comparável |
| grounded | — | 0.667 | 0.667 | — | sem dado |
| coverage | 0.000 | 0.000 | 0.000 | 0.000 | empate |
| inventions | 0.000 | 0.000 | 0.000 | 0.000 | empate |
| portuguese | 1.000 | 0.991 | 0.993 | 0.123 | melhora |
| prompt_tokens | 2162 | 2749 | 2602 | 890 | piora |
| output_tokens | 580 | 703 | 673 | 451 | piora |
| total_ms | 1690 | 1982 | 1909 | 1663 | piora |

Regra de troca atendida: não.

Rubrica humana: aderência ao veredito (0/1) e sustentação — se cada trecho citado sustenta a afirmação, com atenção a negação e requisito opcional (0/1).

| Caso | Split | Status | Fidelidade | Ancorado | Cobertura | Invenções | Opcionais | Português | Tokens (entrada/saída) | ms | Aderência | Sustentação |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | :---: |
| 01-fora_de_area-27-review_required | tuning | AI_FAILED (SCHEMA_MISMATCH) | 0.000 | — | — | — | — | — | 2651/829 | 2258 |  |  |
| 02-fora_de_area-28-review_required | tuning | AI_FAILED (SCHEMA_MISMATCH) | 0.000 | — | — | — | — | — | 2658/620 | 1787 |  |  |
| 03-fora_de_area-29-review_required | tuning | AI_COMPLETED | 1.000 | 1.000 | 0.000 | 0 | 0 | 0.985 | 2761/645 | 1882 |  |  |
| 04-fora_de_area-30-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.992 | 2654/741 | 2042 |  |  |
| 06-fora_de_area-31-review_required | tuning | AI_FAILED (SERVER_ERROR) | — | — | — | — | — | — | —/— | — |  |  |
| 08-fora_de_area-32-review_required | reserved | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 1.000 | 2075/481 | 1483 |  |  |
| 09-fullstack-07-review_required | tuning | AI_COMPLETED | — | 0.000 | 0.000 | 0 | 0 | 0.988 | 2837/490 | 1518 |  |  |
| 10-fullstack-18-review_required | tuning | AI_COMPLETED | 1.000 | 1.000 | 0.000 | 0 | 0 | 1.000 | 2931/895 | 2404 |  |  |
| 11-fullstack-37-review_required | reserved | AI_FAILED (SCHEMA_MISMATCH) | 0.000 | — | — | — | — | — | 2248/680 | 1897 |  |  |
| 12-ai-11-review_required | tuning | QUOTA_BLOCKED (QUOTA_EXHAUSTED) | — | — | — | — | — | — | —/— | — |  |  |
