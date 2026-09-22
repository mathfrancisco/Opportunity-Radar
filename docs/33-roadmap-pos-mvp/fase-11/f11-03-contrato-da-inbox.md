# CARD F11-03 — Expor atualidade no contrato da Inbox

- **Status:** Done
- **Fase:** 11 — Reavaliação por mudança de versão
- **Depende de:** F11-01
- **Bloqueia:** F11-04
- **Origem no roadmap:** [Fase 11](../../33-roadmap-pos-mvp.md#fase-11--reavaliação-por-mudança-de-versão)

## Resultado

A API diferencia assessment atual, fallback desatualizado e oportunidade nunca avaliada.

## Contexto

Filtrar apenas pela versão ativa remove o resultado antigo durante o backfill. Retornar
apenas o último assessment também faz a Inbox parecer atual quando não está.

## Escopo

- Preferir o assessment atual quando ele existir.
- Usar o assessment mais recente como fallback enquanto a reavaliação estiver pendente.
- Expor versões avaliada e atual, `rules_version` e `is_stale`.
- Retornar campos nulos quando nunca houve assessment.

## Fora de escopo

- Alterar a apresentação visual.
- Reavaliar oportunidades dentro da query da Inbox.

## Notas de implementação

O read model precisa resolver a escolha em SQL sem carregar agregados completos. Manter
paginação, filtros e ordenação atuais.

## Critérios de aceite

- [x] Assessment atual sempre vence o fallback.
- [x] Assessment antigo retorna com `is_stale=true`.
- [x] O contrato expõe versões suficientes para explicar a desatualização.
- [x] Oportunidade nunca avaliada permanece na Inbox sem score inventado.
- [x] Paginação e filtros não duplicam oportunidades durante o backfill.

## Verificação

Cobrir estados sem assessment, somente antigo, antigo mais atual e múltiplos históricos
para a mesma oportunidade.

## Arquivos prováveis

- `src/opportunity_radar/dashboard/queries.py`
- `src/opportunity_radar/presentation/http/dashboard.py`
- `apps/web/src/features/dashboard/api.ts`
- `tests/backend/dashboard/`
- `apps/web/src/features/dashboard/api.test.ts`
