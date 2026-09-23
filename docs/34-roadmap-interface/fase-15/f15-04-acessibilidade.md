# CARD F15-04 — Acessibilidade e navegação por teclado

- **Status:** Concluído em 2026-09-22
- **Fase:** 15 — Design, consistência e acesso
- **Depende de:** F15-02
- **Bloqueia:** Milestone N
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §4

## Resultado

Toda a interface é operável por teclado, com foco visível, rótulos associados e erro de
formulário vinculado ao campo que o causou.

## Contexto

O básico já aparece em pontos isolados: `InboxPage` e `CompaniesPage` usam `sr-only` nos
campos de busca, algumas regiões têm `aria-live`, e `.retry-button` declara
`:focus-visible`. É pontual. Fora desses casos, o foco herda o padrão do navegador sobre
fundos de baixo contraste, tabelas densas não têm cabeçalho associado, e os formulários que
a Fase 14 vai acrescentar não têm nenhum padrão de erro para seguir.

## Escopo

- Foco visível em todo elemento interativo, com contraste suficiente sobre cada superfície.
- Rótulo associado a todo campo, e erro vinculado por `aria-describedby` com
  `aria-invalid`.
- Cabeçalho de tabela associado às células, e legenda onde a tabela precisa de contexto.
- Link para pular ao conteúdo e `aria-current` na navegação do `PageShell`.
- Ordem de tabulação previsível em cada rota, sem armadilha de foco.

## Fora de escopo

- Auditoria formal WCAG ou certificação.
- Leitura de gráfico complexo, que a interface ainda não tem.
- Internacionalização.

## Notas de implementação

O alvo é AA, verificável. Cada critério precisa de uma checagem repetível: contraste medido
por par de tokens, foco conferido por rota, erro de formulário coberto por teste. Uma regra
que só existe como intenção não sobrevive à próxima tela.

## Critérios de aceite

- [x] Todo elemento interativo tem foco visível com contraste AA.
- [x] Todo campo tem rótulo associado e, em erro, `aria-invalid` e descrição vinculada.
- [x] Tabelas associam cabeçalho às células.
- [x] Existe link para pular ao conteúdo e a rota ativa é anunciada.
- [x] As nove rotas são percorríveis só com teclado, incluindo executar uma fonte e
      submeter um formulário.
- [x] Nenhuma informação é transmitida apenas por cor.

## Verificação

Percurso por teclado documentado por rota; verificação automática de acessibilidade nos
testes de componente; tabela de contraste conferida contra os tokens da F15-01.

## Nota de execução

O anel de foco usa `ink`, não `accent`. O verde-limão sobre superfície clara fica em torno
de 1.2:1 — visível para quem já sabe onde procurar, invisível para quem depende dele. Sobre
o botão primário, que é escuro, o anel inverte para `accent` pelo mesmo critério: o
contorno contrasta com o que está atrás dele.

O erro de campo virou mecanismo antes de virar uso: `Field` liga o texto ao controle por
`aria-describedby` e marca `aria-invalid`. Hoje nenhuma tela tem erro por campo — os
formulários da Fase 14 é que vão tê-los, e vão encontrar o padrão pronto em vez de
inventar o seu.


## Arquivos prováveis

- `apps/web/src/components/PageShell.tsx`
- `apps/web/src/components/`
- `apps/web/src/routes/`
- `apps/web/src/styles.css`
