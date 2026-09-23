# CARD F14-06 — Teste ao vivo do collector pela interface

- **Status:** Backlog
- **Fase:** 14 — Cadastro e curadoria pela interface
- **Depende de:** F14-02
- **Bloqueia:** Milestone M
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §3.3

## Resultado

O operador confirma pela tela que o collector de uma fonte externa lê o endpoint público, e
esse teste é o que grava a evidência confirmada — a mesma prova que o terminal exige hoje,
com o mesmo registro de auditoria.

## Contexto

F14-01 a F14-05 tiraram do terminal o cadastro, a homologação, a vaga avulsa e o vínculo de
empresa. Ficou um passo: `evidence_status = confirmed` só é gravado por
`scripts/enable_sources.py`, que chama cada collector contra o endpoint público com
`max_items` pequeno, e só grava a evidência se o collector ler o schema sem erro. Sem esse
passo, uma fonte externa criada pela tela nasce `unverified` e fica bloqueada no gate para
sempre, e o primeiro critério da §3.3 — criar, homologar, habilitar e executar uma fonte
inteira sem terminal — não fecha.

O script, porém, faz mais que testar: com `--accept-terms`, ele também marca termos
revisados, data de revisão e habilita, tudo de uma vez e em lote. A tela não pode herdar
isso. Termos revisados são uma afirmação humana sobre uma fonte específica, e a F14-02 já
existe para registrá-la.

## Escopo

- Levar a sonda do script para o domínio (`AcquisitionService.probe_source`), para que o
  script e a API usem a mesma função e não duas definições de "o collector funciona".
- `POST /sources/{id}/probe` com `expected_version`: executa o collector com `max_items`
  pequeno, sem persistir `RawItem` nem `SourceRun`, e responde o resultado — ok, itens vistos,
  requisições HTTP, código e resumo do erro.
- Quando a sonda passa: gravar `evidence_status = confirmed`, `collector_local_tested = true`
  e o `homologation_audit` em `configuration`, com a referência pública do endpoint, a data e
  a telemetria — o mesmo registro que o script grava.
- Quando a sonda falha: não alterar a fonte, e devolver o código do domínio
  (`SOURCE_NOT_FOUND`, `PARSER_SCHEMA_CHANGED`, `SOURCE_TIMEOUT`…).
- Registrar toda tentativa, com sucesso ou falha, numa tabela própria de sondas: quem pediu
  (tela ou script), quando, resultado e telemetria. A evidência confirmada precisa apontar
  para a tentativa que a produziu.
- Botão "Testar o collector agora" no painel de homologação, com o resultado no próprio
  painel e a lista do que ainda falta atualizada.

## Fora de escopo

- Marcar termos revisados ou habilitar a fonte como efeito da sonda. Continuam sendo passos
  explícitos da F14-02.
- Sondar em lote pela interface.
- Sondar fonte habilitada, que já está coletando e tem evidência melhor que uma sonda: as
  próprias execuções.
- Fonte manual, que não tem endpoint.

## Notas de implementação

A sonda faz requisição real a terceiro, a pedido de um clique. Então ela precisa das mesmas
travas de uma execução: a política de rate limit da fonte, o circuit breaker e um intervalo
mínimo entre sondas da mesma fonte — um duplo clique não pode virar duas requisições, e um
operador impaciente não pode martelar um board público. A resposta a uma sonda cedo demais é
recusa com o tempo restante, não fila.

A sonda não persiste o que leu. Ela prova que o collector entende o endpoint, e qualquer
vaga lida ali entraria no radar sem `SourceRun` — exatamente o atalho que a fase proíbe.

`reviewed_at` continua sendo a data da revisão humana dos termos, não a data da sonda. As
duas coisas aparecem separadas no painel.

## Critérios de aceite

- [ ] Uma fonte externa criada pela tela chega a `confirmed` só por uma sonda bem-sucedida.
- [ ] Sonda que falha não altera a fonte e mostra o código e o resumo do domínio.
- [ ] Nenhuma sonda persiste `RawItem`, `SourceRun` ou `Opportunity`.
- [ ] Duas sondas seguidas da mesma fonte dentro do intervalo mínimo resultam numa só
      requisição externa.
- [ ] Termos revisados e habilitação continuam exigindo ação explícita depois da sonda.
- [ ] Script e API usam a mesma função de sonda, e ambos gravam a tentativa.
- [ ] O primeiro critério da §3.3 fecha: criar, sondar, homologar, habilitar e executar uma
      fonte externa sem terminal.

## Verificação

Teste de domínio da sonda com collector falso (sucesso, schema quebrado, timeout); teste de
integração do endpoint contra o board local do compose (`tests/e2e/fake_job_board.py`),
incluindo conflito de versão e sonda repetida dentro do intervalo; passo E2E que cria uma
fonte Greenhouse pela API apontando para o board local, sonda, homologa, habilita e espera a
coleta agendada.

## Arquivos prováveis

- `src/opportunity_radar/acquisition/service.py`
- `src/opportunity_radar/presentation/http/acquisition.py`
- `scripts/enable_sources.py`
- `migrations/versions/`
- `apps/web/src/components/SourceControlsPanel.tsx`
- `apps/web/src/features/sources/api.ts`
- `.github/workflows/pipeline.yml`
