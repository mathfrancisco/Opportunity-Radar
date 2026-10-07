# F53-18 — cutover, rollback e recuperação

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-13, F53-16, F53-17.

## Objetivo

Alterar tráfego/dados reais somente após piloto, backup, monitoramento e
retenção. Rollback de tráfego não pode apagar escrita posterior.

## Sequência futura

1. Abrir janela com owner, digest, DNS, estado banco, RPO/RTO e critério abortar.
2. Colocar writers em manutenção, esperar jobs/claims e registrar última atividade.
3. Fazer dump final, checksum, cópia externa e restore isolado antes de promover.
   O `scripts/restore_check.py` é apenas ensaio: ele cria `restore_check_<data>`,
   testa e remove scratch; ele não importa no Neon destino. Implementar e revisar
   procedimento separado de import com `pg_restore`, credencial fora de argv,
   destino vazio aprovado e verificação de revisão, extensões, contagens e
   relações antes de mudar DNS.
4. Alterar DNS em etapa pequena e validar TLS/CORS/JWT, dados, timer e métricas.
5. Se falhar antes de escrita, restaurar record/digest. Após escrita, quiescer,
   preservar os dois lados e decidir reconciliação humana; não sobrescrever.
6. Encerrar com relatório de custo, métricas, backup, incidentes e aceite owner.

## Aceite

| ID | Positivo | Negativo/operacional |
| --- | --- | --- |
| AC01 | restore final validado | checksum/manifest falho aborta |
| AC02 | writers quiescentes | writer ativo bloqueia promoção |
| AC03 | DNS/TLS/auth/dados passam | falha restaura tráfego planejado |
| AC04 | rollback preserva escrita nova | pós-escrita exige reconciliação humana |
| AC05 | relatório fecha custo/riscos | ausência owner mantém janela aberta |

## Diagnóstico e evidências

Erro de import, extensão ausente, checksum diferente ou contagem divergente
interrompe a janela antes de DNS. TTL ainda propagando não autoriza nova alteração
concorrente: registrar o resolver, horário e record observado. Se a API falhar
após DNS, só restaurar tráfego ao digest/record conhecido depois de provar zero
escritas no novo destino e compatibilidade de schema; caso contrário, congelar
writers, preservar ambos os lados e decidir reconciliação antes de novo DNS.

O pacote futuro contém plano da janela, manutenção, hash, checksum, resultado
de restore-check, prova de import, queries agregadas de comparação, DNS/TLS,
observação e decisão do owner. Redigir host, ID, URL, usuário e todos os
segredos. Um log sem correlação entre dump final e import não satisfaz AC01.

Guardar cronologia, hashes e IDs mascarados; nunca dump, token, DSN ou state.

## Rollback e recuperação

Tráfego volta por DNS/digest; banco não é restaurado por reflexo. Recuperar
dados primeiro em isolado, comparar e obter aprovação. Parar a janela em falha.

## Procedimento executável futuro de import

Executar primeiro este roteiro em destino isolado. O `restore_check.py` atual
cria scratch via banco administrativo e o remove: ele não importa no destino
Neon escolhido e nunca deve ser usado para import de produção. Antes da janela,
registrar revisão do repositório, RPO/RTO, origem, destino Neon **novo e vazio**,
owner, TTL e compatibilidade de PostgreSQL, extensões, roles e schema.

1. Congelar todos os writers: manutenção de mutações API, timer/jobs, claims e
   workers; aguardar claims finais ou deadline e registrar contagens.
2. Produzir dump final, manifesto, cópia cifrada e checksum pelo F53-14. Manter
   origem, dump e cópia externa imutáveis; transferir dump e manifesto juntos,
   validar hash e descriptografar em diretório protegido no host de import.
3. Criar `PGPASSFILE` 0600 no cofre/host no formato libpq
   `host:port:database:user:password`; o quinto campo vem do cofre e nunca é
   escrito em comando, argv, log ou evidência. Exportar apenas `PGHOST`,
   `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSFILE`, `PGSSLMODE=verify-full` e
   `PGSSLROOTCERT` de CA aprovada e testada.

```bash
umask 077
export PGHOST='<HOST_NEON_NOVO>' PGPORT=5432 PGDATABASE='<BANCO_VAZIO>' PGUSER='<USUARIO_IMPORT>'
export PGPASSFILE='<ARQUIVO_SEGURO_0600>' PGSSLMODE=verify-full PGSSLROOTCERT='<CA_APROVADA>'
DUMP_PATH='<CAMINHO_PROTEGIDO_DUMP_DESCRIPTOGRAFADO>'
test -r "$PGPASSFILE" && test -r "$PGSSLROOTCERT"
sha256sum --check '<CHECKSUM_DO_CIPHERTEXT_TRANSFERIDO>'
psql -v ON_ERROR_STOP=1 -c 'select current_database(), version(), inet_server_addr(), ssl from pg_stat_ssl where pid = pg_backend_pid()'
psql -v ON_ERROR_STOP=1 -c "select count(*) from pg_tables where schemaname not in ('pg_catalog','information_schema')"
```

Confirmar com o owner que host/projeto exibidos correspondem ao destino Neon novo
aprovado antes de qualquer import; contagem zero não impede host errado. O segundo
comando precisa retornar zero antes de import, salvo schemas/extensões
explicitamente aprovados. O primeiro `psql`, sob `verify-full`, deve retornar
`ssl = t`; falha de CA, hostname ou handshake bloqueia import. O checksum é do
ciphertext criado no F53-14 e é conferido **depois da transferência e antes da
descriptografia**; hash de plaintext só vale se gerado separadamente. Antes da
janela, F53-14 deve escolher e provar em isolado o cifrador, versão, chave e
comando de descriptografia aprovados, registrar esse comando no procedimento
operacional e então criar `DUMP_PATH`; sem essa prova não há cutover. Conferir
extensões/roles suportados no destino; se dump precisa de role/extensão
indisponível, parar e corrigir compatibilidade, nunca usar `--clean` ou
`--create`.

```bash
test -s "$DUMP_PATH"
pg_restore --no-owner --no-privileges --exit-on-error --dbname="$PGDATABASE" "$DUMP_PATH"
```

Não executar upgrade cego antes do restore: confirmar Alembic current/head e a
sequência de migrações porque schema já veio no dump. Depois, executar somente
consultas de leitura. A relação `alembic_version` e o campo `version_num` são os
usados pelo código atual de backup/restore; contagens de relações vêm somente do
manifesto final, sem inventar tabelas de órfãos.

```bash
psql -v ON_ERROR_STOP=1 -c "select count(*) as schemas_aplicacao, bool_or(nspname = 'dashboard') as dashboard_presente from pg_namespace where nspname !~ '^pg_' and nspname <> 'information_schema'"
psql -v ON_ERROR_STOP=1 -c 'select version_num from alembic_version'
psql -v ON_ERROR_STOP=1 -c "select connamespace::regnamespace as schema, conname from pg_constraint where not convalidated"
```

Comparar a primeira saída com os oito schemas esperados, incluindo `dashboard`,
e a revisão com head/revisão da origem registrados na janela. Consultar as
relações e contagens apenas com os nomes do manifesto final. Divergência de
revisão, contagem, extensão ou constraint bloqueia DNS e liberação de writers.

4. Executar smoke F53-16 para API, auth, TLS, CORS, Pages e hostname antes/depois
   da alteração DNS; respeitar TTL e registrar resolvedor/horário.
5. Liberar writers somente após comparações e smoke passarem. Observar orçamento,
   RPO/RTO, conexões e backup no período acordado.

| Verificação | Prova | Artefato redigido |
| --- | --- | --- |
| V01 | origem quiescente e dump/manif. final | UTC, hash, repo revision |
| V02 | destino vazio e pg_restore sem erro | host mascarado, versão, exit code |
| V03 | schemas/revisão/relações/constraints conferem | contagens agregadas |
| V04 | DNS e smoke passam antes de writers | TTL, status e build ID |
| V05 | RPO/RTO/orçamento observados | cronologia e decisão owner |

Antes de escrita, rollback restaura apenas tráfego ao record/digest conhecido e
preserva ambos os bancos. Depois de escrita, congelar origem e destino, preservar
e reconciliar com aprovação humana; DNS sozinho não autoriza overwrite ou restore.
