# Rebuild da stack real com dados preservados (2026-09-29)

Encerramento antecipado da janela de 7 dias (F20-35/F20-38/F20-49), **autorizado pelo
usuário em 2026-09-29**: backup, rebuild mantendo dados, reprocessamento do acervo e
importação das fontes da `f20manual`. Stack real = projeto compose `opportunity-radar`
(portas 3000/8000), comandos rodados a partir do checkout principal, branch
`feature/f20-groq-e-consolidacao` (HEAD `815786f`, não alterada). Nenhum `down -v`,
nenhum volume removido, nenhum DROP/TRUNCATE. A `f20manual` só foi lida (SELECT).

## 1. Medição parcial da janela — T3.5 (janela encerrada antes, autorizado pelo usuário em 2026-09-29)

Método dos cards F20-35/F20-38/F20-49 (`produtividade-fase-20.md` §4): `/search-metrics`,
`/analysis-metrics`, créditos Tavily em `acquisition.source_run`, erros em
`platform.ai_call_record`. Só SELECT. Medido em 2026-09-29T17:48Z.

Janela válida = a partir do segundo reinício, **T0b = 2026-09-28T12:01:55Z**
(`f20-janela-7d-t0-2026-09-28b.json`), ou seja ~29,8 h (≈1,24 dia), não 3,5 dias.
O "T3.5" do pedido cobre T0 nominal 2026-09-26/27; os T0 de 09-27 e 09-28T00:45Z foram
invalidados nos próprios cards (stack parada / fontes sem `schedule`). Por isso as duas
leituras abaixo: acumulado do `/search-metrics?window=7d` (mistura pré-T0b) e delta
desde T0b.

Lacunas na janela (sem `source_run`): 2026-09-29 00:01Z–12:10Z (buraco de ~12 h) e a
hora de 2026-09-28 16Z, conforme a instrução do coordenador (uma das lacunas foi só
conferida pelas horas com run). Horas com execuções desde T0b (UTC): 09-28 16, 18, 21;
09-29 00, 12, 15. A cadência esperada (`0 */3 * * *`) não foi cumprida (6 blocos em ~30 h
em vez de ~10). Causa não investigada aqui.

| Métrica | Meta (F20-49) | T0b (09-28T12:01Z) | T3.5 acumulado 7d | Delta desde T0b |
| --- | --- | --- | --- | --- |
| Execuções (`coverage.runs`) | — | 48 | 141 | +93, todas `SUCCEEDED`, `SCHEDULED` |
| Requisições HTTP (`useful_yield.requests`) | — | 68 | 169 | +101 (`sum(http_requests)`) |
| Itens vistos / persistidos / duplicados | — | 1519 / 1332 / 187 | 3803 / 1383 / 2420 | +2284 vistos, +51 persistidos |
| Vagas úteis novas (`new_unique_opportunities`) | >= 1/dia | 653 | 686 | **+33 em ~1,24 dia** (25 em 09-28, 8 em 09-29) = ~26,6/dia, meta batida no recorte, amostra curta |
| `yield_per_100_requests` | — | 86,76 | 34,91 | 33/101 = 32,7 no delta |
| Empresas cobertas / com ATS | — | 15 / 55 | 15 / 55 | sem mudança |
| Funil (`enabled` / `collected_recently`) | sem regressão | 15 / 8, `enabled_but_unhealthy=7` | 15 / 3, `enabled_but_unhealthy=12` | **regressão de `collected_recently` (8 -> 3)**, efeito direto do buraco 00Z–12Z |
| `homologated` / `endpoint_discovered` | não regride | 15 / 222 | 15 / 222 | sem regressão |
| `seniority_unknown_rate` | — | 50,38 % | 49,42 % | -0,96 p.p. |
| Créditos Tavily / dia | <= 33/dia | — | — | 1 crédito em 09-28, 0 em 09-29 |
| Rate limit (`rate_limit_events`) | — | — | — | 0 em 93 runs; 0 retries |
| Análises IA concluídas / dia | >= 1/dia | — | — | 09-29: 108 `gpt-oss-120b` + 45 `qwen3.8-27b` concluídas; 09-28 (pós-T0b): 885 `AI_FAILED` por `QUOTA_EXHAUSTED`, 366 `AI_FAILED` em 09-29 |
| Taxa de fallback (Groq, 09-29, `ai_call_record`) | < 5 % | — | — | 45 de 193 chamadas (23,3 %); **meta não batida**, causado pela quota diária do modelo primário |
| Taxa de 429 (`error_kind=quota`) | < 2 % | — | — | 43/193 = 22,3 %; **meta não batida** (todas no `qwen`, fallback; primário ficou em 105 reqs / 169.522 tokens de 170.000) |
| `json_valid_rate` | >= 99 % | — | — | 100 % (bloco `ai` do `/analysis-metrics`) |
| Erros por tipo | nenhum dominante sem causa | — | — | `QUOTA_EXHAUSTED` domina (85 % das análises 7d do primário), causa identificada: teto diário de tokens; `SERVER_ERROR` 0,05 % |

Limitações: `ai_call_record` só tem linhas de 09-29 no recorte (09-28 pós-T0b sem chamadas
registradas, apenas análises `AI_FAILED` em `match_analysis`); F20-38 pede também bytes e
frescor, e `source_run` não guarda bytes; o orçamento por host (`host_budget_state`)
mostra `remotive.com` 1, `boards.greenhouse.io` 1, `api.lever.co` 4, `api.ashbyhq.com` 12
requisições na janela horária corrente, todas abaixo do teto. **Veredito: inconclusivo**
para as metas de custo de IA e cobertura (amostra ~1,24 dia, com buraco de 12 h); nada aqui
é extrapolado para 7 dias. JSON brutos guardados no scratchpad
(`t35-search-metrics.json`, `t35-analysis-metrics.json`).

## 2. Exportação da `f20manual`

Fonte: `f20manual-postgres-1` (SELECT em `source_definition` + `company_source` + `company`).
Arquivo: `C:/Users/mathf/AppData/Local/Temp/claude/C--Users-mathf-Documents-GitHub-Opportunity-Radar/289fa8ba-b770-4c53-b6c1-157b43ddae34/scratchpad/f20manual-sources-export.json`.

- `f20manual`: 150 `source_definition`; real: 24.
- Critério: habilitada na `f20manual` e ausente na real (chave `source_type` + identificador
  do board: `board_identifier`, `board_token`, `site_identifier`, `tenant_identifier`,
  `account_identifier`, `company_identifier`, comparado em minúsculas).
- Excluídas: fontes desabilitadas (`talentpluto`, `Pearl Talent`, `LiveKit`, `DeepL`,
  `Wikimedia`, probes e `Manual`), as 15 que já existiam na real, e **`Braintrust jobs`**
  (Ashby `braintrust`, habilitada na `f20manual`, mas está na lista de fontes proibidas).
- **Exportadas: 120 fontes** = greenhouse 43, ashby 34, workday 15, lever 10, workable 9,
  teamtailor 6, factorial 2, hacker_news 1 (schedule forçado `0 18 3 * *`).
- 59 com `company_source` + `company` (todas `radar_status=active`); 61 sem linha de
  empresa na `f20manual` (21 "Proposed ..." e fontes criadas só com `company_name` na
  configuração), importadas com `company_source_id` nulo, como na origem.

## 3. Backup da base real (verificado)

```
docker exec opportunity-radar-api-1 python /app/scripts/backup.py \
  --output-dir /tmp/bk --label pre-rebuild-2026-09-29
```

`wrote /tmp/bk/pre-rebuild-2026-09-29.dump (9469563 bytes, sha256 e1d9539a14c4...)`.
O container `api` não monta o volume de backups, então o dump foi copiado com
`docker cp` para dois destinos e o temporário removido:

- Volume `opportunity-radar_local_backups`: `/app/data/backups/pre-rebuild-2026-09-29.dump`
  (+ `.manifest.json`), visível no container `worker`.
- Cópia local (scratchpad): `C:/Users/mathf/AppData/Local/Temp/claude/C--Users-mathf-Documents-GitHub-Opportunity-Radar/289fa8ba-b770-4c53-b6c1-157b43ddae34/scratchpad/backup/pre-rebuild-2026-09-29.dump`.

Verificação: 9.469.563 bytes; sha256 `e1d9539a14c4c59ca2beb31546fce82fbe6d1bb999aae0c4e90a9884acd46a6b`
idêntico nas três cópias; `pg_restore --list` = 287 linhas. Manifesto: `alembic_revision
20260926_0044`, companies 223, company_sources 279, source_definitions 24, source_runs
141, raw_items 1383, opportunities 686, source_occurrences 687, observations 3130,
match_assessments 3246, match_analyses 2451, ai_call_record 575; extensões
`plpgsql, unaccent, vector`. **Não** foi feito restore-check em banco descartável
(`scripts/restore_check.py`); só a listagem do TOC.

## 4. Rebuild

`docker compose -p opportunity-radar up -d --build` (a partir do checkout principal).
`migrate` aplicou `20260926_0044 -> 20260926_0052 -> 20260928_0053 -> 20260929_0054`.

- `alembic current` = `alembic heads` = `20260929_0054 (head)` (cabeça única).
- 4 serviços `healthy`; oportunidades 686 antes e depois (dados preservados).
- Política de reinício (`docker inspect`): postgres, api, worker e frontend =
  `unless-stopped`.

## 5. Reprocessamento (normalizer v6 / seniority-v3)

Caminho usado (o do F20-02, `reprocessamento-skills-v3-2026-09-27.md`): `POST
/opportunities/normalizations/pending?limit=500` até fila vazia. Não há dry-run nesse
endpoint. Código: `NORMALIZER_VERSION = "v6"`, `SENIORITY_MAPPING_VERSION = "seniority-v3"`.

Antes (logo após o rebuild; o worker já tinha normalizado 300 itens em v6):
`normalization_result` v3 670, v4 670, v5 1383 (FAILED 38, REVIEW_REQUIRED 4, SUCCEEDED
1341), v6 300 (FAILED 3, SUCCEEDED 297).

Lotes: `500 (393 ok, 88 review, 19 falhas)`, `500 (397, 87, 16)`, `70 (60, 10, 0)`, `0`.

Depois: v6 = 1383 = total de `raw_item` (FAILED 38, REVIEW_REQUIRED 185, SUCCEEDED 1160);
oportunidades 686 (nenhuma perdida/duplicada). As 38 falhas repetem o total de v5.

## 6. Backfills

Dry-run e execução real, no container `api` (`scripts/backfill_*.py`):

| Script | Dry-run | Real |
| --- | --- | --- |
| `backfill_opportunity_company.py` | `null_before 0, linkable 0, updated 0` | idem |
| `backfill_startup_evidence.py` (antes da importação) | `[]` | `[]` |
| `backfill_startup_evidence.py` (depois da importação) | 21 propostas, todas `skipped: company not found` | idem; `company_startup_evidence` = 0 linhas |

Sem efeito: todas as vagas já têm `canonical_company_id`; as 21 fontes "Proposed" não têm
empresa na `f20manual` (fonte da verdade), então não há a quem ligar evidência.

## 7. Importação das fontes na base real

Script único (`import_sources.py`, no scratchpad, copiado para `/tmp` do container `api`
e removido como root no fim; `/tmp` do `api` vazio). Reaproveita
`enable_sources._probe_all` (concorrência 8, serializa por host a 1 req/s),
`enable_sources._homologation_audit` e `AcquisitionService.record_script_probe`, no
mesmo padrão de `ativacao-backlog-f20-60-2026-09-29.md`. Passos:

1. `dry`: 42 empresas a criar / 17 reaproveitadas (por `normalized_name`), 59
   `company_source` a criar, 120 `source_definition` a criar, 0 conflitos `(source_type,name)`.
2. `import`: mesma contagem gravada; fontes criadas **desabilitadas**
   (`evidence_status=unverified`, `terms_reviewed=false`, `homologation_audit` removido da
   configuração), `schedule`/`priority`/`rate_limit_policy` copiados da `f20manual`.
   Total de `source_definition`: 24 -> 144.
3. `probe`: 120 probes (`max_items=1`, `requested_by=script`); **120 passaram, 0 falharam**.
   Passadas foram habilitadas (`enabled`, `confirmed`, `terms_reviewed`,
   `collector_local_tested`, `homologation_audit` novo com `probe_id`) e a empresa ficou
   `active`. Total habilitadas: 17 -> 137.

Passaram: greenhouse 43, ashby 34, workday 15, lever 10, workable 9, teamtailor 6,
factorial 2, hacker_news 1 (lista nominal no arquivo de exportação; nenhuma falha).

Ponto de atenção: das 120, só **25 têm `schedule`** (13 com `0 */3 * * *`, 11 com
`0 0 * * 0`, hacker_news `0 18 3 * *`); **95 estão habilitadas sem `schedule`**
(reproduzem a `f20manual`). O worker pula fonte sem `schedule` (`NOT_SCHEDULED`, mesma
lacuna do segundo reinício da janela), então essas 95 só coletam sob demanda
(`collect.py`). Não foi alterado: o pedido era copiar a configuração da `f20manual`.
Decisão pendente do usuário: definir `schedule` para elas.

Nenhuma coleta rodou nas fontes novas dentro desta sessão (0 `source_run` nos últimos
20 min após a importação).

## 8. Remedição de senioridade

Mesma query dos documentos anteriores (`opportunities.opportunity.seniority`, total do
acervo):

| Momento | Total | `UNKNOWN` | % UNKNOWN | JUNIOR + INTERN | % |
| --- | --- | --- | --- | --- | --- |
| Baseline F17-06 (648 oportunidades) | 648 | 328 | 50,62 % | — | — |
| Antes do reprocessamento (pós-rebuild) | 686 | 339 | 49,42 % | 5 | 0,73 % |
| Depois (v6 / seniority-v3) | 686 | 339 | **49,42 %** | 5 (JUNIOR 3, INTERN 2) | 0,73 % |

**Meta (metade de 50,62 %, ~25 %) não atingida e não mudou com o reprocessamento.**
Motivo verificado: `seniority-v3` só preenche títulos `UNKNOWN` com palavra-chave
(trainee, estagiário, entry level, new grad, graduate, early career, apprentice/aprendiz);
nenhuma das 339 vagas `UNKNOWN` tem título com esses termos (query em `canonical_title`
retorna só os 5 já classificados). O grosso do `UNKNOWN` é título sem sinal de
senioridade, fora do alcance de regra por título.

## Uncertezas e pendências

- Sem `restore_check` do dump (só `pg_restore --list`).
- Buraco de execuções 09-29 00Z–12Z e cadência abaixo do esperado: causa não investigada.
- 95 fontes importadas sem `schedule`; 0 coletas nas fontes novas até o fim desta sessão.
- 21 propostas sem empresa: `backfill_startup_evidence` não tem efeito.
- Pertencimento das fontes importadas herdado da `f20manual` (probe só prova que o endpoint
  responde e o coletor lê 1 item, não que o board é da empresa).
- `README.md` e `validacao-pendente.md` não foram alterados (outro worker).

## Adendo — agenda das fontes importadas (2026-09-29 ~18:25Z)

Decisão do usuário (maximizar vagas): as 95 fontes importadas sem `schedule` receberam agenda — Workday `0 6 * * *` (11), demais ATS `0 */3 * * *`. Resultado nas 137 fontes ativas: `0 */3 * * *` 113, `0 6 * * *` 11, `0 0 * * 0` 11, `0 18 3 * *` 1 (HN), 1 manual sem agenda. Worker reiniciado.
