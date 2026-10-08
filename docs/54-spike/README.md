# WP1 — spike de primitives da SPEC 54

**Estado:** evidência local e descartável; não é implementação do produto, nem
aceite visual, nem seleção final.

## Escopo executado

O experimento vive somente no worktree descartável
`.worktrees/f54-primitives`, branch `spike/f54-primitives-20261007`, criado no
commit `e84be68`. Ele adiciona a rota isolada `/__f54-primitives`, sem chamadas
de API, banco ou alteração de CSS de produção. A rota exercita wrappers locais
de `Button`, `Field`, `Dropdown`, `Dialog` e `Table` em `components/ui`.

Os wrappers são uma **prova de viabilidade Radix com estilo local inspirado na
arquitetura shadcn**, escritos manualmente. Nenhum arquivo de registry shadcn,
CLI ou `components.json` foi copiado/gerado. Portanto, isto não valida uma
proveniência shadcn ou uma versão de registry para integração futura.

## Baseline e resultado mensurado

| Medida | Base `e84be68` | Spike Radix | Delta |
| --- | ---: | ---: | ---: |
| módulos Vite | 133 | 207 | +74 |
| CSS gzip | 6.65 kB | 7.24 kB | +0.59 kB |
| JS inicial gzip | 149.01 kB | 179.77 kB | +30.76 kB / **20.64%** |
| testes | 42 arquivos / 292 testes | 43 / 294 | +1 / +2 |

O aumento de JS excede o orçamento AC54-09 de 10%. Como a rota foi incluída no
bundle inicial apenas para medir o custo total, ela não mascara o custo por lazy
loading. A spike não libera merge nem escolhe Radix/shadcn; qualquer adoção
futura precisa reduzir/justificar esse delta e repetir a medida no conjunto de
rotas aprovado.

## Comparação de candidatos

| Candidato | Versão consultada | Licença | peer React 19 | Evidência de execução |
| --- | --- | --- | --- | --- |
| Radix Dialog + Dropdown + Slot | 1.2.0 / 2.1.25 / 1.4.0 | MIT | `^19.0` aceito | instalada com versões exatas, typecheck/build/test e smoke Playwright |
| React Aria Components | 1.21.1 | Apache-2.0 | `^19.0.0-rc.1` aceito | apenas metadados e documentação Context7 |
| MUI Material | 9.4.0 | MIT | `^19.0.0` aceito | apenas metadados e documentação Context7; declara `@emotion/react`, `@emotion/styled` e `@mui/material-pigment-css` como peers |

As versões, licenças e peers vêm de `npm view` em 2026-10-07. A compatibilidade
Radix foi provada no app React 19 / Vite 8 / Tailwind 4 existente; Tailwind foi
usado somente para classes dos wrappers, sem alterar `styles.css`. React Aria e
MUI não receberam instalação, árvore, medição de bundle ou teste de teclado, e
não podem ser considerados comparados de forma completa.

## Acessibilidade e isolamento verificados

- Vitest exercitou label de campo, tabela com `caption`, abertura por ArrowDown,
  Escape e retorno de foco do diálogo ao gatilho.
- Smoke Playwright em `127.0.0.1:4173/__f54-primitives` confirmou
  `returnedFocus: "Abrir confirmação"`, abriu o menu por teclado e bloqueou toda
  chamada `/api`; o resultado foi `apiRequests: []`.
- O browser check é de teclado e DOM. Revisão manual por leitor de tela,
  contraste final, zoom, mobile e aprovação visual continuam pendentes.

## Dependências e segurança

A árvore local direta está em [artifacts/dependency-tree.txt](artifacts/dependency-tree.txt).
`npm audit --omit=dev --json` retornou 0 vulnerabilidades de produção após a
instalação Radix. O `npm ci` do baseline e o install avisaram uma vulnerabilidade
alta no audit completo, que não foi corrigida por estar fora da spike; esta não
aparece no audit de produção. Houve também aviso de engine de `jsdom@30.0.1`
com Node 24.12.0, já presente no baseline.

## Próxima decisão

Manter a escolha em aberto. Antes de WP1 ser aceita, registrar proveniência
shadcn (registry/revisão e licenças dos arquivos copiados) se essa distribuição
for escolhida, medir alternativas executáveis quando necessário e cumprir o
orçamento de bundle. F53 e os três protótipos visuais continuam gates pendentes
da SPEC 54.

## Correção do smoke de rede

O smoke inicial foi reforçado antes da segunda comparação: **antes de navegar**,
o Playwright agora aborta qualquer origem diferente de
`http://127.0.0.1:4173` e qualquer caminho `/api`. Ele também falha se houver
uma tentativa bloqueada. A execução literal persistida confirma zero tentativas,
Tab e Shift+Tab dentro do diálogo, Escape e retorno de foco tanto no diálogo
quanto no menu. O servidor local não abriu a visão geral nem qualquer rota de
domínio.

Enquanto a spike estava em andamento, `main` avançou externamente para
`b6d25ae`; não há mudança de frontend dessa revisão no worktree baseado em
`e84be68`. Os únicos arquivos deliberadamente criados em `main` por esta spike
são os desta pasta `docs/54-spike`.

## Segundo spike: Base UI (resultado nao aprovado)

Uma tentativa adicional usou Base UI 1.8.0 em worktree descartavel baseada em `e84be68`. Rota, botao nativo, tabela, campo, dialogo e menu foram exercitados; testes unitarios passaram. No smoke real, Tab, Escape, foco restaurado e bloqueio de rede passaram, mas **Shift+Tab dentro do dialogo falhou**. O check completo tambem falhou: ESLint percorreu `node_modules.radix-archived` dentro do app. A limpeza ficou parcial por bloqueio de binario no Windows. Nao considerar o candidato aprovado nem o check completo verde.

Fontes, manifestos, teste e smoke estao preservados em `artifacts/base-ui-source.patch`. E arquivo de referencia para revisao, nao pacote pronto para aplicar sobre `main`; nao inclui dependencias, binarios ou worktree. Nao houve terceira comparacao nem selecao de kit. Radix cresceu 20,64% (+30,76 kB gzip de JS inicial), acima do orcamento maximo de +10%; Base UI tem falha de teclado; React Aria e MUI foram pesquisados somente por metadados. A decisao permanece aberta.