# CARD F15-05 — Responsividade e densidade

- **Status:** Concluído em 2026-09-22
- **Fase:** 15 — Design, consistência e acesso
- **Depende de:** F15-02
- **Bloqueia:** Milestone N
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §4

## Resultado

Nenhuma tela provoca rolagem horizontal da página, e as tabelas densas continuam legíveis
em tela estreita sem esconder coluna que decide algo.

## Contexto

As telas foram desenhadas para tela larga. A métrica por fonte introduzida na Fase 13 tem
seis colunas, a de execuções tem cinco, e a de senioridade carrega contagem, percentual e
procedência na mesma célula. Em tela estreita, isso hoje empurra a página inteira para o
lado — e a rolagem horizontal do documento é a forma mais rápida de perder a primeira
coluna, que é justamente o nome da fonte.

## Escopo

- Conter toda tabela larga em contêiner com rolagem própria, mantendo a primeira coluna
  visível.
- Definir o comportamento em tela estreita para as tabelas de métricas, execuções e
  candidaturas: rolagem no contêiner ou lista de cartões, decidido por tabela.
- Revisar densidade: espaçamento, tamanho mínimo de alvo de toque e quebra de texto longo
  como URL de vaga.
- Garantir que nenhuma coluna que sustente uma decisão seja escondida sem alternativa de
  leitura.

## Fora de escopo

- Aplicativo móvel ou layout dedicado a telefone.
- Reordenar colunas por preferência do operador.
- Gráficos.

## Notas de implementação

Esconder coluna em tela estreita é tentador e perigoso: a coluna de cobertura é o que separa
"não executou" de "sem vagas", e some junto com a distinção. Quando o espaço não couber, a
resposta é cartão com todos os campos, não tabela truncada.

## Critérios de aceite

- [x] Nenhuma rota rola horizontalmente no documento em largura de 360 px.
- [x] Tabelas largas rolam dentro do próprio contêiner.
- [x] Nenhuma coluna necessária a uma decisão é omitida sem equivalente visível.
- [x] Alvos de toque respeitam o mínimo definido pelos tokens.
- [x] URL e texto longo quebram sem estourar o contêiner.

## Verificação

Percorrer as nove rotas em 360 px, 768 px e 1280 px conferindo a rolagem do documento;
revisar cada tabela contra a lista de colunas que sustentam decisão.

## Nota de execução

A primeira coluna das tabelas densas fica fixa em vez de rolar junto: seis números sem o
nome da fonte ao lado não pertencem a ninguém. A tabela de empresas manteve a estratégia
que já tinha — tabela em tela larga, cartões em tela estreita —, que é exatamente a
alternativa que este card pede quando a linha não cabe.

Nenhuma coluna foi escondida. A de cobertura é a que separa "não executou" de "sem vagas",
e some junto com a distinção se a resposta ao aperto for esconder coluna.


## Arquivos prováveis

- `apps/web/src/routes/OverviewPage.tsx`
- `apps/web/src/routes/SourcesPage.tsx`
- `apps/web/src/routes/PipelinePage.tsx`
- `apps/web/src/components/`
