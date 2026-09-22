# CARD F15-02 — Componentes compartilhados

- **Status:** Backlog
- **Fase:** 15 — Design, consistência e acesso
- **Depende de:** F15-01
- **Bloqueia:** F15-03, F15-04, F15-05
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §4

## Resultado

Botão, badge de status, cartão, tabela e campo de formulário existem uma vez, e cada tela
os usa em vez de recriá-los.

## Contexto

`apps/web/src/components/` tem apenas `PageShell` e `ApplicationPanel`. O resto vive
duplicado: o mapa de tom por status aparece em `SourcesPage.tsx` e de novo em
`OverviewPage.tsx`, com rótulos diferentes para o mesmo estado; classes de botão primário
são recopiadas em cada rota. Duas cópias do mesmo conceito divergem, e a divergência aparece
para o operador como duas linguagens na mesma interface.

## Escopo

- Extrair `Button`, `StatusBadge`, `Card`, `DataTable`, `Field` e `Toolbar` a partir do uso
  já existente.
- Centralizar o mapa de estado para execução de fonte e cobertura, com rótulo e tom únicos.
- Migrar as nove rotas para os componentes, sem alterar o que cada tela informa.
- Deixar os componentes sem conhecimento de domínio: eles recebem estado, não o inferem.

## Fora de escopo

- Criar componente que ainda não tem dois usos reais.
- Mudar a informação exibida, a ordem das colunas ou os filtros de cada tela.
- Storybook ou catálogo visual dedicado.

## Notas de implementação

`StatusBadge` é o caso mais sensível: hoje há duas tabelas de tradução para os mesmos
estados, e os nomes de cobertura da Fase 13 — `NOT_ENABLED`, `CONFIGURATION_BLOCKED`,
`NOT_SCHEDULED`, `NOT_RUN`, `SUCCEEDED_ZERO` — precisam continuar distinguíveis depois da
unificação. Um estado sem tradução mostra o próprio código, nunca um rótulo genérico.

## Critérios de aceite

- [ ] Cada componente extraído tem ao menos dois usos em rotas distintas.
- [ ] Existe um único mapa de rótulo e tom por estado de execução e de cobertura.
- [ ] Nenhuma rota declara classe de botão primário por conta própria.
- [ ] Estado desconhecido é exibido pelo próprio código, sem virar "indefinido".
- [ ] As telas informam exatamente o que informavam antes da migração.

## Verificação

Teste de unidade por componente cobrindo variantes e estado desconhecido; revisão das nove
rotas contra capturas anteriores; busca por classes duplicadas de botão como parte da
revisão.

## Arquivos prováveis

- `apps/web/src/components/`
- `apps/web/src/routes/`
- `apps/web/src/components/*.test.tsx`
