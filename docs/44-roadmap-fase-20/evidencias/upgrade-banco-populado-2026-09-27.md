# Upgrade de banco populado e retomada de backfill — F20-48 (2026-09-27)

Card F20-48. Duas provas independentes: um teste automatizado com um dump sintético
pequeno na revisão `20260925_0029` (roda em CI), e uma execução manual contra o dump real
verificado `data/backups/f20-02-pre-skills-v3-2026-09-27.dump` (revisão `20260926_0043`),
restaurado num projeto compose isolado `-p f20up`, nunca no projeto `opportunity-radar`.

## 1. Prova automatizada (CI) — `tests/backend/test_upgrade_populated_integration.py`

`tests/backend/fixtures/pre_f20_dump.sql` é um dump sintético (`pg_dump --format=plain`),
sem dado real de empresa, candidato ou vaga: gerado subindo um Postgres descartável em
`20260925_0029` (`alembic upgrade 20260925_0029`), coletando/normalizando 20 vagas e
criando 20 avaliações e análises pelo fluxo HTTP real (`POST /sources`, `/sources/{id}/
runs`, `/opportunities/normalizations/pending`, `/profile/versions`,
`/matches/evaluate`), gravando 20 `match_analysis` com `model_id="qwen3:8b-q4_K_M"`
(Ollama, pré-Groq) e 3 `application_process` via SQL, e então `alembic downgrade
20260925_0029` para remover as colunas/tabelas que só existem a partir de `0030`. O
resultado é dado real (sintético) numa forma de schema autêntica: exatamente o que um
banco que parou de receber migrações antes da Fase 20 teria.

Reaproveita em vez de reimplementar:

- F20-41 (`scripts.restore_check.create_database`/`drop_database`,
  `platform.backup.with_database`/`postgres_dsn`) para o banco descartável.
- F20-12/F20-19: as tabelas `platform.ai_quota_usage`/`platform.ai_call_record` fazem
  parte do que `alembic upgrade head` precisa criar; o teste confere que aparecem vazias
  depois do upgrade (a Fase 20 não fabrica histórico).
- F17-06 (`OpportunityService.normalize_pending`) para a retomada de backfill — o teste
  não reimplementa retomada, só aciona o mecanismo existente sobre dado que acabou de
  passar por um upgrade real.

```
docker compose -p f20-48t -f compose.yaml -f compose.dev.yaml run --rm \
  -e RUN_DATABASE_INTEGRATION=1 api pytest -q tests/backend/test_upgrade_populated_integration.py
...
3 passed, 1 warning in 14.31s
```

- `test_pre_phase_20_database_upgrades_to_head_without_losing_history`: restaura o dump,
  confere `alembic_version = 20260925_0029`, roda `alembic upgrade head` (subprocesso,
  como a CI roda), confere que as 10 contagens da tabela vertical são idênticas antes e
  depois, e que `platform.ai_quota_usage`/`platform.ai_call_record` existem e começam
  vazias.
- `test_old_ollama_analyses_remain_legible_after_the_upgrade`: as 20 `match_analysis`
  continuam com `model_id="qwen3:8b-q4_K_M"`, `status="AI_COMPLETED"` e resumo legível.
- `test_interrupted_backfill_resumes_without_duplicating`: apaga o `normalization_result`
  de 5 `raw_item` (simulando um backfill pendente após o upgrade), chama
  `normalize_pending(limit=2)` repetidamente — cada chamada independente da anterior,
  como um worker que reinicia entre lotes — até esvaziar a fila (5 chamadas para 5 itens
  em lotes de 2), confere que nenhuma oportunidade/ocorrência nova apareceu (a
  re-normalização encontra a ocorrência existente pela identidade da fonte e a atualiza,
  não duplica) e que uma chamada final processa 0.

Suíte completa e checagens estáticas, mesmo comando:

```
docker compose -p f20-48t -f compose.yaml -f compose.dev.yaml run --rm \
  -e RUN_DATABASE_INTEGRATION=1 api pytest -q
911 passed, 10 skipped, 12 warnings in 92.89s

docker compose -p f20-48t -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
All checks passed!

docker compose -p f20-48t -f compose.yaml -f compose.dev.yaml run --rm api mypy
Success: no issues found in 118 source files
```

Nota de implementação: a primeira versão de `_alembic_upgrade_head` chamava
`alembic.command.upgrade` no próprio processo do pytest. Isso reconfigura o logging
global (`migrations/env.py` chama `fileConfig(...)`) e quebrou `caplog` num teste
não relacionado mais adiante na mesma sessão
(`test_worker.py::test_the_startup_log_reports_what_the_scheduler_actually_holds`,
`StopIteration`). Corrigido chamando `alembic upgrade head` como subprocesso — o mesmo
comando que a CI e um operador rodam, não uma reimplementação dele — o que também isola
o processo de teste da reconfiguração de logging. Suíte completa voltou a passar 100%
depois da correção.

Projeto `f20-48t` foi derrubado (`docker compose ... down -v`) ao final; nenhum dado
ficou retido.

## 2. Prova real contra o acervo verdadeiro — projeto isolado `-p f20up`

`data/backups/f20-02-pre-skills-v3-2026-09-27.dump` é o backup real (F20-41) tirado do
projeto `opportunity-radar` antes do reprocessamento oficial `skills-v3`
(`docs/44-roadmap-fase-20/evidencias/reprocessamento-skills-v3-2026-09-27.md`), na
revisão `20260926_0043` — uma migração antes do `head` atual (`20260926_0044`,
F20-36 discovery multi-página). Nunca versionado; usado só localmente, restaurado num
projeto compose isolado, nunca no projeto real.

```
docker compose -p f20up -f compose.yaml -f compose.dev.yaml up -d postgres
docker compose -p f20up -f compose.yaml -f compose.dev.yaml cp \
  data/backups/f20-02-pre-skills-v3-2026-09-27.dump postgres:/tmp/f20-02.dump
docker compose -p f20up -f compose.yaml -f compose.dev.yaml exec -T postgres \
  pg_restore -U opportunity_radar -d opportunity_radar --no-owner --no-privileges \
  --exit-on-error /tmp/f20-02.dump
```

### Contagens antes do upgrade — batem com o manifesto (`f20-02-pre-skills-v3-2026-09-27.manifest.json`)

| Tabela | Manifesto | Restaurado |
| --- | --- | --- |
| `alembic_version` | `20260926_0043` | `20260926_0043` |
| `company_radar.company` | 223 | 223 |
| `opportunities.opportunity` | 648 | 648 |
| `acquisition.raw_item` | 670 | 670 |
| `matching.match_analysis` | 714 | 714 |
| `platform.ai_quota_usage` | 90 | 90 |
| `platform.ai_call_record` | 190 | 190 |

### Upgrade para `head`

```
docker compose -p f20up -f compose.yaml -f compose.dev.yaml run --rm migrate alembic upgrade head
...
Running upgrade 20260926_0043 -> 20260926_0044, Add multi-page discovery columns to `company_radar.discovery_attempt`.
```

### Contagens depois do upgrade — critério 1 (idênticas)

| Tabela | Antes | Depois |
| --- | --- | --- |
| `company_radar.company` | 223 | 223 |
| `opportunities.opportunity` | 648 | 648 |
| `acquisition.raw_item` | 670 | 670 |
| `matching.match_analysis` | 714 | 714 |
| `opportunities.source_occurrence` | 648 | 648 |
| `matching.match_assessment` | 1296 | 1296 |
| `crm.application_process` | 0 | 0 |

### Critério 2 — análises antigas legíveis

```
model_id             | count
openai/gpt-oss-120b  |  526
disabled             |  144
qwen/qwen3.8-27b     |   44
```

Uma amostra `AI_COMPLETED` depois do upgrade:

```
82f23227-... | openai/gpt-oss-120b | AI_COMPLETED | "The role is remote, which aligns with the candidate's accept..."
```

`model_id` e o resumo continuam exatamente como antes do upgrade — nenhuma reescrita de
histórico.

### Critério 3 — backfill interrompido e retomado sem duplicar

Antes do upgrade, os 670 `raw_item` estavam normalizados em `v3`/`v4`; o código desta
árvore usa `NORMALIZER_VERSION = "v5"` — subir o código para `head` deixa os 670 itens
pendentes de reprocessamento, o cenário real que F17-06 descreve
("subir a versão do normalizador reprocessa todo `RawItem`"). Usei isso como a prova real
de backfill retomável, em vez de forçar um estado artificial:

```
POST /opportunities/normalizations/pending {"limit": 100}   -> processed=100 (lote 1, "interrompido" aqui de propósito)
$ SELECT count(*) FROM opportunities.normalization_result WHERE normalizer_version='v5';  -> 100
```

Retomada (7 chamadas subsequentes, cada uma independente da anterior — o mesmo padrão de
"um worker reinicia entre lotes"):

```
batch 2 processed=100 total=200
batch 3 processed=100 total=300
batch 4 processed=100 total=400
batch 5 processed=100 total=500
batch 6 processed=100 total=600
batch 7 processed=70  total=670
batch 8 processed=0   total=670   <- idempotente: nada sobrou para reprocessar
```

Depois de esvaziar a fila:

| Verificação | Resultado |
| --- | --- |
| `normalization_result` em `v5` | 670 (nenhum a menos, nenhum duplicado) |
| `opportunities.opportunity` | 648 (inalterado — nenhuma oportunidade duplicada) |
| `opportunities.source_occurrence` | 648 (inalterado) |
| `company_radar.company` | 223 (inalterado) |
| `v5` por status | `SUCCEEDED`: 648, `FAILED`: 22 |

As 22 falhas em `v5` reproduzem exatamente as 22 falhas `INVALID_COLLECTED_ITEM_V1` que
`docs/38-roadmap-ia-e-busca/fase-17/f17-06-normalizacao-mais-precisa.md` já registrava
para o mesmo acervo — nenhuma falha nova, nenhuma oportunidade perdida ou duplicada.

Projeto `f20up` foi completamente derrubado ao final
(`docker compose -p f20up ... down -v`); `data/backups/f20-02-pre-skills-v3-2026-09-27.dump`
nunca foi copiado para fora de `data/backups/` nem versionado por este card. O projeto
`opportunity-radar` não foi tocado em nenhum momento desta sessão.

## Critério → evidência

| Critério | Evidência |
| --- | --- |
| Contagens iguais antes e depois do upgrade | Seção 1 (`test_pre_phase_20_database_upgrades_to_head_without_losing_history`, fixture sintética) e seção 2 (dump real, tabela "Contagens depois do upgrade") |
| Análises antigas legíveis | Seção 1 (`test_old_ollama_analyses_remain_legible_after_the_upgrade`, `model_id="qwen3:8b-q4_K_M"`) e seção 2 (amostra `openai/gpt-oss-120b` real) |
| Backfill retomado sem duplicar | Seção 1 (`test_interrupted_backfill_resumes_without_duplicating`) e seção 2 (670 itens reais em 7 lotes retomados, contagens de oportunidade/ocorrência/empresa inalteradas, 8º lote idempotente) |

## Pronto

Testes: `docker compose -p f20-48t -f compose.yaml -f compose.dev.yaml run --rm -e
RUN_DATABASE_INTEGRATION=1 api pytest -q` (911 passed, 10 skipped). `ruff check .` e
`mypy` limpos. Prova real documentada acima. Os três critérios de aceite têm evidência
automatizada (CI) e evidência real (máquina de referência).
