# CARD F15-06 — Escala tipográfica, espaçamento e elevação

- **Status:** Backlog
- **Fase:** 15 — Design, consistência e acesso
- **Depende de:** F15-01
- **Bloqueia:** F15-07
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §4

## Resultado

Tamanho de texto, entrelinha, espaçamento entre blocos, raio e sombra saem de uma escala
declarada, como a cor já sai desde F15-01.

## Contexto

A cor foi nomeada; a forma não. O que restou é escolhido por tela:

```text
tracking-[-0.04em]  PageShell         tracking-[-0.03em]  Overview, Inbox, detalhe
tracking-[0.08em]   quatro arquivos   rounded-[2rem]      PageShell
shadow-[0_24px_70px_rgba(23,50,45,0.10)]                  PageShell
```

O `rgba` daquela sombra escapa do lint de literal hexadecimal — é a última cor crua da
interface. Os tamanhos seguem o mesmo padrão: `text-5xl` no título, `text-3xl` no número do
tile, `text-lg` na seção, `text-sm` e `text-xs` no resto, sem relação declarada entre eles.
O mesmo vale para o vertical: `mt-1`, `mt-2`, `mt-3`, `mt-4`, `mt-6`, `mt-8` e `mt-10`
aparecem lado a lado, e a distância entre dois blocos depende de quem escreveu a tela.

## Escopo

- Declarar a escala de texto em `@theme`: papel, tamanho, entrelinha e `letter-spacing`
  juntos, para display, título, seção, corpo, apoio e legenda.
- Declarar os degraus de espaçamento vertical usados entre blocos, e aplicá-los.
- Declarar raio e elevação como tokens, incluindo a sombra do `PageShell`.
- Substituir todo valor arbitrário de `tracking`, `rounded` e `shadow` pelos tokens.
- Estender o lint para recusar `rgba(` e `#` dentro de valor arbitrário de classe.

## Fora de escopo

- Trocar a família tipográfica ou carregar fonte externa.
- Redesenhar telas: a escala descreve o que já existe, e só corrige o que destoa.
- Animação e transição, que são de outro card.

## Notas de implementação

A escala nasce do uso atual, não de uma régua ideal: medir os tamanhos em tela, agrupar os
próximos e escolher um degrau por grupo. Um degrau que não tem uso não entra. Onde dois
tamanhos vizinhos hoje diferem sem motivo, o card registra qual venceu.

## Critérios de aceite

- [ ] Nenhum valor arbitrário de `tracking`, `rounded` ou `shadow` permanece em rotas e
      componentes.
- [ ] Nenhuma cor crua resta em sombra ou em qualquer outro valor arbitrário.
- [ ] Todo degrau de texto declarado tem pelo menos um uso.
- [ ] Título, seção, corpo e legenda usam sempre o mesmo degrau em todas as telas.
- [ ] O lint recusa `rgba(` e `#` em valor arbitrário de classe.

## Verificação

Busca por `tracking-[`, `rounded-[`, `shadow-[` e `rgba(` em `apps/web/src` como passo do
lint; revisão das nove rotas comparando o degrau usado por papel.

## Arquivos prováveis

- `apps/web/src/styles.css`
- `apps/web/src/components/`
- `apps/web/src/routes/`
- `apps/web/eslint.config.js`
- `docs/35-design-tokens.md`
