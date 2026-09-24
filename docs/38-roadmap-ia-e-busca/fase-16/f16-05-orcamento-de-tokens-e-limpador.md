# CARD F16-05 — Orçamento de tokens, limpador de descrição e `CONTEXT_OVERFLOW`

- **Status:** Em revisão
- **Fase:** 16 — Camada local de IA
- **Depende de:** F16-03
- **Bloqueia:** F16-07, F16-09
- **Origem:** [SPEC da camada de IA](../../36-spec-ollama.md), §4.1, §5.2, §11

## Resultado

Antes de enviar, o radar sabe quantos tokens o prompt vai ocupar, corta a descrição onde
for preciso e registra o corte — e nunca manda um prompt que o servidor truncaria sem
avisar.

## Contexto

O F16-07 vai levar a descrição da vaga ao modelo. Descrições longas, somadas ao system
prompt, ao snapshot e ao perfil, podem passar da janela de 8 192 tokens. Nesse caso o
Ollama trunca o prompt pelo início — onde estão as instruções — e registra isso só no log
dele. Para o radar, a truncagem seria silenciosa. Este card entrega as ferramentas antes
de o texto entrar no payload.

## Escopo

- **Limpador** (`matching/text.py` ou módulo compartilhado com o F16-09): remove HTML e
  entidades, colapsa espaços e quebras, descarta blocos de boilerplate reconhecidos por
  cabeçalho ("About us", "Sobre nós", "Equal opportunity", "Benefits", "Benefícios"
  genéricos). A lista de padrões é versionada (`cleaner-v1`).
- **Distribuição real:** script que mede no acervo o tamanho das descrições limpas
  (caracteres, percentis) e registra em `docs/pesquisas/`. É a primeira coisa que o card
  faz, para dimensionar o orçamento com dado e não com palpite.
- **Razão caracteres/token por modelo:** calculada a partir das análises gravadas (F16-03)
  — soma de `prompt_tokens` ÷ soma de `prompt_chars` das últimas N análises do modelo.
  Nova coluna `prompt_chars` em `match_analysis`. Sem histórico, razão inicial
  conservadora (0,35 token/caractere).
- **Orçamento:** `num_ctx − num_predict − 10%`. Partes fixas (system, snapshot, perfil)
  entram inteiras; a descrição recebe o que sobrar e é cortada em fronteira de frase,
  com `description_truncated: true` no payload.
- **`CONTEXT_OVERFLOW`:** novo `AnalysisFailureCode`, não retentável. Se nem as partes
  fixas cabem, a análise não é enviada e o motivo é gravado.
- A análise grava `prompt_chars` e a estimativa de tokens feita antes do envio; a
  diferença para o `prompt_tokens` real é o indicador de calibração.

## Fora de escopo

- Colocar a descrição no payload (F16-07). Aqui as ferramentas existem e são testadas
  contra o payload atual.
- Tokenizer exato em Python: a razão calibrada é suficiente com a margem de 10%.

## Notas de implementação

- O limpador é código puro, testável com fixtures de descrições reais anonimizadas de cada
  ATS (Ashby `descriptionPlain`, Greenhouse `content` em HTML escapado, Lever
  `descriptionPlain`).
- Cortar em fronteira de frase: procurar o último `.`, `!`, `?` ou quebra de parágrafo
  antes do limite; sem nenhum, cortar em espaço.

## Critérios de aceite

- [ ] O limpador remove HTML, entidades e boilerplate listado, com teste por ATS.
- [ ] O relatório de distribuição do acervo existe em `docs/pesquisas/`.
- [ ] Nenhum prompt enviado passa do orçamento; o excedente vira corte marcado ou
      `CONTEXT_OVERFLOW`.
- [ ] Cada análise grava `prompt_chars` e a estimativa; a razão é recalculada do histórico.

## Verificação

- **CI:** testes unitários do limpador e do orçamento com textos acima e abaixo do limite;
  teste de `CONTEXT_OVERFLOW` com partes fixas artificiais maiores que a janela.
- **Máquina de referência:** comparar estimativa × `prompt_tokens` real em 20 análises e
  registrar o erro médio no PR.

## Arquivos prováveis

- `src/opportunity_radar/matching/text.py` (novo), `matching/ollama.py`,
  `matching/analysis.py`, `matching/models.py`
- `migrations/versions/*_prompt_chars.py`
- `scripts/measure_descriptions.py` (novo)
- `tests/backend/matching/`
