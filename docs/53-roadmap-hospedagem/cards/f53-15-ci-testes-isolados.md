# F53-15 — CI e testes isolados

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-05, F53-06, F53-07.

## Objetivo e base atual

Os testes devem reproduzir auth sem Clerk, banco ou segredo reais. O guard atual
exige RUN_DATABASE_INTEGRATION=1, DATABASE_INTEGRATION_ISOLATED=1 e URL com
sufixo _test, mas destino e servidor também devem ser isolados. O E2E atual do
pipeline usa curl anônimo e não atende ao futuro contrato Clerk.

## Sequência futura

1. Criar fixtures offline de JWT, JWKS, issuer, azp, audiência configurada e
   OWNER_SUB. A chave de teste não pode ser confiável em produção.
2. Fazer startup fail-closed: auth, issuer ou allowlist ausentes impedem servir
   rota privada. Não criar bypass de produção.
3. Trocar E2E anônimo por fixture JWT e testar dono, token ausente/expirado,
   outro sub, CORS estranho e JWKS inválido.
4. Rodar npm run check e verificações backend pertinentes, guardando saída
   redigida. Falha não usa continue-on-error.
5. Rodar integração uma vez no final apenas com variáveis de isolamento e
   servidor/compartment separado.
6. Inspecionar manifest publicado de api e worker: deve conter linux/arm64;
   Buildx instalado não prova plataforma publicada.

## Aceite

| ID | Teste | Saída esperada |
| --- | --- | --- |
| AC01 | startup sem auth | falha fechada |
| AC02 | JWT/JWKS fixture do dono | E2E autorizado sem Clerk live |
| AC03 | claims inválidos ou outro sub | 401 ou 403 determinístico |
| AC04 | URL não isolada | guard recusa antes de tocar dados |
| AC05 | manifest de imagens | api e worker incluem linux/arm64 |

Preservar JUnit, saída, workflow e prova de isolamento sem token, DSN ou env.

## Rollback e gate

Reverter workflow e auth como unidade se a prova falhar. Revogar fixture
comprometida. F53-16 e F53-18 dependem de AC01–AC05.

## Comandos e isolamento futuros

O contrato de fixture e YAML futuro está no [runbook: F53-15](../../53-plano-hospedagem-cloudflare-oracle-neon-clerk.md#f53-15-testes-isolados)
e na seção [Fixture offline de Clerk no CI](../../53-plano-hospedagem-cloudflare-oracle-neon-clerk.md#fixture-offline-de-clerk-no-ci).
Executar no root backend, em etapas separadas, e registrar apenas exit code e
saída redigida:

```bash
ruff check .
mypy
pytest -q
```

Executar o check do frontend no seu diretório, sem imprimir `.env`:

```bash
cd apps/web
npm ci
npm run check
```

Para integração PG17 isolada, exportar somente no job
`RUN_DATABASE_INTEGRATION=1`, `DATABASE_INTEGRATION_ISOLATED=1` e URL de banco
`_test` em servidor isolado. Fixtures offline incluem JWKS/JWT/issuer/owner;
não recebem segredo Clerk, não fazem rede live e não oferecem bypass habilitável
em produção. Token fixture deve ser criado em arquivo temporário 0600 ou memória,
nunca argv/log.

## Mapa de comandos e diagnóstico

Executar unitários e E2E em runner sem credencial Clerk. Executar `npm run
check` no diretório que já o declara e registrar versão Node/pacote, sem imprimir
arquivo de ambiente. Rodar integração isolada uma única vez no fim; validar o
nome do banco, host e compartment antes de exportar variáveis. Nunca executar
essa suite contra Neon operacional para "economizar" ambiente.

Falha de assinatura fixture, JWKS inacessível, issuer inesperado ou ausência de
owner deve falhar como o servidor falharia em produção: fechado. Falha ARM no
manifest exige corrigir build/publicação e revalidar digest; não é aceitável
testar em x86 e inferir que A1 funciona. Arquivar comando, exit code e artefato
redigidos por revisão.
