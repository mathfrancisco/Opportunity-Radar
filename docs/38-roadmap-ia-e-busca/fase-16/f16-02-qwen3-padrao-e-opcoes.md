# CARD F16-02 — `qwen3:8b-q4_K_M` como padrão e opções explícitas da chamada

- **Status:** Backlog
- **Fase:** 16 — Camada local de IA
- **Depende de:** F16-01
- **Bloqueia:** F16-03, F16-04, Milestone O
- **Origem:** [SPEC da camada de IA](../../36-spec-ollama.md), §3.3, §4.4, §5.1

## Resultado

Toda análise usa o `qwen3:8b-q4_K_M` com janela, limite de saída, semente, `keep_alive` e
raciocínio desligado declarados na própria requisição, e nenhuma dessas escolhas depende
de padrão do servidor.

## Contexto

O padrão atual é `llama3.2:3b`, escolhido pelo custo em CPU antes de haver GPU e
avaliação. A requisição (`matching/ollama.py:196`) envia só `temperature: 0`: a janela de
contexto, o tamanho máximo da resposta e o tempo que o modelo fica carregado ficam por
conta do servidor. O Qwen3 ainda raciocina antes de responder por padrão, o que numa
análise estruturada gasta segundos e janela sem melhorar a saída.

`.env.example` declara `OLLAMA_MODEL_OUTREACH` e `OLLAMA_MODEL_INTERVIEW`, que nenhum
código lê.

## Escopo

- `Settings` (`platform/config.py`):
  - `ollama_model_analysis = "qwen3:8b-q4_K_M"`;
  - `ollama_num_ctx = 8192`, `ollama_num_predict = 1024`, `ollama_seed = 42`;
  - `ollama_keep_alive = "30m"`, `ollama_think = False`;
  - `ollama_analysis_timeout_seconds = 60` (com o aquecimento do F16-04, a carga sai do
    caminho da análise; até lá, 60 s cobre a primeira carga de 5 GB).
- `OllamaAnalysisAdapter` recebe as opções pelo construtor e monta o payload:
  `options = {temperature, num_ctx, num_predict, seed}`, e no topo da requisição
  `keep_alive` e `think`. `build_analysis_adapter` passa tudo a partir das `Settings`.
- `compose.yaml` (âncora `app-environment`) e `.env.example` com as variáveis novas.
- Remover `OLLAMA_MODEL_OUTREACH` e `OLLAMA_MODEL_INTERVIEW` do `.env.example`.
- `prompts/opportunity_analysis/v1/metadata.yaml`: `default_model: qwen3:8b-q4_K_M`.
- `docs/21-ollama-prompts.md` §7 e o runbook com o modelo e as variáveis novas.
- `tests/e2e/fake_ollama.py`: responder com `"model": "qwen3:8b-q4_K_M"`.

## Fora de escopo

- Mudar o prompt, o schema ou o payload de conteúdo (F16-07).
- Gravar métricas (F16-03).
- Comparar modelos (F16-12) — aqui a troca é a decisão da SPEC §3.3.

## Notas de implementação

- `think` é campo do topo da requisição do `/api/chat`, não de `options`.
- A chave de cache (`analysis_cache_key`) já inclui `model_id`. Trocar o modelo faz toda
  análise nova ser uma chave nova; as análises antigas ficam no histórico com
  `model_id = llama3.2:3b`. Conferir em `MatchingService.pending_analysis_ids` se a troca
  reenfileira as avaliações já analisadas. Se reenfileirar tudo de uma vez, a fila por
  valor do F16-04 decide a ordem, e o cooldown existente limita o ritmo.
- O `health` compara o modelo configurado com `/api/tags`. O Ollama falso responde lista
  vazia de propósito, para o primeiro passo do E2E ver `degraded`; isso continua valendo
  com o modelo novo — não listar o `qwen3` no falso.
- `tests/backend/matching/test_ollama_adapter.py:102` confere `temperature`; estender para
  as demais opções.

## Critérios de aceite

- [ ] O modelo padrão é `qwen3:8b-q4_K_M` nas `Settings`, no `.env.example`, no compose e
      no `metadata.yaml`.
- [ ] O payload enviado contém `num_ctx`, `num_predict`, `seed`, `temperature`,
      `keep_alive` e `think: false`, conferido por teste do adaptador.
- [ ] Nenhuma variável de modelo sem uso sobra no `.env.example`.
- [ ] Na máquina de referência, uma análise completa com o modelo novo, na GPU, e grava
      `model_id = qwen3:8b-q4_K_M`.

## Verificação

- **CI:** teste do adaptador com cliente falso inspecionando o corpo da requisição; E2E
  existente com o Ollama falso.
- **Máquina de referência:** uma análise pela tela ("Analisar agora" no detalhe da vaga) e
  `ollama ps` durante ela.

## Arquivos prováveis

- `src/opportunity_radar/platform/config.py`
- `src/opportunity_radar/matching/ollama.py`, `matching/adapters.py`
- `tests/backend/matching/test_ollama_adapter.py`
- `tests/e2e/fake_ollama.py`
- `prompts/opportunity_analysis/v1/metadata.yaml`
- `compose.yaml`, `.env.example`, `docs/21-ollama-prompts.md`, `docs/30-runbook.md`
