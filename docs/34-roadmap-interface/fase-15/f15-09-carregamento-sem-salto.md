# CARD F15-09 — Carregamento sem salto de layout

- **Status:** Concluído em 2026-09-23
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

- [x] Listas e tabelas carregam com esqueleto na forma do conteúdo.
- [x] A posição vertical dos blocos não muda entre carregando e carregado.
- [x] O estado de carregamento é anunciado uma vez por região, não por item.
- [x] Com `prefers-reduced-motion`, o esqueleto não pulsa.
- [x] Bloco curto continua usando `LoadingState`, sem esqueleto inventado.

## Nota de execução

`components/skeletons.tsx` tem o invólucro `Skeleton` — um `role="status"` com
`aria-busy` e o mesmo texto que a faixa dizia, e a forma inteira sob `aria-hidden` — e as
formas que nasceram das telas: lista de cartões, tabela, painel de três colunas. A
pulsação é `motion-safe:animate-pulse`; com movimento reduzido a forma fica e o pulso some.

Onde entrou esqueleto: Oportunidades e Fontes (lista de cartões), Empresas (tabela em tela
larga, cartões na estreita, a mesma troca da lista real), Candidaturas (três colunas de
estágio), e na Visão geral o resumo — os três blocos com os títulos reais — e a tabela de
métricas por fonte. A faixa de cobertura de Fontes é uma consulta própria e ganhou espaço
reservado, para que a que responde por último não empurre a outra. Os botões de janela das
métricas também: a linha do título reserva a altura deles antes de existirem.

Onde `LoadingState` ficou: detalhe de oportunidade, detalhe de empresa, perfil, avaliação e
painel de candidatura. São um registro só, e a faixa já tem mais ou menos a altura dele.

Medido na Visão geral com a resposta retida e depois liberada, pela posição de cada bloco:
o deslocamento ficou em 4 px em 1280 px, 6 px em 768 px e 13 px em 360 px, onde antes a
página inteira trocava uma faixa de cinco linhas pelo resumo. O resto é texto de tamanho
variável — quantas pílulas de veredito existem, se a dica quebra linha —, que o esqueleto
não tem como saber antes do dado.

## Verificação

Carregar cada tela com a rede limitada e conferir que nada se desloca ao chegar o dado;
percorrer com leitor de tela confirmando um anúncio por região; repetir com movimento
reduzido ativado.

## Arquivos prováveis

- `apps/web/src/components/states.tsx`
- `apps/web/src/components/`
- `apps/web/src/routes/`
- `apps/web/src/styles.css`
