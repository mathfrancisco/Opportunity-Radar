# CARD F16-04 — Aquecimento, `keep_alive` e fila por valor

- **Status:** Backlog
- **Fase:** 16 — Camada local de IA
- **Depende de:** F16-02
- **Bloqueia:** Milestone O
- **Origem:** [SPEC da camada de IA](../../36-spec-ollama.md), §6.1, §6.2, §6.3

## Resultado

A primeira análise de um lote não paga a carga do modelo, a fila analisa primeiro o que o
operador vai ler primeiro, e timeout não vira retentativa imediata.

## Contexto

Carregar 5 GB de pesos na VRAM leva segundos. Sem aquecimento, esse tempo cai dentro da
primeira análise do lote e aparece como latência dela — ou como timeout. A fila hoje
segue a ordem de `pending_analysis_ids`, sem considerar veredito nem recência: com a fila
atrasada, uma vaga `WATCHLIST` antiga pode ser analisada antes de uma `HIGH_PRIORITY` de
hoje. E o adaptador trata `TIMEOUT` como retentável, então um modelo que estourou o tempo
com uma entrada tenta de novo na hora, com a mesma entrada.

## Escopo

- `OllamaAnalysisAdapter.warm_up()`: `POST /api/generate` com `{"model", "prompt": "",
  "keep_alive"}`, que carrega o modelo sem gerar texto. Devolve as métricas da carga
  (`load_duration`) e nunca levanta exceção.
- Job único `warm-up-models` agendado no início do worker (`next_run_time` imediato,
  sem intervalo), só quando a análise está habilitada. Não entra em
  `FUNCTIONAL_JOB_IDS`, porque não é recorrente.
- Reaquecimento antes de um lote quando a última chamada ao modelo foi há mais tempo que o
  `keep_alive` configurado. O adaptador guarda o instante da última chamada; ele é o mesmo
  objeto entre lotes (passado em `args` do job).
- `pending_analysis_ids` ordena por valor: `HIGH_PRIORITY`, `RECOMMENDED`,
  `REVIEW_REQUIRED`, `WATCHLIST`; dentro de cada um, publicação mais recente primeiro.
- `TIMEOUT` deixa de ser retentado dentro do adaptador. Retentativa imediata fica só para
  transporte e 5xx, com backoff exponencial e jitter. A retentativa de timeout é o cooldown
  da fila (`analysis_retry_*`).

## Fora de escopo

- Paralelismo de análises: `OLLAMA_NUM_PARALLEL=1` é decisão de VRAM (SPEC §3.1).
- Cliente HTTP persistente: descartado na SPEC §6.1, porque o worker cria um loop de
  eventos por análise (`asyncio.run`, `worker.py:163`).

## Notas de implementação

- `/api/generate` com `prompt` vazio é o jeito documentado do Ollama de carregar um
  modelo; com `keep_alive` ele fica residente.
- O aquecimento loga `load_ms` com `job = "warm-up"`; é a medida de "primeira análise após
  ociosidade" da SPEC §3.2.
- A ordenação por veredito precisa de uma expressão `CASE` estável e de `id` como último
  critério, para lotes determinísticos.

## Critérios de aceite

- [ ] O worker aquece o modelo ao subir, com a análise habilitada, e registra `load_ms`.
- [ ] Um lote após ociosidade maior que o `keep_alive` é precedido de aquecimento.
- [ ] Com as quatro categorias pendentes, a ordem de análise segue a da seção de escopo.
- [ ] `TIMEOUT` não é retentado pelo adaptador; transporte e 5xx são, com backoff.
- [ ] Servidor indisponível no aquecimento não impede o worker de subir.

## Verificação

- **CI:** teste do adaptador para `warm_up` com servidor falso respondendo e fora do ar;
  teste de integração de `pending_analysis_ids` com assessments de vereditos e datas
  misturados; teste da política de retentativa.
- **Máquina de referência:** no log do worker, `load_ms` do aquecimento e o `load_ms` da
  primeira análise logo depois (esperado: perto de zero).

## Arquivos prováveis

- `src/opportunity_radar/matching/ollama.py`, `matching/service.py`
- `src/opportunity_radar/worker.py`
- `tests/backend/matching/test_ollama_adapter.py`, `tests/backend/test_worker.py`
