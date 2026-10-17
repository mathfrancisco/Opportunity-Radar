# Deploy #3 (A5-fixes, C2-C6, D2-D6) e limpeza das vagas antigas (17/10/2026)

Sem PII e sem segredos.

## Imagens
O run `39035243741` do `pipeline.yml` com `publish=true`, a partir do `main` `512b8f3` (PRs #109, #110 e #111), passou em todos os jobs.
- api `sha256:7442f2af124e6c3e11b35bdd8b377caaf82a104d7f9ffc09b78024bbcf9e109f`
- worker `sha256:872b8c1ef73d6a4f2f5b097a961a09127c03ae1d7755c196fc575a28f3d121b8`
- proxy `sha256:f3fc3e0e4460c2d062357d39de7ea41715977af0a5ef1d24bff959e51cb19d5b`

O deploy usou o `remote-deploy.sh`. A migração `20261017_0072` foi aplicada e o `migrate.env` foi apagado depois do uso. O timer continua horário, com janela de 900 s. `OPPORTUNITY_RETENTION_APPLY=false`.

## Janela manual de verificação
`outcome success`, 40 s de 900 s. O estágio de avaliação reavaliou 500 vagas com `matching-v6`, sem falhas.

## Limpeza das vagas antigas (OK do dono)
Primeiro rodou `scripts/stale_cleanup_report.py` sem `--apply` (dry-run): 1 113 vagas fora da janela de 7 dias, 0 protegidas, 0 sem fonte.

| Empresa | Vagas |
| --- | --- |
| Databricks | 706 |
| Datadog | 357 |
| Telnyx | 45 |
| Netlify | 5 |

Com o OK do dono, rodou com `--apply`. Linhas apagadas: `opportunity` 1 113, `raw_item` 1 143, `match_assessment` 940.
O script rodou dentro do container da API (`docker exec -i opportunity-radar-api-1 python -`), porque o `docker compose exec` não carrega os envs.

## Banco (Neon production `tiny-dust-53844381`)
| Momento | `pg_database_size` | Observação |
| --- | --- | --- |
| Baseline 16/10 | 26,0 MB | antes do R55 |
| Pico 17/10 | 103,4 MB | lote 1 do A5 (Greenhouse sem filtro de 7 dias) |
| 17/10 14:42 UTC | 107 511 808 bytes (107,5 MB) | depois da limpeza; autovacuum rodou às 14:38 UTC |

O autovacuum marca o espaço como livre para reuso, mas não devolve os arquivos ao sistema. Novas linhas reaproveitam esse espaço, então o tamanho deve ficar estável até o espaço livre acabar. Só `VACUUM FULL` reduz o número, e ele trava as tabelas; não foi rodado.

Maiores tabelas por linhas vivas depois da limpeza: `match_factor` 3 720, `opportunity_skill` 1 509, `company_source` 802, `normalization_result` 740.

## Rollback
- Imagens: refazer o `images.env` com os digests do deploy #2 (api `ff84fb02…`, worker `2f70a493…`, proxy `4630069e…`) e rodar o `remote-deploy.sh`. A migração `0072` tem downgrade documentado.
- Limpeza: não tem desfazer no banco. As vagas voltam se ainda estiverem publicadas e dentro da janela de 7 dias, na próxima coleta das fontes.
