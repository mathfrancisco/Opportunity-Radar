# F51-11 — amostra nova, sorteada onde cada regra emite

Data: 2026-10-06. Card: F51-11. Preparação para o dono rotular; nada aqui libera regra.

## Por que existe

O gold confirmado (368 vagas) dá de 0 a 8 emissões por regra de descrição contra um mínimo
de 20, 12 casos `unknown` e 18 vagas no Remotive. Nenhuma regra passa nem falha com
evidência. A amostra antiga foi sorteada sem olhar as regras e cortou a descrição em 1.200
caracteres, que quase nunca chegam onde a regra emite. Esta amostra sorteia só entre vagas em
que a regra emite, com a descrição inteira.

## O que foi gerado (arquivos novos, nada existente foi editado)

- `scripts/sample_rule_support.py`: sorteio, só leitura. Teste em
  `tests/backend/test_sample_rule_support.py` (seis testes: mesma semente, mesma escolha;
  vagas do gold existente excluídas; teto por regra; resumo de suporte; entrada com descrição
  inteira e sem rótulo; detecção de emissão).
- `docs/pesquisas/f50-01-amostra-para-rotular-suporte-2026-10-06.json`: 176 entradas, uma por
  vaga e regra, com a descrição inteira, título, empresa, local, tipo de fonte, a regra que
  selecionou (`regra_selecao`) e o valor que ela emitiu (`regra_valor`). `judgment`,
  `valor_recomendado`, `evidencia` e `revisado_por` nulos.
- `docs/pesquisas/f50-01-amostra-para-rotular-suporte-2026-10-06-proposta.json`: as mesmas
  176 entradas com a sugestão do modelo (`julgamento_sugerido`, `valor_sugerido`,
  `trecho_sugerido`, `observacao_modelo`, `ambiguo`, `concorda`). Discordâncias primeiro.
  `revisado_por` nulo em todas.

## Como foi sorteado

- Semente: `20261006`. Teto: 40 por regra.
- Regras: as seis de `DESCRIPTION_RULES` (`seniority:description_years_min`,
  `seniority:description_years_range`, `seniority:description_entry_phrase`,
  `seniority:description_intern_phrase`, `work_mode:description_phrase`,
  `allowed_countries:description`).
- "Emite" é o que `scripts/measure_content_classification.py` chama de emitir: a mesma função
  `classify`, sobre título, local e descrição inteira da vaga.
- Excluídas as vagas que já estão em `f50-01-amostra-para-rotular.json` (368), em
  `f50-01-gold.json` (39) e em `f52-01-amostra-senioridade.json` (300 casos de senioridade),
  para não rotular a mesma vaga duas vezes. Só a primeira é o "gold existente" estrito; as
  outras duas são exclusão a mais, e pesam pouco no resultado (colunas abaixo).
- Base: dev, 18.842 vagas com descrição (de cerca de 31 mil). Leitura por `psql \copy` dentro
  de transação `READ ONLY` e regras rodadas localmente.
- Comando (a partir do CSV exportado; com `DATABASE_URL` e sem `--rows-csv` o script lê o
  banco, só com `SELECT`):

```
PYTHONPATH=src python scripts/sample_rule_support.py --seed 20261006 \
  --rows-csv rows.csv \
  --exclude-gold docs/50-roadmap-motor-de-busca/rotulagem/f50-01-amostra-para-rotular.json \
  --exclude-gold docs/50-roadmap-motor-de-busca/rotulagem/f50-01-gold.json \
  --exclude-gold docs/pesquisas/f52-01-amostra-senioridade.json \
  --out docs/pesquisas/f50-01-amostra-para-rotular-suporte-2026-10-06.json
```

O CSV tem as colunas `id, canonical_title, company_name, description, location_text,
seniority, work_mode, allowed_countries, source_type` de `opportunities.opportunity`; o tipo
de fonte é o da ocorrência mais antiga, como em `_fetch_rows`. O CSV não foi versionado (127
MB).

## Contagens por regra

| Regra | Emite no catálogo | Já no gold/amostras antigas | Sorteadas | Discordâncias da proposta |
| --- | ---: | ---: | ---: | ---: |
| `seniority:description_years_min` | 2.055 | 66 | 40 | 10 |
| `seniority:description_years_range` | 268 | 11 | 40 | 21 |
| `seniority:description_entry_phrase` | 17 | 1 | 16 | 7 |
| `seniority:description_intern_phrase` | 0 | 0 | 0 | 0 |
| `work_mode:description_phrase` | 1.680 | 52 | 40 | 8 |
| `allowed_countries:description` | 376 | 12 | 40 | 8 |
| Total | | | 176 | 54 |

Achados de suporte, independentes de rótulo:

- `description_intern_phrase` não emite em nenhuma das 18.842 vagas com descrição. Com zero
  emissões ela não chega a 20 e não pode passar.
- `description_entry_phrase` emite em 17 vagas no catálogo inteiro (16 fora do gold). Mesmo
  com todas rotuladas e certas, tem 17 emissões válidas, abaixo de 20, e só alcança o mínimo se
  o catálogo crescer. Hoje não pode passar.
- As outras quatro regras têm emissões de sobra no catálogo (268 a 2.055); o gargalo é rótulo,
  não suporte.

## Tipos de fonte na amostra

Vagas distintas (176; nenhuma vaga entrou por duas regras): `greenhouse` 81, `ashby` 68,
`workable` 16, `lever` 10, `teamtailor` 1.

| Regra | greenhouse | ashby | workable | lever | teamtailor |
| --- | ---: | ---: | ---: | ---: | ---: |
| `description_years_min` | 18 | 13 | 6 | 3 | 0 |
| `description_years_range` | 13 | 19 | 7 | 1 | 0 |
| `description_entry_phrase` | 8 | 4 | 0 | 3 | 1 |
| `work_mode:description_phrase` | 24 | 11 | 2 | 3 | 0 |
| `allowed_countries:description` | 18 | 21 | 1 | 0 | 0 |

Tipos abaixo de 20 vagas na amostra: `workable` (16), `lever` (10), `teamtailor` (1) e os que têm
descrição no catálogo e ficaram com zero: `factorial` (155 vagas com descrição), `hacker_news`
(297), `inhire` (1.494) e `remotive` (19). Remotive volta a ser um problema: das 19 vagas com
descrição, a regra de anos mínimos emite em 1 e a de modo de trabalho em 1; nenhuma foi
sorteada. Emissões no catálogo por tipo, para o dono saber o que dá para cobrir (soma das
seis regras por tipo ainda tem sobreposição de vagas):

| Tipo | years_min | years_range | entry_phrase | work_mode | countries |
| --- | ---: | ---: | ---: | ---: | ---: |
| `inhire` | 14 | 1 | 0 | 80 | 2 |
| `factorial` | 14 | 8 | 0 | 0 | 0 |
| `hacker_news` | 3 | 2 | 0 | 0 | 5 |
| `remotive` | 1 | 0 | 0 | 1 | 0 |

Rotular a amostra não resolve o critério de 50 vagas por tipo de fonte: `remotive` tem 19 vagas
com descrição no total, `teamtailor` emite poucas vezes, e quatro tipos presentes no catálogo
não aparecem na amostra. Se o dono quiser mesmo 50 por tipo, o critério ou a definição de
população precisa mudar; isso é decisão dele, não está tomada aqui.

## Proposta do modelo

O modelo julgou o valor correto do campo de cada entrada a partir do título e da descrição,
sem ver o que a regra emitiu; só depois comparou. Cada entrada traz o julgamento, o valor, um
trecho curto e, quando é incerto, uma nota (`ambiguo: true` quando o nível vem só dos anos).

Limites da leitura, ditos com clareza:

- O modelo leu o título, o início da descrição e janelas em torno de palavras de anos, nível,
  modo de trabalho e país, não cada descrição palavra por palavra. Numa conferência depois
  do julgamento, procurando pistas que as janelas não mostraram, achou três erros (anos que não
  apareciam na janela) e corrigiu. A proposta não tem varredura equivalente para os casos em
  que o julgamento foi aplicável e coerente com a janela; uma verificação cruzada de modo de
  trabalho (40 casos) não achou contradição.
- Para senioridade sem nível dito, o modelo usou bandas de anos que são julgamento dele, não
  regra do repositório: até 2 anos `JUNIOR`; 3 a 4 `MID`; 5 a 8 `SENIOR`. Faixas que cruzam
  bandas (3-5, 5-10, 7-12) ficaram `UNKNOWN`. A maior parte das 21 discordâncias em
  `description_years_range` (19) é isso: a regra emite um nível para uma faixa que o modelo
  considera ambígua. Se o dono discorda das bandas, essas discordâncias mudam de lado. Os casos
  de `description_years_min` com nível só por anos estão marcados `ambiguo`.
- As 8 discordâncias de modo de trabalho são em grande parte vagas da XP ("presencial
  flexível conforme a função"), que o modelo julgou `UNKNOWN`.

Discordâncias por regra e tipo: ver `concorda: false` na proposta. Estas contagens medem a
distância entre dois julgamentos (modelo e regra); não são precisão.

## O que o dono precisa fazer

1. Abrir a proposta e, caso a caso, preencher `judgment`, `valor_recomendado`, `evidencia` e
   `revisado_por`. Só entradas com `revisado_por` entram na medição.
2. Começar pelas discordâncias (54 primeiras). Decidir as bandas de anos de senioridade antes
   de assinar em bloco, porque elas decidem pelo menos 19 das 54.
3. Decidir o que fazer com `intern_phrase` (sem emissões) e `entry_phrase` (17 no catálogo) e
   com a população por tipo de fonte (acima).
4. Depois da assinatura, rodar o portão, uma regra por vez e com a descrição inteira:
   `python scripts/measure_content_classification.py --gold <proposta> --gold-text
   --check-gate --candidate-rule <regra>`. O arquivo de proposta já carrega a descrição inteira.

## O que isto não estabelece

- Precisão não foi medida. Com `revisado_por` nulo em todas as 176 entradas, o leitor
  (`load_gold`) carrega zero casos assinados nos dois arquivos; a precisão só existe depois
  que o dono assinar.
- A amostra sorteia entre emissões da regra; ela mede precisão (emissões corretas dentre as
  emitidas), não cobertura nem falsos negativos. O portão atual também só mede isso.
- Os 40 sorteados são uma amostra aleatória do catálogo de dev, não da produção, e com tipo de
  fonte concentrado em `greenhouse` e `ashby`.
- Nada mudou em `GATED_RULES`, nos limites (20 emissões, 90%), no código do portão ou em
  alguma regra. Nenhum rótulo foi alterado. Os arquivos antigos de gold, amostra e proposta
  não foram editados.
- A amostra e a proposta trazem a descrição de vagas públicas. Os endereços de e-mail que
  apareciam dentro dos textos (37 ocorrências em cada arquivo) foram trocados por
  `[email removido]` antes da publicação; é a única diferença para a descrição original.
  Nenhum comentário de Hacker News entrou.
