# F53-13 — economia de storage e retenção

**Prioridade:** P1. **Estado:** planejado. **Depende de:** F53-06, F53-14.

## Objetivo

Reduzir armazenamento somente depois de backup restaurável e mapa de lineage.
Proposta inicial: raw de 365 para 30 dias, preservando canônico, CRM, lineage e
última referência; assessments opt-in por sete dias, protegendo a referência e
o último item. Cache usa TTL e expiração, não purge indiscriminado.

## Procedimento futuro

1. Inventariar tabelas, bytes, crescimento e referências que dependem de raw,
   assessment e cache. Confirmar que dump/manifest e restore F53-14 cobrem estes
   dados antes de qualquer deleção.
2. Escrever migração/job futuro idempotente que seleciona candidatos por data,
   não por identificação pessoal; manter relatório dry-run com contagem por tipo.
3. Executar dry-run em fixture e verificar que canônico, lineage/CRM, última
   evidência e referência de assessment sobrevivem. Não usar retenção para apagar
   dados exigidos por auditoria.
4. Aplicar lote pequeno aprovado, medir bytes liberados e restaurar em destino
   isolado para conferir relações e contagens de manifesto.
5. Configurar TTL de cache com chave/versionamento; expiração remove entrada
   vencida, sem confundir cache com dado fonte ou backup.
6. Só então propor 30/7 dias em produção, com janela, owner e relatório antes/
   depois. Alteração de retenção é reversível somente via backup validado.

## Aceite

| ID | Positivo | Negativo/operacional |
| --- | --- | --- |
| AC01 | dry-run lista somente candidatos permitidos | referência protegida impede remoção |
| AC02 | restore prova relações pós-lote | manifesto divergente bloqueia promoção |
| AC03 | bytes e crescimento são medidos | redução sem métrica não é aceita |
| AC04 | cache expira por TTL | purge não apaga canônico/CRM/lineage |

Evidência inclui política, contagens agregadas, hash/manifest e relatório de
restore, tudo redigido. Não anexar raw, currículo ou dados de vaga sensíveis.

## Rollback e gate

Suspender job de retenção e restaurar somente no ambiente isolado até a prova
ser revisada. Se dados reais foram removidos indevidamente, usar backup externo
F53-14 sob incidente; não repetir purge. F53-18 requer os quatro ACs.

## Execução segura de retenção futura

No banco isolado, obter tamanho por schema/tabela com SQL somente leitura
revisado e registrar apenas totais. O job futuro recebe data de corte, lote e
`--dry-run`; ele deve listar contagens e excluir candidatos com canônico, CRM,
lineage, referência ou último assessment. Fazer backup pré-lote; aplicar lote
pequeno apenas no isolado; rodar checks pós-lote de relações protegidas; gerar
novo dump/manifest e restaurá-lo em segundo alvo isolado. Preservar backup
pré-lote. Sem dry-run, novo dump e restore pós-lote, não propor purge real.

## Diagnóstico somente leitura e lote futuro

Execute diagnósticos apenas no banco isolado, com `PGSERVICE`/`PGPASSFILE` já
protegidos. Não passe DSN com senha no argv e não use estas consultas para apagar
dados.

```bash
export PGSERVICE=opportunity_radar_storage_test
export PGPASSFILE=<caminho-protegido>
psql 'service=opportunity_radar_storage_test' -v ON_ERROR_STOP=1 <<'SQL'
SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size;
SELECT schemaname, relname, pg_size_pretty(pg_total_relation_size(relid)) AS total
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC LIMIT 20;
SELECT schemaname, indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes ORDER BY pg_relation_size(indexrelid) DESC LIMIT 20;
SQL
```

1. Registre totais por schema/tabela/índice, baseline, crescimento semanal e
   projeção mensal. A redução só é mensurável com o mesmo método de coleta.
2. Escreva política atual e proposta: raw 365→30 dias, assessments opt-in sete
   dias e cache por TTL. Preserve canônico, CRM, proveniência/lineage, referência
   protegida e item mais recente conforme o contrato de cada tabela.
3. Antes de implementar, nomeie script futuro e defina contrato `--dry-run`,
   data de corte, lote, relatório e reinício idempotente. O script não existe;
   não execute comando inventado.
4. Em fixture, teste fronteira temporal, referência protegida, relações pendentes,
   reinício no meio do lote e zero referências pendentes após o lote. Relação
   dangling bloqueia a proposta.
5. Faça backup/restore aprovado antes do primeiro lote e novo backup/restore
   depois. Preserve backup anterior até validar o lote posterior.

`VACUUM` regular pode recuperar espaço para reutilização interna; não promete
reduzir disco faturado. Só declare economia física após medição do provedor.
