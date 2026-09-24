# CARD F16-12 — Confirmação do modelo e da quantização

- **Status:** Backlog
- **Fase:** 16 — Camada local de IA
- **Depende de:** F16-06, F16-07
- **Bloqueia:** Nenhum
- **Origem:** [SPEC da camada de IA](../../36-spec-ollama.md), §8.1, §12

## Resultado

A escolha do `qwen3:8b-q4_K_M` como padrão fica confirmada — ou substituída — por um
relatório que compara qualidade, latência e VRAM no hardware de referência.

## Contexto

O modelo padrão foi decidido pelo operador (SPEC §3.3) com base em fontes públicas,
antes de existir o conjunto de avaliação. A regra da §8 vale para sair desse padrão; este
card aplica a regra uma vez, com o prompt `v2`, para fechar a decisão com número.

## Escopo

Rodar `make eval-analysis PROMPT=v2` para cada candidato, registrando também a VRAM
ocupada (`ollama ps`, com `num_ctx` de 8 192) e a latência p50/p95:

| Candidato | Papel na comparação |
| --- | --- |
| `qwen3:8b-q4_K_M` | padrão atual |
| `qwen3:8b-q4_K_M` com `think: true` | custo × ganho do raciocínio |
| `llama3.1:8b` em Q4_K_M | outra família, mesmo porte |
| `llama3.2:3b` | piso: o que havia antes |
| `qwen3:4b` em Q4_K_M | reserva se o 8B não couber com folga (cerca de 2,6 GB) |
| `gemma3:4b` em Q4_K_M | outra família pequena, bom em português |
| `phi4-mini` | outra família pequena, forte em raciocínio curto |
| Qwen3 8B em Q5_K_M ou Q6_K | só se houver tag oficial no Ollama; senão, registrar a ausência |
| KV cache `f16` × `q8_0` | efeito da quantização do cache na qualidade e na VRAM |

- **Desclassificação:** qualquer configuração que ocupe RAM além da VRAM (`size_vram <
  size`) sai da comparação, qualquer que seja a nota.
- **Folga real de VRAM:** no Windows, se a RTX 5060 também liga o monitor, o desktop já
  ocupa de 0,5 a 1 GB dela. Medir com o desktop aberto, como é o uso real. Se o 8B
  transbordar, testar primeiro `num_ctx` 6 144 e depois o `qwen3:4b`, nessa ordem.
- **Temperatura e ocupação da GPU:** registrar pico de temperatura e utilização
  (`nvidia-smi --query-gpu=temperature.gpu,utilization.gpu --format=csv -l 1`) durante as
  30 análises de cada candidato. Utilização alta é esperada — é a GPU trabalhando —, mas
  temperatura sustentada acima de 80 °C entra no relatório como custo.
- **Fora da comparação:** modelos de raciocínio como o DeepSeek-R1, que geram cadeia de
  pensamento antes de responder — custam muito tempo e tokens num resumo estruturado, o
  mesmo motivo de `think: false` no Qwen3. E modelos de 12B ou mais (Gemma3 12B, Qwen3
  14B, gpt-oss 20B), que precisam de 12 GB ou mais e transbordariam nos 8 GB.
- **Decisão:** manter o padrão, a menos que outro candidato não piore nenhum critério e
  melhore pelo menos um. A decisão atualiza a SPEC §3.3, o `.env.example` e o
  `metadata.yaml`.

## Quantizações disponíveis (conferido em 24/09/2026)

O Ollama oficial publica, para o `qwen3:8b`, só estas tags:

| Tag | Tamanho | Cabe nos 8 GB com contexto de 8K? |
| --- | --- | --- |
| `qwen3:8b-q4_K_M` (padrão) | 5,2 GB | sim |
| `qwen3:8b-q8_0` | 8,9 GB | não |
| `qwen3:8b-fp16` | 16 GB | não |

**Não existem** tags oficiais `q4_K_S`, `q5_K_M` nem `q6_K` para o 8B. Consequências:

- A linha "Qwen3 8B em Q5_K_M ou Q6_K" da comparação fica registrada como **indisponível
  no oficial**, e não é testada por padrão.
- **Q4_K_S** (menor que a Q4_K_M, mais folga de VRAM) foi sugerida em relato de uso do
  Qwen com cache de contexto em Q8_0. Ela só existe em GGUF de terceiros no Hugging Face,
  que o Ollama baixa como `hf.co/<autor>/<repositório>:Q4_K_S`. Entra na comparação como
  **experimento**, não como candidata a padrão, e só se o 8B oficial não couber com folga:
  - apenas de quantizador conhecido, com o repositório e o arquivo registrados no
    relatório (não é tag fixada pelo Ollama: o conteúdo pode mudar);
  - o conjunto de avaliação roda com contagem de repetições: resposta que repete o mesmo
    trecho ou atinge o `num_predict` sem fechar o JSON conta como falha — o mesmo relato
    aponta que uma variante não oficial do Qwen "fica presa em loops";
  - adotar exigiria a regra da SPEC §8 e, além dela, fixar o arquivo por hash.
- Se o problema for só folga de VRAM, a ordem da SPEC continua valendo: `num_ctx` 6 144,
  depois `qwen3:4b` oficial, e só então o GGUF de terceiros.

## Fora de escopo

- Modelos que não cabem em 8 GB com o contexto útil (12B ou mais em Q4).
- Quantizar ou converter modelo localmente (GGUF próprio).

## Notas de implementação

- Descarregar o modelo anterior entre candidatos (`keep_alive: 0`) para que a VRAM medida
  seja a do candidato.
- Com `think: true`, os tokens de raciocínio contam no custo; o orçamento do F16-05 precisa
  de `num_predict` maior para esse candidato, registrado no relatório.

## Critérios de aceite

- [ ] Relatório em `docs/pesquisas/` com todos os candidatos disponíveis, nota por
      critério, latência e VRAM.
- [ ] A decisão está registrada na SPEC §3.3, com o motivo.

## Verificação

- **Máquina de referência:** é um card de medição; o relatório é o entregável e fica
  anexado ao PR que atualiza a SPEC.

## Arquivos prováveis

- `docs/pesquisas/*-comparacao-modelos.md` (novo)
- `docs/36-spec-ollama.md`, `.env.example`, `prompts/opportunity_analysis/v2/metadata.yaml`
