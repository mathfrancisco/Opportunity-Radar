# Reprocessamento oficial do acervo real — `skills-v3` / `NORMALIZER_VERSION v5` (2026-09-27)

Card F20-02. Pendência deixada pela sessão de rotulagem humana de 2026-09-27 (registrada
no próprio card): o alias solto `ci` foi removido de `cicd` em
`src/opportunity_radar/opportunities/domain.py`, `SKILL_TAXONOMY_VERSION` subiu de
`"skills-v2"` para `"skills-v3"` e `NORMALIZER_VERSION` de `"v4"` para `"v5"` (commit
`c5b751f`), mas o reprocessamento oficial contra o acervo real (projeto compose
`opportunity-radar`) não tinha rodado ainda — a base ficou com `opportunity_skill` rows em
`skills-v2`. Esta evidência fecha essa pendência.

## 1. Estado da stack real antes de tocar em qualquer coisa

```
$ docker compose -p opportunity-radar ps -a
NAME                           STATUS
opportunity-radar-api-1        Exited (255) 15 hours ago
opportunity-radar-frontend-1   Exited (255) 15 hours ago
opportunity-radar-migrate-1    Exited (0) 26 minutes ago
opportunity-radar-postgres-1   Exited (0) 26 minutes ago
opportunity-radar-worker-1     Exited (255)
```

Todos os containers estavam parados (nenhum rodando). Estado de referência para a
restauração no fim.

## 2. Backup verificado (F20-41) — feito antes de qualquer mudança

```
docker compose -p opportunity-radar up -d postgres
docker compose -p opportunity-radar run --rm -v "<repo>\data\backups:/app/data/backups" \
  api python scripts/backup.py --label "f20-02-pre-skills-v3-2026-09-27"
```

Saída:

```
wrote data/backups/f20-02-pre-skills-v3-2026-09-27.dump (4692123 bytes, sha256 e320ea78242f...)
wrote data/backups/f20-02-pre-skills-v3-2026-09-27.manifest.json
```

Manifesto (`data/backups/f20-02-pre-skills-v3-2026-09-27.manifest.json`):
`alembic_revision=20260926_0043`, `companies=223`, `opportunities=648`, `raw_items=670`,
`match_assessments=1296`, `match_analyses=714`, extensões `plpgsql, unaccent, vector`.

Verificação com restore real (F20-41, `scripts/restore_check.py`), banco descartável,
banco de trabalho intocado:

```
docker compose -p opportunity-radar run --rm -v "<repo>\data\backups:/app/data/backups" \
  api python scripts/restore_check.py --dump data/backups/f20-02-pre-skills-v3-2026-09-27.dump
```

```
restoring data/backups/f20-02-pre-skills-v3-2026-09-27.dump into restore_check_20260927133933
  companies: 223 | opportunities: 648 | raw_items: 670 | match_assessments: 1296 | ...
restore check passed
```

Backup confirmado antes de seguir. Caminho: `data/backups/f20-02-pre-skills-v3-2026-09-27.dump`
(+ `.manifest.json`).

## 3. Métricas antes (somente leitura, acervo real)

```sql
select count(*) from opportunities.opportunity;                              -- 648
select count(*) from opportunities.opportunity o
  where exists (select 1 from opportunities.opportunity_skill s where s.opportunity_id=o.id);
                                                                               -- 588 (90,74%)
select taxonomy_version, count(*) from opportunities.opportunity_skill group by 1;
                                                                               -- skills-v2: 1844
select canonical_name, count(*) from opportunities.opportunity_skill
  where canonical_name='cicd' group by 1;                                     -- cicd: 221
select requirement, count(*) from opportunities.opportunity_skill group by 1;
                                                                -- UNKNOWN 1630, PREFERRED 127, REQUIRED 87
select normalizer_version, count(*) from opportunities.normalization_result group by 1;
                                                                -- v3: 670, v4: 670
```

## 4. Trazer a stack real para o código atual

Ao tentar rodar o backup pela primeira vez, o serviço `migrate` falhou:

```
FAILED: Can't locate revision identified by '20260926_0043'
```

Diagnóstico: as imagens `opportunity-radar-migrate`/`opportunity-radar-api`/`opportunity-radar-worker`
em uso eram anteriores ao arquivo de migração
`migrations/versions/20260926_0043_source_run_resume_and_manifest.py`
(`git log` mostra esse arquivo commitado em 2026-09-26 21:21, depois do build das imagens
em uso). O código do `compose.yaml` copia o contexto no build (sem bind mount de `src/`
em produção), então uma imagem antiga não vê migração nova mesmo com o arquivo presente
no working tree.

```
docker compose -p opportunity-radar build migrate api worker
docker compose -p opportunity-radar run --rm --no-deps migrate alembic current   # 20260926_0043 (head)
docker compose -p opportunity-radar run --rm --no-deps migrate alembic heads     # 20260926_0043 (head)
docker compose -p opportunity-radar run --rm migrate                             # sem novas migrações a aplicar
```

Nenhuma migração de schema nova nesta branch além da já aplicada; o rebuild das imagens
resolveu o descompasso. Nenhum `down -v`, nenhum volume tocado.

## 5. Reprocessamento oficial

```
docker compose -p opportunity-radar up -d api   # healthy
curl -s -X POST "http://127.0.0.1:8000/opportunities/normalizations/pending?limit=500"
curl -s -X POST "http://127.0.0.1:8000/opportunities/normalizations/pending?limit=500"
curl -s -X POST "http://127.0.0.1:8000/opportunities/normalizations/pending?limit=500"
```

```
batch 1: {"processed":500,"succeeded":497,"review_required":0,"failed":3}
batch 2: {"processed":170,"succeeded":151,"review_required":0,"failed":19}
batch 3: {"processed":0,"succeeded":0,"review_required":0,"failed":0}   -> fila vazia
```

500 + 170 = 670 = total de `raw_items` do acervo (todo o acervo reprocessado, nenhum
item pulado). 3 + 19 = 22 falhas, mesmo total do baseline v3/v4.

## 6. Métricas depois (mesmas queries)

```sql
select count(*) from opportunities.opportunity;                              -- 648 (nenhuma perdida/duplicada)
select count(*) from opportunities.opportunity o
  where exists (select 1 from opportunities.opportunity_skill s where s.opportunity_id=o.id);
                                                                               -- 587 (90,59%)
select taxonomy_version, count(*) from opportunities.opportunity_skill group by 1;
                                                                               -- skills-v3: 1735 (zero linha skills-v2 órfã)
select canonical_name, count(*) from opportunities.opportunity_skill
  where canonical_name='cicd' group by 1;                                     -- cicd: 112
select requirement, count(*) from opportunities.opportunity_skill group by 1;
                                                                -- UNKNOWN 1522, PREFERRED 127, REQUIRED 86
select normalizer_version, count(*) from opportunities.normalization_result group by 1;
                                                                -- v3: 670, v4: 670, v5: 670
select status, count(*) from opportunities.normalization_result
  where normalizer_version='v5' group by 1;                                  -- SUCCEEDED 648, FAILED 22
```

Conferência de que as 22 falhas de `v5` são exatamente o mesmo conjunto de `raw_item_id`
das falhas de `v4` (nenhuma falha nova, nenhuma resolvida por acaso):

```sql
select count(*) from (
  select raw_item_id from opportunities.normalization_result where normalizer_version='v4' and status='FAILED'
  except
  select raw_item_id from opportunities.normalization_result where normalizer_version='v5' and status='FAILED'
) d;
-- 0
```

## 7. Comparação antes → depois

| Métrica | Antes (v4 / skills-v2) | Depois (v5 / skills-v3) |
| --- | --- | --- |
| Oportunidades | 648 | 648 (nenhuma perdida/duplicada) |
| Oportunidades com ≥1 skill | 588 (90,74%) | 587 (90,59%) |
| `opportunity_skill` rows | 1844, todas `skills-v2` | 1735, todas `skills-v3` (zero linha `skills-v2` órfã) |
| Hits de `cicd` | 221 | 112 (-109; alias `ci` removido não casava mais com "CI&T") |
| `requirement=UNKNOWN` | 1630/1844 = 88,4% | 1522/1735 = 87,7% |
| `normalization_result` | v3: 670, v4: 670 | v3: 670, v4: 670, v5: 670 |
| Falhas (`FAILED`, `INVALID_COLLECTED_ITEM_V1`) | 22 sob v3 e v4 | 22 sob v5, **mesmo conjunto** de `raw_item_id` |

A queda de 588 → 587 é esperada e correta: ao contrário do bump v1→v2 (estritamente
aditivo), este bump v2→v3 **remove** o alias `ci` que casava falsamente com o nome da
empresa "CI&T" — uma oportunidade cuja única evidência de skill era esse falso positivo
perdeu a linha e ficou sem skill. A queda de 109 hits de `cicd` (221 → 112) bate
exatamente com a queda de linhas `opportunity_skill` (1844 → 1735 = -109): a mudança só
tocou o alias `ci`, nenhum outro termo foi afetado. Zero falha nova, zero oportunidade
perdida, mesmo `raw_items` (670) reprocessado por completo.

## 8. Restauração da stack

```
docker compose -p opportunity-radar down
```

Todos os containers e a rede do projeto foram parados e removidos (sem `-v`); os volumes
nomeados (`opportunity-radar_postgres_data`, `_local_backups`, `_local_exports`,
`_ollama_models`) não foram tocados — dados intactos. O estado original já tinha todos os
containers parados (nenhum rodando); o `down` deixa a stack real no mesmo estado
"nada rodando", sem consumir recursos. Diferença notada: os containers originais ficaram
"Exited" e não removidos; após `down` eles precisam ser recriados por `up`/`run` na
próxima vez (comportamento padrão do compose, sem impacto em dados ou schema).

```
$ docker volume ls | grep opportunity-radar
local     opportunity-radar_local_backups
local     opportunity-radar_local_exports
local     opportunity-radar_ollama_models
local     opportunity-radar_postgres_data
```

## Backup

- Arquivo: `data/backups/f20-02-pre-skills-v3-2026-09-27.dump` (4.692.123 bytes,
  sha256 `e320ea78242f...`)
- Manifesto: `data/backups/f20-02-pre-skills-v3-2026-09-27.manifest.json`
- Verificado com `scripts/restore_check.py` em banco descartável: **restore check passed**
