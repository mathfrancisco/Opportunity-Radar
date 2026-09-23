# CARD F15-01 — Tokens de design e tema

- **Status:** Concluído em 2026-09-22
- **Fase:** 15 — Design, consistência e acesso
- **Depende de:** Nenhum
- **Bloqueia:** F15-02
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §4

## Resultado

Cor, tipografia, espaçamento e raio vêm de tokens nomeados, e nenhuma rota escreve um valor
hexadecimal literal.

## Contexto

A interface usa Tailwind 4 sem tema declarado. Cores como `#17322d`, `#6d827b`, `#dce4dc`,
`#9b3e2e` e `#eef3df` aparecem dezenas de vezes espalhadas por `apps/web/src/routes/` e
`apps/web/src/components/`. Isso impede duas coisas: revisar contraste, porque não há par
cor/uso nomeado, e mudar um tom, porque a mudança é uma busca textual pelo repositório.

## Escopo

- Declarar tokens em `@theme`: superfícies, texto, borda, acento, e os tons semânticos de
  sucesso, atenção, erro e neutro.
- Nomear pelo papel, não pelo tom: `surface`, `surface-muted`, `text-subtle`,
  `border-subtle`, `accent`, `danger`.
- Substituir todos os literais das rotas e componentes pelos tokens equivalentes.
- Documentar em `docs/` o par token/uso e o contraste medido de cada combinação de texto
  sobre fundo.

## Fora de escopo

- Tema escuro, que está no recorte explícito do roadmap.
- Redesenhar telas, alterar layout ou trocar a paleta.
- Introduzir biblioteca de componentes de terceiros.

## Notas de implementação

A substituição é mecânica e precisa ser verificável: um literal que sobra é um token que não
existe. A troca deve preservar o resultado visual atual, exceto onde um par reprovar no
contraste — nesse caso, o ajuste é registrado no card com o valor antigo e o novo.

## Critérios de aceite

- [x] Nenhum literal hexadecimal permanece em `apps/web/src/routes/` e
      `apps/web/src/components/`.
- [x] Todo token declarado é usado ao menos uma vez.
- [x] Texto sobre fundo atinge contraste AA em todas as combinações documentadas.
- [x] A aparência das telas permanece equivalente, salvo os ajustes de contraste
      registrados.
- [x] A verificação de literais roda no pipeline.

## Verificação

Busca por `#` seguido de seis dígitos hexadecimais em `apps/web/src` como passo do lint;
tabela de contraste conferida por par; revisão visual das nove rotas antes e depois.

## Arquivos prováveis

- `apps/web/src/styles.css`
- `apps/web/src/routes/`
- `apps/web/src/components/`
- `apps/web/eslint.config.js`
- `docs/`
