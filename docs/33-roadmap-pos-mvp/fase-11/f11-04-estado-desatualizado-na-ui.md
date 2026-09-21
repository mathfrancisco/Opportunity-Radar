# CARD F11-04 — Mostrar assessment desatualizado na UI

- **Status:** Backlog
- **Fase:** 11 — Reavaliação por mudança de versão
- **Depende de:** F11-02, F11-03
- **Bloqueia:** Gate da Fase 11
- **Origem no roadmap:** [Fase 11](../../33-roadmap-pos-mvp.md#fase-11--reavaliação-por-mudança-de-versão)

## Resultado

O usuário distingue resultado atual, resultado antigo em reprocessamento e oportunidade
ainda não avaliada.

## Contexto

Durante uma reavaliação em massa, esconder a oportunidade ou mostrar o score antigo sem
aviso faz a interface discordar silenciosamente do perfil ativo.

## Escopo

- Mostrar marcador de desatualização no card e no detalhe.
- Expor versões avaliada e atual em texto acessível.
- Atualizar automaticamente quando o novo assessment chegar.
- Manter o resultado antigo utilizável enquanto o backfill roda.

## Fora de escopo

- Barra global de progresso do backfill.
- Edição do perfil neste card.

## Notas de implementação

O marcador não depende apenas de cor. O texto deve explicar que o score usa uma versão
anterior e que a reavaliação está pendente.

## Critérios de aceite

- [ ] Antes do backfill, o card antigo aparece com aviso.
- [ ] Durante o backfill, a oportunidade não desaparece nem duplica.
- [ ] Depois do backfill, o aviso some e o novo resultado aparece.
- [ ] Alterar modalidade aceita de `REMOTE` para `ONSITE` muda o verdict da fixture.
- [ ] O estado é compreensível por leitor de tela.

## Verificação

Demonstrar os três estados com relógio e respostas controladas, incluindo atualização da
query sem recarregar manualmente a página.

## Arquivos prováveis

- `apps/web/src/routes/InboxPage.tsx`
- `apps/web/src/routes/OpportunityDetailPage.tsx`
- `apps/web/src/features/dashboard/`
- `apps/web/src/features/matching/`
