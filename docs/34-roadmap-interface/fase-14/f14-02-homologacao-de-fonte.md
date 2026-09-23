# CARD F14-02 — Homologação e kill switch de fonte pela interface

- **Status:** Concluído em 2026-09-23
- **Fase:** 14 — Cadastro e curadoria pela interface
- **Depende de:** F14-01
- **Bloqueia:** Milestone M
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §3

## Resultado

O operador registra termos revisados, collector testado e data de revisão, e habilita ou
desabilita a fonte pela tela, com conflito de versão tratado.

## Contexto

`PATCH /sources/{id}` já aplica o gate e exige `expected_version`. Hoje a única forma de
homologar uma fonte é `scripts/enable_sources.py`, que decide por lote e exige
`TERMS_REVIEWED=1` no terminal. Falta o caso do operador que revisou uma fonte específica e
quer registrar exatamente isso.

## Escopo

- Controles por fonte para `enabled`, `terms_reviewed`, `collector_local_tested` e
  `reviewed_at`, enviando a versão atual como `expected_version`.
- Bloquear a habilitação na interface enquanto o gate não estiver satisfeito, explicando
  qual requisito falta.
- Tratar 409 como conflito: avisar que a fonte mudou, recarregar o registro e preservar a
  intenção do operador.
- Refletir imediatamente a mudança na lista e na saúde da fonte.

## Fora de escopo

- Aceitar termos em massa pela interface.
- Alterar configuração ou tipo da fonte neste card.
- Remover o gate para fonte manual, que já é exceção no domínio.

## Notas de implementação

A tela não decide o gate: ela lê `evidence_status`, `reviewed_at`, `terms_reviewed` e
`collector_local_tested` do próprio recurso e desabilita o controle com a justificativa. O
servidor continua sendo a autoridade, e o 422 dele precisa ser exibido tal como veio.

## Critérios de aceite

- [x] Homologar e habilitar uma fonte externa é possível pela tela quando o gate está
      satisfeito.
- [x] Com requisito faltando, a tela explica qual é e não envia a habilitação.
- [x] Conflito de versão é reportado como conflito e recuperável sem recarregar a página.
- [x] Desabilitar uma fonte pela tela interrompe sua coleta agendada.
- [x] A recusa do servidor aparece na tela com a mensagem do domínio.

## Verificação

Homologar uma fonte pela tela e confirmar coleta agendada no ciclo seguinte; forçar conflito
alterando a fonte por API entre a leitura e o envio; tentar habilitar uma fonte sem termos
revisados e confirmar a recusa.

## Nota de execução

O conflito não era um conflito. `PATCH /sources/{id}` com versão desatualizada respondia
422 `INVALID_CONFIGURATION`, a mesma resposta do gate recusado, e nenhuma tela conseguiria
distinguir "releia" de "falta um requisito". Agora é 409 `version_conflict`
(`SourceVersionConflictError`), e o painel mostra o aviso de conflito. Recarregar busca a
versão nova sem desmarcar o que o operador marcou.

O painel de homologação abre por fonte, lê o próprio recurso e lista o que falta antes de
habilitar. O botão fica desabilitado com a lista ligada a ele por `aria-describedby`. O
servidor continua sendo a autoridade, e a recusa dele aparece como veio.

**Limite que o card não resolve:** evidência `confirmed` só é gravada pelo teste do
collector contra o endpoint público (`scripts/enable_sources.py`), e testar ao vivo está
fora do escopo desta fase. Uma fonte externa criada pela tela nasce `unverified` e fica
bloqueada no gate, que explica exatamente isso. Habilitar e desabilitar pela tela vale para
fontes cuja evidência já foi confirmada — o kill switch e a reabilitação — e para a fonte
manual, que não tem gate.

Desabilitar interrompe a coleta agendada porque o worker só coleta fontes habilitadas
(`test_a_disabled_source_never_runs_by_the_clock`). Verificado no navegador: gate listando o
que falta, conflito forçado por API entre a leitura e o envio, habilitar e desabilitar.

## Arquivos prováveis

- `apps/web/src/routes/SourcesPage.tsx`
- `apps/web/src/features/sources/api.ts`
- `apps/web/src/features/sources/useSources.ts`
- `apps/web/src/features/sources/api.test.ts`
