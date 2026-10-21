# LLM gratuitos para o Bateia — pesquisa de 2026-10-20

Objetivo: não depender só do Groq (free tier) e da Token Harbor, que esgotam em dias de muita coleta.
Leitura feita em 2026-10-20. Limites de terceiros mudam sem aviso: conferir no painel de cada provedor
antes de ligar. Onde a fonte é oficial, está marcado **(oficial)**.

## Quanto o Bateia gasta

- `job_match`: até 5.000 tokens de entrada e 800–900 de saída (`platform/ai/tasks.py`), ~6 k por análise.
- `job_classification`: 1.500 + 300. `job_extraction`: 3.000 + 600.
- Groq free: ~200 k tokens/dia por modelo, então umas 35 análises `job_match` por modelo por dia.

## Candidatos

| Provedor | Prefixo proposto | Modelos (open-weight) | Limite grátis | Privacidade | Veredito |
|---|---|---|---|---|---|
| Groq (atual) | — | gpt-oss-120b, gpt-oss-20b, qwen3.8-27b | 30 RPM, 1 k RPD, ~200 k TPD por modelo | não declarado | manter, primeiro da cadeia |
| Cerebras | `cerebras:` | gpt-oss-120b, qwen-3.8-27b (mesmos do Groq) | **(oficial)** 5 RPM, 90 k TPM, 1 M tokens/hora e /dia por modelo; exige cartão verificado | não declarado | **adicionar** — mesmo modelo, ~5× a cota diária |
| OpenCode Zen | `zen:` | deepseek-v4.1-flash-free, glm-5.3-flash-free, minimax-m3.1-flash-free | **(oficial)** grátis "por tempo limitado"; limites não publicados | **(oficial)** zero retenção, sem treino nesses três | **adicionar** — confirmar termos de uso fora de agente de código (help@anoma.ly) |
| Token Harbor (atual) | `tokenharbor:` | deepseek-v4.1-flash:free, mimo-v2.6-flash:free | 60 RPM, 1,8 k/hora; janela móvel de 7 dias | pode reter prompts | manter, depois do Zen |
| Google AI Studio (Gemma) | `gemini:` | Gemma 4 31B/26B | não publicado por modelo; um blog cita 3 k/dia | grátis pode ser usado para melhorar produtos fora de EEA/UK/CH | **adicionar** |
| OpenRouter `:free` | `openrouter:` | gpt-oss-120b:free, nemotron, gemma-4 | 20 RPM, 50/dia (1 k/dia após US$ 10 em créditos, uma vez) | provedores grátis podem registrar prompts | **adicionar** |
| Cloudflare Workers AI | `workersai:` | @cf/openai/gpt-oss-120b | **(oficial)** 10 k neurons/dia (~45 `job_match`); acima disso US$ 0,011 / 1 k neurons (~US$ 0,0024 por análise) | não declarado | **adicionar** como reserva paga com teto diário |
| NVIDIA NIM | — | gpt-oss, nemotron | 40 RPM | "trial use only — do not submit personal or confidential data" | **adicionar** (projeto pessoal; texto já sanitizado) |
| Mistral La Plateforme | — | Mistral Small/Large | não publicado | grátis exige aceitar treino | **adicionar** (treino aceito) |
| GitHub Models | — | Llama, DeepSeek | fechado a novas contas desde jun/2026 (fonte única) | — | não usar |
| Ollama na VM (self-host) | `ollama:` | gpt-oss-20b, qwen3 8B | sem cota; limite é CPU/RAM | dados não saem da VM | fase 2: a VM atual tem 8 GB; OCI A1 (24 GB) só com medição |

## Decisão proposta

1. Uma camada de provedores declarativa, compatível com OpenAI, em vez de uma classe por provedor.
2. Cadeia: modelos do Groq → Cerebras → Zen → NIM → Token Harbor → Gemma → Mistral → OpenRouter → Workers AI com teto diário.
   Treino com os prompts é aceito: o projeto é pessoal (decisão do dono, 2026-10-20).
3. Cota por provedor (os limites de hoje são iguais para todo modelo).
4. Um script de sondagem que confirma, com chave real, se cada modelo aceita `json_schema` e devolve JSON válido.
5. Ordem final e flags decididas por medição (`scripts/eval_analysis.py` + `scripts/benchmark_report.py`), não por opinião.

Plano: `docs/superpowers/plans/2026-10-20-ia-multiprovedor.md`.

## Fontes

- Cerebras rate limits (oficial): https://inference-docs.cerebras.ai/support/rate-limits
- OpenCode Zen docs (oficial): https://opencode.ai/docs/zen/
- Cloudflare Workers AI pricing (oficial): https://developers.cloudflare.com/workers-ai/platform/pricing/
- Cloudflare OpenAI compatibility (oficial): https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/
- Gemini OpenAI compatibility (oficial): https://ai.google.dev/gemini-api/docs/openai
- Free LLM API tiers, out/2026: https://dev.to/tariqnasser/free-llm-api-tiers-in-october-2026-whats-left-and-how-i-chain-them-227l
- awesome-free-llm-apis: https://github.com/amardeeplakshkar/awesome-free-llm-apis
- OpenRouter limits: https://www.truefoundry.com/pt/blog/openrouter-rate-limits-your-free-tier-depends-on-what-youve-already-paid
- NVIDIA NIM 40 RPM: https://forums.developer.nvidia.com/t/request-for-nvidia-nim-api-rate-limit-increase-40-200-rpm/378941
- Mistral free tier: https://benchlm.ai/md/free-tier/mistral.md
- GitHub Models: https://klymentiev.com/blog/github-models-shutdown
- Gemma 4 no Gemini API: https://en.kocpc.com.tw/?p=3753
- Ampere A1 / Llama 3: https://amperecomputing.com/blogs/llama3-on-Ampere-based-OCI-A1
