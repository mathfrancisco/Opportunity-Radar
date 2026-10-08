# F53-06 — compatibilidade Neon e migração

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-01.

## Objetivo e base verificada

Validar Neon PostgreSQL 17 antes de qualquer migração. O código atual usa
`pool_pre_ping=True`, `API_STATEMENT_TIMEOUT_MS` e schemas/extensões que incluem
`vector` e `unaccent`; isto não prova compatibilidade Neon. A separação de URL
runtime/direct não é configuração existente: projetá-la somente se testes a
justificarem.

## Procedimento futuro

1. Criar branch Neon de ensaio no projeto correto, medir quota inicial, e
   confirmar PG 17, extensões, permissões e inventário Alembic de schemas:
   `profile`, `company_radar`, `acquisition`, `opportunities`, `matching`,
   `crm`, `platform` e `dashboard` na revisão atual.
2. Aplicar migrações em branch/piloto e executar testes de sessão, FTS,
   `unaccent`, `vector`, permissões e timeout. Não usar banco de produção.
3. Verificar connection string poolada para API e, se o provedor a exigir,
   conexão direta limitada para migração/restore. Documentar motivo e dono de
   cada URL; não criar variável fictícia antes da implementação.
4. Executar restore seco cedo com cópia de fixture em destino isolado que tenha
   privilégios `CREATEDB`; `DATABASE_URL` com sufixo `_test` sozinho não torna
   seguro usar servidor de produção.
5. Medir CU-h, armazenamento, suspensão e conexões. Uma base a 0,25 CU durante
   744 h consome cerca de 186 CU-h, portanto não manter conexão ou ping 24x7.
6. Parar se extensão, schema, restore ou quota falhar; não adaptar produção por
   tentativa sem evidência.

## Aceite e evidências

| ID | Positivo | Negativo/operacional |
| --- | --- | --- |
| AC01 | PG17, `vector`, `unaccent` e inventário Alembic atual funcionam | extensão/schema ausente bloqueia migração |
| AC02 | API preserva pre-ping e timeout | consulta acima do timeout recebe cancelamento esperado |
| AC03 | restore de fixture isolada compara manifesto | URL de produção ou sem `CREATEDB` é rejeitada |
| AC04 | projeção mensal fica <=80 CU-h e <1 GB | 24x7 a 0,25 CU é registrada como inaceitável |

Guardar relatório de migração, saída de teste e consumo redigidos. Nunca anexar
URL, credenciais, dump ou payload de usuário.

## Matriz de compatibilidade e comandos existentes

Use branch ou projeto Neon isolado. Antes de tocar destino real, registre versão
PG, extensões requeridas, URL direta/pool e privilégio `CREATEDB` em matriz
redigida. Execute apenas scripts existentes e com URL isolada:

```text
scripts/backup.py --output-dir <diretório> --label <rótulo> --prune-days 0
scripts/restore_check.py --dump <arquivo> --backup-dir <diretório>
```

`restore_check.py` cria e derruba scratch; não execute contra banco operacional.
Ele também passa DSN ao cliente atual, então F53-14 deve resolver exposição de
senha em argv antes do piloto cloud. Falha de extensão, timeout ou restore
impede migration; descarte somente branch de ensaio após preservar evidência.

## Consultas de compatibilidade e promoção

Execute estas consultas só contra banco piloto isolado, por cliente que receba
URL por variável protegida ou serviço de credenciais. Não ponha DSN na linha de
comando, histórico PowerShell ou evidência.

```sql
SELECT current_database(), current_setting('server_version');
SELECT extname, extversion FROM pg_extension ORDER BY extname;
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
ORDER BY table_schema, table_name;
```

1. Compare resultado à origem, migrations, extensões e inventário da revisão
   Alembic. Não aceite número fixo de schemas após uma migration nova.
2. Use URL direta apenas em migration, dump/restore e administração aprovada;
   use URL poolada no runtime somente após o driver passar compatibilidade.
3. Rode migration após restore piloto e registre revisão, duração, schema alvo e
   contagens redigidas.
4. Teste criar, ler, atualizar e remover no banco isolado, inclusive transação
   de coleta; nunca faça esse teste no banco operacional.
5. Projete `statement_timeout` e conexões por medição; não aplique timeout
   global sem consultas legítimas, resultado e rollback.

Falha de extensão, schema ou migration interrompe promoção. Preserve diagnóstico
redigido e corrija o piloto antes de trocar URL de runtime.

## Rollback e gate

Descartar branch de ensaio, não a branch de produção. F53-14 depende deste
restore cedo, mas backup operacional ainda é requisito separado; F53-10, F53-12
e F53-15 só começam com AC01–AC04.
