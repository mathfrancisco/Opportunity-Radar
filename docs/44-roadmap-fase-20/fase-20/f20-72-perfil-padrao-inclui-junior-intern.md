# CARD F20-72 — Perfil padrão e UI não devem esconder JUNIOR/INTERN silenciosamente no matching

- **Status:** Backlog.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** Nenhum
- **Origem:** diagnóstico "por que a busca traz tão poucas vagas junior/estágio",
  registrado em
  [`docs/44-roadmap-fase-20/evidencias/diagnostico-vagas-junior-2026-09-28.md`](../evidencias/diagnostico-vagas-junior-2026-09-28.md)
  (2026-09-28), seção 3.5.

## Contexto

`_seniority_filter` (`src/opportunity_radar/matching/domain.py:423-435`): quando uma
vaga tem `seniority` JUNIOR/INTERN e o perfil do usuário não inclui essas senioridades
em `profile.accepted_seniorities`, a vaga é marcada `INELIGIBLE` e não aparece na tela
de matches. Isso é comportamento correto e esperado quando o usuário de fato não quer
esse nível — não é bug de coleta. A busca geral (`dashboard/search_filters.py:41-42`)
não tem esse comportamento: só filtra por senioridade se o usuário pedir
explicitamente, então a busca "crua" não escondia nada por padrão nesta auditoria.

O risco identificado é de UX/onboarding: se o fluxo de criação/edição de perfil não
deixa claro que `accepted_seniorities` vazio ou sem JUNIOR/INTERN marcado esconde essas
vagas do matching, o usuário pode nunca perceber por que não vê vagas junior/estágio
mesmo quando existem no catálogo (F20-71 pode aumentar essa contagem). Este card não
tem número de impacto medido — o diagnóstico de origem não avaliou perfis de usuário
reais.

## Escopo

1. Levantar (sem PII, sem exportar dado pessoal) como a UI de perfil hoje comunica
   `accepted_seniorities` — se há algum estado "nenhuma senioridade marcada" e o que
   ele significa hoje no filtro (bloqueia tudo? aceita tudo?).
2. Se `accepted_seniorities` vazio hoje é tratado como "aceita nada" (bloqueia tudo),
   avaliar mudar para "aceita qualquer" — mesma decisão de design já usada para
   UNKNOWN (`_seniority_filter` retorna UNKNOWN, não bloqueia, quando a vaga não tem
   senioridade decidida; um perfil sem preferência declarada deveria ter o mesmo
   tratamento permissivo, não restritivo).
3. Se a UI já deixa isso claro (ex.: checkbox visível, default "todos marcados"),
   fechar este card documentando a evidência, sem mudança de código.

## Fora de escopo

- Mudar `_seniority_filter` para tratar JUNIOR/INTERN como caso especial diferente de
  outras senioridades — o filtro deve continuar simétrico entre todos os valores do
  enum.
- Qualquer mudança em `search_filters.py` (busca geral) — já não filtra por padrão,
  confirmado no diagnóstico de origem.

## Critérios de aceite

- [ ] Comportamento de `accepted_seniorities` vazio documentado com evidência de teste
      (comportamento atual: bloqueia ou aceita?).
- [ ] Se o comportamento atual bloqueia tudo com perfil vazio, corrigido para aceitar
      tudo (simetria com o tratamento de UNKNOWN), com teste de regressão.
- [ ] Se a UI já comunica isso claramente, card fechado com evidência (screenshot ou
      trecho de componente), sem mudança de código.

## Não fazer

- Não adicionar lógica que force JUNIOR/INTERN a aparecer mesmo quando o perfil pede
  explicitamente para excluí-los — isso violaria a preferência do usuário.

## Verificação

- **CI:** suíte de testes de `matching/domain.py` e do componente de perfil relevante.

## Pronto quando

O comportamento de perfil vazio/sem preferência de senioridade estiver documentado e,
se necessário, corrigido para não esconder JUNIOR/INTERN por omissão.
