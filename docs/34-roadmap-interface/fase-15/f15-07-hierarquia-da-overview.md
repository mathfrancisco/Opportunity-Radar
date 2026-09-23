# CARD F15-07 — Hierarquia da Visão geral

- **Status:** Concluído em 2026-09-22
- **Fase:** 15 — Design, consistência e acesso
- **Depende de:** F15-06
- **Bloqueia:** Milestone N
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §4

## Resultado

A Visão geral responde, na ordem em que se lê: o que exige ação hoje, o que o radar
encontrou, e como a operação está passando.

## Contexto

A tela cresceu por adição. Hoje ela abre com oito tiles de peso visual idêntico, segue com
as pílulas de verdict, depois as fontes em falha, e termina com uma tabela de seis colunas
por fonte. "Candidaturas ativas" e "Itens brutos pendentes" recebem o mesmo destaque que
"Alta prioridade", embora só um deles peça uma decisão hoje.

O resultado é uma tela densa e plana: tudo está lá, nada se destaca, e o operador precisa
reler a página inteira para descobrir se precisa fazer algo. Uma tela de visão geral que
exige leitura completa não está resumindo nada.

## Escopo

- Agrupar o conteúdo em três blocos declarados: decisão pendente, acervo, operação.
- Dar peso visual diferente ao primeiro bloco, e reduzir o dos demais.
- Rever a granularidade dos tiles: métrica que ninguém aciona vira linha de apoio, não
  cartão.
- Levar a tabela de métricas por fonte para o fim, sob o bloco de operação, com um resumo
  acima dela — quantas fontes saudáveis, degradadas, sem execução.
- Manter cada número clicável para o mesmo lugar para onde ele já leva hoje.

## Fora de escopo

- Criar métrica nova ou mudar o cálculo de qualquer uma.
- Esconder informação atrás de aba, acordeão ou filtro por padrão.
- Gráficos.

## Notas de implementação

Nada some: o que sai do destaque continua na página, um degrau abaixo. Reduzir peso é
diferente de esconder, e a distinção importa porque cada número aqui tem alguém que o
procura — inclusive os que raramente mudam.

A ordem dos blocos é a pergunta que a tela responde primeiro. Se a resposta for "nada
pendente", a tela precisa deixar isso óbvio sem obrigar a leitura do resto.

## Critérios de aceite

- [x] A tela apresenta três blocos nomeados, na ordem decisão, acervo, operação.
- [x] O bloco de decisão é visualmente dominante e cabe na primeira dobra em 1280 px.
- [x] Nenhum número deixou de existir ou de levar ao mesmo destino de antes.
- [x] Um estado sem pendência é legível sem ler a página inteira.
- [x] O resumo de saúde por fonte antecede a tabela e concorda com ela.

## Nota de execução

Nenhum número saiu da tela. Os que não pedem ação deixaram de ser cartão e viraram linha
de apoio, com os mesmos destinos: "Avaliadas" continua levando à Inbox filtrada,
"Candidaturas ativas" continua levando ao pipeline. O follow-up devido, que antes era dica
dentro do cartão de candidaturas, virou cartão no bloco de decisão — era a única pendência
com prazo escondida numa nota de rodapé.

O resumo de cobertura é derivado das mesmas linhas que a tabela exibe, e não de uma segunda
consulta. Um resumo que pode discordar da tabela logo abaixo dele é pior que nenhum.

## Verificação

Comparar a lista de números e destinos antes e depois, item a item; percorrer a tela em
1280 px e 360 px confirmando a ordem dos blocos; conferir o resumo contra os estados de
cobertura da tabela.

## Arquivos prováveis

- `apps/web/src/routes/OverviewPage.tsx`
- `apps/web/src/components/`
- `apps/web/src/features/dashboard/api.ts`
