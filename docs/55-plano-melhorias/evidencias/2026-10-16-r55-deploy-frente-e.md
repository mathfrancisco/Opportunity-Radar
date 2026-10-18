# Deploy da Frente E e de B3/B4/D1 na VM (16/10/2026)

Sem PII e sem segredos. A saída foi filtrada para não mostrar DSN, chaves nem subjects.

## Imagens publicadas
O run `38974394971` do `pipeline.yml`, com `publish=true` a partir do `main` `ccba644`, passou em todos os jobs. Os manifests têm `linux/amd64` e `linux/arm64`.
- api `sha256:7c7021b3647a9b8191cd310c5c1a7a83c3efd42afae19d5c2dae8c05b9b48394`
- worker `sha256:d67f105b8d563a3b8fc1b4d1e862ed84d19fa6faa2b019129724820057597678`
- proxy `sha256:5ff959be13c8621b348ff1fc463581ab28ebcb1881e4d350375874347dbc9dc5`

## Deploy
- Envs gerados de novo, com `pipeline.env` em 900 s (`PIPELINE_DEADLINE_SECONDS` e `PIPELINE_WINDOW_SECONDS`) e `OPPORTUNITY_RETENTION_APPLY` desligada (padrão `false`). O `migrate.env` foi transferido, usado e removido pelo `remote-deploy.sh` (`migration=ok migrate_env_removed=true`).
- O Neon production `tiny-dust-53844381` está em `alembic 20261016_0071`, com `attcompression='l'` (lz4) em `raw_item_payload.payload`.
- As units do systemd foram instaladas a partir do `main`: `OnCalendar=hourly UTC`, `TimeoutStartSec=960`, `Persistent=false`.
- `api running healthy`, `proxy running`; `/health/live` respondeu 200 pelo hostname público.

## Primeira janela horária (2026-10-16 22:31:15 UTC, `run_id 2026-10-16T22:31:15Z-0d971d6b`)
- `exit_code 0`, `outcome success`, duração de 10,4 s numa janela de 900 s.
- `retention` rodou em dry-run em 344 ms, sem apagar nada.
- `collect_enabled_sources` teve `skipped 1`: a fonte com agendamento manual foi pulada. O card R55-B2 trata disso.
- A normalização processou 95 itens pendentes: as oportunidades passaram de 100 para 200.
- Medição na janela: `database_size_bytes 25993216`, `database_size_alert false`.

## Tamanho do banco
| Momento (UTC) | `pg_database_size` | Oportunidades | Raw items | Observações |
| --- | --- | --- | --- | --- |
| 2026-10-16 15:48, antes | 25 993 216 | 100 | 225 | 291 |
| 2026-10-16 22:32, depois do deploy e da 1ª janela | 28 622 848 | 200 | 225 | 291 |

## Rollback
- Imagens anteriores: api `sha256:2bd72817…`, worker `sha256:e10f9cb5…`, proxy `sha256:35198bda…`. Para voltar, refaça o `images.env` com esses digests e rode o `remote-deploy.sh`.
- Timer: reinstalar as units do commit `deaf0a3` (06:00 UTC, janela de 3 600 s).
- Para evitar exclusões: deixar `OPPORTUNITY_RETENTION_APPLY=false`, que é o estado atual.
