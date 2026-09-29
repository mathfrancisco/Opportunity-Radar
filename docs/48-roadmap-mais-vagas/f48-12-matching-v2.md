# F48-12 — `matching-v2` (V04, V07)

## Resultado

- `RULES_VERSION = "matching-v2"` (`matching/service.py`); `default_rule_set()` devolve a v2. O
  histórico `matching-v1` fica: uma avaliação nova é uma linha nova com `rules_version`
  próprio, nada é editado no lugar. Nenhum reprocessamento do banco real foi feito neste card.
- Snapshot da oportunidade passa `allowed_countries` (`_allowed_countries`: maiúsculas, sem
  duplicata) e `role_family`; o do perfil passa `role_families`, derivadas de
  `experiences` (título + resumo) e `projects` (nome + descrição) pelo classificador de vagas
  (`classify_role_family`), sem `UNKNOWN`. Fuso e autorização seguem sem coleta e deixaram de
  ser "desconhecidos que exigem revisão".
- `GEOGRAPHY_CONTRACT_FIT` considera só modo de trabalho, país e contrato
  (`_geography_dimensions`). Qualquer `FALSE` continua `INELIGIBLE`. Dimensão desconhecida vale
  0,5 e a confiança do fator é a fração de dimensões conhecidas (0, 1/3, 2/3, 1). Política
  `NEUTRAL`: o fator nunca força `REVIEW_REQUIRED`. Revisão só por conflito
  (`compensation_conflict`).
- `DOMAIN_EXPERIENCE` = interseção de `opportunity.role_family` com `profile.role_families`:
  1,0 com interseção, 0,25 (`DOMAIN_NO_OVERLAP_SCORE`) sem interseção, `UNKNOWN` (0,5) se a vaga
  não foi classificada ou o perfil não evidencia área.
- `TIMEZONE` e `CONTRACT_COMPENSATION`: `EXCLUDE_AND_RENORMALIZE` (saem do denominador sem dado).
- Pesos v2 (soma 1,00), com a justificativa em `matching/domain.py`:

  | Fator | v1 | v2 | Motivo |
  | --- | --- | --- | --- |
  | GEOGRAPHY_CONTRACT_FIT | 0,20 | 0,15 | portão grosseiro; falha dura já é INELIGIBLE |
  | TECHNOLOGY_FIT | 0,25 | 0,25 | sem mudança |
  | COMPANY_PRIORITY | 0,15 | 0,10 | proxy fraco do interesse (V05) |
  | DOMAIN_EXPERIENCE | 0,15 | 0,20 | ganhou avaliador |
  | SENIORITY_SCOPE | 0,10 | 0,15 | ganhou dado (F48-13) |
  | CONTRACT_COMPENSATION | 0,05 | 0,05 | renormalizado sem dado |
  | TIMEZONE | 0,05 | 0,05 | renormalizado sem dado |
  | RECENCY | 0,05 | 0,05 | sem mudança |

- Cortes: HIGH_PRIORITY 80 e RECOMMENDED 65 mantidos; WATCHLIST 45 -> **50**. Raciocínio: uma
  vaga com tudo desconhecido pontua cerca de 55 (todo fator neutro é 0,5); WATCHLIST precisa de
  evidência ao menos neutra, então uma vaga puxada para a casa dos 40 por incompatibilidade
  conhecida (ex.: senioridade acima da preferência) vira LOW_MATCH; RECOMMENDED exige um sinal
  forte conhecido sobre a base neutra (sobreposição total de tecnologia soma cerca de 12
  pontos); HIGH_PRIORITY exige vários (tecnologia, área e senioridade).

### Distribuição de veredito nos 50 casos rotulados (`prompts/opportunity_analysis/eval/cases/`)

Antes = veredito gravado nos casos (`matching-v1`); depois = casos reavaliados com a v2 (snapshots
reconstruídos do payload, `role_family` classificada do título/descrição do caso, recência
medida em 2026-03-01 para ser reprodutível).

| Veredito | Antes (v1) | Depois (v2) |
| --- | --- | --- |
| REVIEW_REQUIRED | 40 | 0 |
| INELIGIBLE | 10 | 10 |
| WATCHLIST | 0 | 34 |
| LOW_MATCH | 0 | 6 |
| RECOMMENDED / HIGH_PRIORITY | 0 | 0 |

Das 40 não inelegíveis, 34 (85 %) recebem WATCHLIST (guarda > 0 e meta de 30 % cumpridos no
conjunto). Nenhum chega a RECOMMENDED: nos 50 casos `required_skills` está quase sempre vazio
(`TECHNOLOGY_FIT` neutro), o perfil dos casos tem uma skill e nenhuma experiência (domínio
neutro) e 25 dos 50 casos são SENIOR ou acima, então a pontuação fica entre 38 e 61. O teste
sintético em `test_domain.py` mostra que evidência forte conhecida alcança HIGH_PRIORITY.

## Contexto

`matching-v1` deixava 4.442 das 5.187 avaliações reais em `REVIEW_REQUIRED` e 745 em
`INELIGIBLE`; os cortes 80/65/45 nunca eram exercidos (spec 48, §4.4 e §4.7). Causa:
`GEOGRAPHY_CONTRACT_FIT` virava `UNKNOWN` com `REQUIRE_REVIEW` se qualquer entre modo, país,
autorização, fuso ou contrato fosse desconhecido, e o snapshot nunca preenchia
`allowed_countries`; quatro fatores (35 % do peso) valiam 0,5 em 100 % das linhas.

## Escopo

`matching/domain.py` (regras, pesos, cortes, avaliadores), `matching/service.py` (snapshots,
`RULES_VERSION`), testes. Fora: `dashboard/*`, `opportunities/*`, `acquisition/*`, `apps/web`,
migração (nenhuma), reprocessamento do banco real.

## Critérios de aceite

- [x] Snapshot passa `allowed_countries` (`test_allowed_countries_reach_the_snapshot_...`).
- [x] `GEOGRAPHY_CONTRACT_FIT` considera modo, país e contrato; desconhecido é neutro e reduz
  confiança; revisão só em conflito
  (`test_geography_knowledge_matrix_never_forces_review`, 8 combinações;
  `test_v2_compensation_conflict_still_requires_review`).
- [x] `DOMAIN_EXPERIENCE` por família; `TIMEZONE`/`CONTRACT_COMPENSATION` renormalizados sem dado
  (`test_domain_experience_is_the_role_family_intersection`,
  `test_timezone_and_compensation_without_data_leave_the_denominator`).
- [x] Regressão dos 50 casos: `tests/backend/matching/test_matching_v2_regression.py`
  (distribuição fixada, INELIGIBLE preservado, nenhum REVIEW_REQUIRED sem conflito, guarda > 0
  e >= 30 % das não inelegíveis em veredito positivo).
- [ ] Meta de 30 % em amostra **real** reavaliada: não medida (sem reprocessar o banco); depende
  de o perfil ter áreas/skills (F48-13) e de a calibração ser confirmada com o usuário.

## Verificação

```
docker compose -p f48w9 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q \
  tests/backend/matching/test_domain.py tests/backend/matching/test_matching_v2_regression.py
```

57 passed. Suíte completa (`-e RUN_DATABASE_INTEGRATION=1`, projeto `f48w9` limpo com `down -v`):
1295 passed, 11 skipped. `ruff check src tests`: All checks passed.

Testes existentes ajustados à troca de versão: `test_reevaluation.py` (o bump de teste agora vai
de v2 para v3) e `dashboard/test_queries.py` (a fixture usa `RULES_VERSION`).
