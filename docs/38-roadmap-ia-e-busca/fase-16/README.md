# Cards da Fase 16 — Camada local de IA

Estes cards executam a [SPEC da camada de IA](../../36-spec-ollama.md): o Ollama passa a
rodar na RTX 5060 com o `qwen3:8b-q4_K_M`, cada análise mede o que custa, o modelo lê a
vaga de verdade, e o pgvector dá às vagas uma noção de "parecida".

A ordem mede antes de otimizar e avalia antes de trocar.

| Ordem | Card | Depende de | Status |
| --- | --- | --- | --- |
| 1 | [F16-01 — GPU, imagem 0.34.4, `ollama-init` e perfis](f16-01-gpu-imagem-e-perfis.md) | Nenhum | Em revisão (PR #18) |
| 2 | [F16-02 — `qwen3:8b-q4_K_M` como padrão e opções da chamada](f16-02-qwen3-padrao-e-opcoes.md) | F16-01 | Em revisão (PR #18) |
| 3 | [F16-03 — custo de cada análise](f16-03-custo-de-cada-analise.md) | F16-02 | Em revisão (PR #18) |
| 4 | [F16-04 — aquecimento, `keep_alive` e fila por valor](f16-04-aquecimento-e-fila-por-valor.md) | F16-02 | Em revisão (PR #18) |
| 5 | [F16-05 — orçamento de tokens e limpador](f16-05-orcamento-de-tokens-e-limpador.md) | F16-03 | Em revisão |
| 6 | [F16-06 — conjunto de avaliação](f16-06-conjunto-de-avaliacao.md) | F16-03 | Em revisão |
| 7 | [F16-07 — vaga no payload e prompt `v2`](f16-07-vaga-no-payload-e-prompt-v2.md) | F16-05, F16-06 | Backlog |
| 8 | [F16-08 — cache persistente](f16-08-cache-persistente.md) | F16-03 | Em revisão |
| 9 | [F16-09 — pgvector e embeddings](f16-09-pgvector-e-embeddings.md) | F16-01 | Backlog |
| 10 | [F16-10 — vagas parecidas e busca por significado](f16-10-vagas-parecidas-e-busca-por-significado.md) | F16-09, F17-03 | Backlog |
| 11 | [F16-11 — contexto recuperado (RAG)](f16-11-contexto-recuperado.md) | F16-06, F16-07, F16-09 | Backlog |
| 12 | [F16-12 — confirmação de modelo e quantização](f16-12-confirmacao-de-modelo-e-quantizacao.md) | F16-06, F16-07 | Backlog |
| 13 | [F16-13 — métricas da análise](f16-13-metricas-da-analise.md) | F16-03 | Em revisão (PR #18) |

F16-09 só depende da infraestrutura e pode andar em paralelo com F16-02 a F16-08.
F16-01 a F16-04 e F16-13 fecham o Milestone O.

## Invariantes da fase

- a saída do modelo nunca altera elegibilidade, score, veredito nem fator;
- com o Ollama fora do ar, o radar coleta, normaliza, avalia e mostra tudo, só sem o
  comentário;
- nenhum prompt é truncado sem que isso fique registrado;
- toda troca de prompt, modelo, quantização ou versão de servidor passa pelo conjunto de
  avaliação;
- embedding é dado derivado: pode ser apagado e refeito, e nunca decide nada;
- nenhum dado sai da máquina.

## Verificação na fase

Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml` e
roda no CI. O CI não tem GPU e usa o Ollama falso: o que depende da RTX 5060 — modelo na
VRAM, latência real, relatórios de avaliação — é verificado na máquina de referência e
registrado no PR de cada card, como cada card descreve.
