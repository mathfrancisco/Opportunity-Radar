# WP1 — spike de primitives da SPEC 54

**Estado:** evidência local e descartável; não é implementação do produto, nem
aceite visual, nem seleção final de um kit completo.

## Escopo executado

O experimento original viveu somente no worktree descartável
`.worktrees/f54-primitives`, branch `spike/f54-primitives-20261007`, criado no
commit `e84be68`. Ele adicionou a rota isolada `/__f54-primitives`, sem chamadas
de API, banco ou alteração de CSS de produção. A rota exercitou wrappers locais
de `Button`, `Field`, `Dropdown`, `Dialog` e `Table` em `components/ui`.

Os wrappers eram uma **prova de viabilidade Radix com estilo local inspirado na
arquitetura shadcn**, escritos manualmente. Nenhum arquivo de registry shadcn,
CLI ou `components.json` foi copiado/gerado; isso não valida proveniência shadcn
nem uma versão de registry para integração futura.

## Baseline histórico e comparação

| Medida | Base `e84be68` | Primeiro spike Radix | Delta |
| --- | ---: | ---: | ---: |
| módulos Vite | 133 | 207 | +74 |
| CSS gzip | 6,65 kB | 7,24 kB | +0,59 kB |
| JS inicial gzip | 149,01 kB | 179,77 kB | +30,76 kB / **20,64%** |
| testes | 42 arquivos / 292 testes | 43 / 294 | +1 / +2 |

Essa primeira medição incluiu Dialog, Dropdown e Slot e excedeu o orçamento
AC54-09 de 10%; permanece como fato histórico, não como a medida do recorte
aprovado abaixo. React Aria Components 1.21.1 e MUI Material 9.4.0 foram apenas
pesquisados por metadados, sem instalação, árvore, medição de bundle ou teste de
teclado. A compatibilidade Radix então observada foi no app React 19 / Vite 8 /
Tailwind 4 existente, usando somente classes Tailwind nos wrappers.

## Verificações e limites preservados

- Vitest do spike exercitou label de campo, `caption` de tabela, ArrowDown,
  Escape e retorno de foco do diálogo ao gatilho.
- O smoke Playwright em `127.0.0.1:4173/__f54-primitives` bloqueou qualquer
  origem diferente de `http://127.0.0.1:4173` e todo caminho `/api` antes de
  navegar; a execução persistida registrou `apiRequests: []`, Tab, Shift+Tab,
  Escape e retorno de foco.
- Revisão manual por leitor de tela, contraste final, zoom, mobile e aprovação
  visual continuam pendentes; o browser check não prova esses pontos.
- `npm audit --omit=dev --json` registrou zero vulnerabilidades de produção
  após instalar Radix. O audit completo manteve um aviso alto do baseline, fora
  do escopo, e houve aviso de engine de `jsdom@30.0.1` com Node 24.12.0.

Uma segunda tentativa descartável com Base UI 1.8.0 teve testes unitários, mas
falhou em Shift+Tab no smoke real; o check completo também teria falhado porque
ESLint percorreu `node_modules.radix-archived`, e a limpeza parcial foi bloqueada
por binário no Windows. Não há log literal completo desse relato. As fontes,
manifestos, teste e runner estão em
`artifacts/base-ui-source.patch`: é referência de revisão, sem dependências,
binários ou worktree, e não deve ser publicada/reparada nem receber uma terceira
tentativa automática.

## Decisão aprovada para WP3B

O produto adota somente `@radix-ui/react-dialog@1.2.0`, por meio de um wrapper
local em `apps/web/src/components/ui/`, para a gaveta de navegação móvel. Não
há menu, popover, combobox ou tabs no app que justifiquem outro primitive.

| Candidato | Delta JS gzip sobre 149,01 kB | Resultado |
| --- | ---: | --- |
| Radix Dialog 1.2.0 | +12,61 kB / **+8,54%** | aprovado; dentro do orçamento de +10% |
| Base UI | +13,35% | reprovado; Shift+Tab falhou |
| React Aria | +16,73% | fora do orçamento |
| MUI | +24,13% | fora do orçamento |

Restam aproximadamente 2,2 kB antes do limite de +10%, mas esse espaço não
autoriza adicionar outro primitive Radix sem nova medição comparável. Caso o
total futuro exceda +10%, o Dialog da gaveta deve ser carregado sob demanda.

## Limites da decisão

Esta decisão seleciona apenas o Dialog e não aprova uma distribuição shadcn,
outros primitives, rotas, estilos globais ou a SPEC 54 como um todo. A
evidência de bundle é específica à medição final acima; mudanças posteriores
exigem nova validação proporcional.
