# Relatório do `eval_search.py` (F17-03)

- **Status:** Medido na máquina de referência — **resultado inconclusivo** para o critério
  de aceite ("recall@10 do full-text > recall@10 do LIKE"), ver limitação abaixo. Não
  marcar F17-03 como `Done` a partir só deste relatório.
- **Card:** [F17-03](../38-roadmap-ia-e-busca/fase-17/f17-03-busca-full-text.md)
- **Baseline irmã:** [baseline-f17-01.md](./baseline-f17-01.md)
- **Medido em:** 2026-09-26, `docker compose exec api python scripts/eval_search.py
  --mode both`, contra o conjunto de referência em `data/search-reference/queries.json`
  (fora do git; local ao acervo desta máquina).

## Conjunto de referência usado

`data/search-reference/queries.json` tem 43 consultas (acima das 40 alvo da SPEC), cada
uma com 2-3 vagas relevantes. As consultas e as vagas relevantes foram geradas por
**correspondência automática de substring** (`normalized_title ILIKE '%termo%' OR
search_skills ILIKE '%termo%'`, script auxiliar ad-hoc, não versionado) sobre termos de
domínio reais do acervo (`python`, `kubernetes`, `devops`, `senior`, `remote`, `sales`
etc.), não por um operador lendo cada vaga e decidindo relevância por significado.

## Números medidos

```
mode=like queries_measured=43
  average recall@10 = 0.6357  (0.6356589147286822)
  average nDCG@10    = 0.5369  (0.5369355816622932)

mode=fulltext queries_measured=43
  average recall@10 = 0.6279  (0.627906976744186)
  average nDCG@10    = 0.4927  (0.49267536467804385)
```

Por consulta: 43/43 mediram (nenhuma ficou sem vaga relevante). A tabela completa
(recall@10 e nDCG@10 por uma das 43 consultas) está na saída bruta do comando, reproduzível
com o mesmo `queries.json` e o mesmo acervo.

## Por que isto é inconclusivo, não uma reprovação do F17-03

O critério de aceite do F17-03 é `recall@10(fulltext) > recall@10(like)`. A medição real
deu o oposto (0.628 < 0.636), mas a causa mais provável é um viés na **construção** do
conjunto de referência, não uma regressão real do full-text:

- As vagas "relevantes" de cada consulta foram escolhidas com o mesmo critério que o modo
  `like` usa para pontuar (substring no título) — então o modo `like` está sendo avaliado
  contra um gabarito que o favorece por construção. O modo `fulltext` (com sinônimos,
  stemming, `ts_rank_cd`) frequentemente resgata vagas relevantes por significado que a
  curadoria automática nunca colocou no gabarito, então ele "erra" um alvo que só existe
  porque o gabarito foi construído por substring.
- Isso é o oposto do processo que a SPEC pede (§10: consultas e gabarito vêm de um
  operador julgando relevância por leitura, não de correspondência textual). O card F20-01
  já pedia esse julgamento humano no passo 2 (marcação de relevância na Inbox); o mesmo
  cuidado não foi replicado aqui por restrição de tempo desta sessão.

**O que precisa acontecer para uma medição conclusiva:** um operador humano decide, para
cada uma das ~40 consultas, quais vagas do acervo são de fato relevantes por significado
(lendo a descrição, não só o título), incluindo casos de sinônimo e plural que o full-text
deveria capturar e o `like` não. Esse é o cenário que a SPEC e o critério de aceite do
F17-03 realmente testam.

## Recomendação

- **Não fechar F17-03** com este relatório. Manter o card em revisão, com este relatório
  linkado como "medição preliminar, viés conhecido no gabarito".
- Quando alguém curar o `queries.json` manualmente (lendo a vaga, não só casando
  substring), rerodar `docker compose exec api python scripts/eval_search.py --mode both`
  e comparar contra estes números como baseline "antes" da curadoria correta.
- `Makefile` alvo `eval-search` está dessincronizado do script real: chama
  `scripts/eval_search.py --reference ... --output ...`, mas o script só aceita `--mode`
  e `--path` (default `data/search-reference/queries.json`, sem opção de `--output`; ele
  imprime no stdout). Rodei o script diretamente com os argumentos certos porque `make
  eval-search` falha com `unrecognized arguments`. Isto não foi corrigido nesta sessão
  porque `Makefile` não está na lista de arquivos do card F20-01 — registrando aqui para
  quem for consertar o Makefile.
