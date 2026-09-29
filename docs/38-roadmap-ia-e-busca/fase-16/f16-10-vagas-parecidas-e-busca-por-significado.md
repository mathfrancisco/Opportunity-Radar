# CARD F16-10 — Vagas parecidas e busca por significado, com gate de uso

- **Status:** Backlog
- **Fase:** 16 — Camada local de IA
- **Depende de:** F16-09, F17-03
- **Bloqueia:** Nenhum; melhoria opcional após Milestone P
- **Origem:** [SPEC da camada de IA](../../36-spec-ollama.md), §7.3, §7.4

## Resultado

O detalhe de cada vaga mostra as mais parecidas e como foram decididas, e a busca por
significado existe pela API; ela só vira o modo da Inbox se vencer a busca full-text no
conjunto de referência.

## Contexto

Com os vetores do F16-09, "parecida" passa a ser uma consulta de cosseno. O uso na busca
é diferente: a busca full-text do F17-03 pode resolver sozinha o que se procura, e
colocar vetor na Inbox sem medir seria trocar um resultado explicável por outro
inexplicável sem saber se é melhor.

## Escopo

- `GET /opportunities/{id}/similar?limit=5`: vizinhos pelo operador `<=>` do pgvector,
  mesmo modelo de embedding, sem a própria vaga, com título, empresa, veredito atual e
  similaridade (`1 − distância`).
- `GET /search/semantic?q=&limit=20`: roteador próprio (`/search`). A consulta vira vetor
  com a instrução do `qwen3-embedding`
  (`Instruct: Given a job search query, retrieve relevant job postings\nQuery: {q}`),
  versionada junto com o modelo. Ollama indisponível → 503 com código, não 500.
- Tela: seção "Vagas parecidas" no detalhe da oportunidade, com veredito e link; vazia
  quando a vaga ainda não tem vetor, dizendo isso.
- **Gate:** script `scripts/eval_search.py` roda as 40 consultas de referência do F17-03
  em três modos — full-text, vetorial e híbrido por *reciprocal rank fusion* (k = 60) — e
  calcula recall@10 e nDCG@10. Relatório em `docs/pesquisas/`.
- **Decisão:** se o vetorial ou o híbrido vencer o full-text em recall@10 por pelo menos
  15% relativo, sem queda de nDCG@10 e dentro do orçamento de latência
  pré-registrado (hipótese inicial p95 aquecido ≤ 2 s), a Inbox ganha o modo vencedor (chave "Buscar por significado" ligada por padrão);
  senão, a busca semântica fica só na API e o relatório registra por quê.
- **Sinal de duplicata** para o F17-08: pares da mesma empresa com similaridade ≥ 0,95.

## Fora de escopo

- Reranqueamento por modelo de linguagem.
- Uso dos vetores dentro da análise (F16-11).

## Notas de implementação

- A rota não pode ficar sob `/opportunities/semantic-search`: `GET
  /opportunities/{opportunity_id}` é declarado antes e capturaria o caminho, respondendo
  422.
- A distância de uma vaga consigo mesma é 0; excluir por `id`, não por distância.
- Usar corpus/filtros/perfil congelados e consultas reservadas do F17-01.
  Registrar suporte, dispersão e cobertura atual do índice; baseline zero exige
  critério absoluto pré-registrado. Paginação estável, com id no desempate final.
- A Inbox faz fallback full-text em timeout, indisponibilidade ou índice parcial,
  preserva termo/filtros e informa modo efetivo. O 503 é só da rota isolada.
- O híbrido soma `1 / (60 + posição)` das duas listas; empate desfeito por publicação.

## Critérios de aceite

- [ ] O detalhe da vaga mostra até 5 vagas parecidas, com veredito.
- [ ] A busca por significado responde pela API e degrada com 503 classificado sem
      Ollama.
- [ ] O relatório do gate existe, com os três modos e as duas métricas.
- [ ] A Inbox adota o modo que o relatório indicar, e só ele.

- [ ] Falha da IA/reindexação não interrompe a busca da Inbox e preserva filtros.
- [ ] Consumidores excluem vetores antigos e mantêm desempate estável por id.
- [ ] Gate reporta ganho relativo, nDCG, latência e cobertura no mesmo corpus.

## Verificação

- **CI:** testes de integração das duas rotas com vetores fixos inseridos direto no banco;
  teste do RRF com listas conhecidas; E2E chamando `/opportunities/{id}/similar` depois do
  ciclo autônomo.
- **Máquina de referência:** execução do `eval_search.py` com as 40 consultas, anexada ao
  PR.

## Arquivos prováveis

- `src/opportunity_radar/opportunities/embeddings.py`
- `src/opportunity_radar/presentation/http/opportunities.py`, `search.py` (novo),
  `routes.py`
- `scripts/eval_search.py` (novo)
- `apps/web/src/routes/OpportunityDetailPage.tsx`, `apps/web/src/features/opportunities/`
