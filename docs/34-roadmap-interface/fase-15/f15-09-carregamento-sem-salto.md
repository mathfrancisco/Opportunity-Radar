# CARD F15-09 — Carregamento sem salto de layout

- **Status:** Backlog
- **Fase:** 15 — Design, consistência e acesso
- **Depende de:** F15-03, F15-06
- **Bloqueia:** Milestone N
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §4

## Resultado

Enquanto os dados chegam, a tela mostra a forma do que vai chegar, no lugar onde vai
chegar, e não se rearranja quando chega.

## Contexto

`LoadingState` unificou o carregamento em uma faixa de texto — "Carregando fontes…" — que
ocupa cinco linhas e some para dar lugar a uma lista de vários cartões. A página inteira
pula quando o dado chega, e em cada tela ela pula de um jeito diferente, porque a altura do
conteúdo final não tem relação com a altura da faixa.

O problema é maior nas telas que carregam em partes. A Visão geral tem duas consultas
independentes: o resumo e as métricas por fonte. Quem chega primeiro empurra o que chega
depois.

## Escopo

- Componente de esqueleto que reproduz a forma do conteúdo: cartão, linha de tabela e tile.
- Substituir a faixa de texto pelo esqueleto nas listas e tabelas, mantendo `LoadingState`
  onde o conteúdo é um bloco curto.
- Reservar a altura do conteúdo que ainda não chegou, para que a primeira consulta a
  responder não desloque a segunda.
- Manter o anúncio em `role="status"`: o esqueleto é visual, e quem usa leitor de tela
  continua ouvindo que a tela está carregando.
- Respeitar `prefers-reduced-motion` em qualquer pulsação do esqueleto.

## Fora de escopo

- Spinner global ou barra de progresso no topo.
- Mudar política de cache ou de refetch.
- Carregamento otimista de dados que a API ainda não devolveu.

## Notas de implementação

Esqueleto que não tem a forma do conteúdo é pior que faixa de texto: promete uma coisa e
entrega outra. Cada esqueleto nasce do componente que ele substitui, e some no mesmo lugar
em que o conteúdo aparece.

Anúncio é uma vez só. Um esqueleto por cartão com `role="status"` em cada um faria o leitor
de tela repetir "carregando" dez vezes.

## Critérios de aceite

- [ ] Listas e tabelas carregam com esqueleto na forma do conteúdo.
- [ ] A posição vertical dos blocos não muda entre carregando e carregado.
- [ ] O estado de carregamento é anunciado uma vez por região, não por item.
- [ ] Com `prefers-reduced-motion`, o esqueleto não pulsa.
- [ ] Bloco curto continua usando `LoadingState`, sem esqueleto inventado.

## Verificação

Carregar cada tela com a rede limitada e conferir que nada se desloca ao chegar o dado;
percorrer com leitor de tela confirmando um anúncio por região; repetir com movimento
reduzido ativado.

## Arquivos prováveis

- `apps/web/src/components/states.tsx`
- `apps/web/src/components/`
- `apps/web/src/routes/`
- `apps/web/src/styles.css`
