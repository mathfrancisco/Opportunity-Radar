# CARD F14-02 — Homologação e kill switch de fonte pela interface

- **Status:** Backlog
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

- [ ] Homologar e habilitar uma fonte externa é possível pela tela quando o gate está
      satisfeito.
- [ ] Com requisito faltando, a tela explica qual é e não envia a habilitação.
- [ ] Conflito de versão é reportado como conflito e recuperável sem recarregar a página.
- [ ] Desabilitar uma fonte pela tela interrompe sua coleta agendada.
- [ ] A recusa do servidor aparece na tela com a mensagem do domínio.

## Verificação

Homologar uma fonte pela tela e confirmar coleta agendada no ciclo seguinte; forçar conflito
alterando a fonte por API entre a leitura e o envio; tentar habilitar uma fonte sem termos
revisados e confirmar a recusa.

## Arquivos prováveis

- `apps/web/src/routes/SourcesPage.tsx`
- `apps/web/src/features/sources/api.ts`
- `apps/web/src/features/sources/useSources.ts`
- `apps/web/src/features/sources/api.test.ts`
