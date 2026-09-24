# CARD F16-06 — Conjunto de avaliação e `make eval-analysis`

- **Status:** Backlog
- **Fase:** 16 — Camada local de IA
- **Depende de:** F16-03
- **Bloqueia:** F16-07, F16-11, F16-12
- **Origem:** [SPEC da camada de IA](../../36-spec-ollama.md), §8

## Resultado

Existe um conjunto fixo de 30 casos e um comando que roda qualquer combinação de prompt e
modelo contra ele, com nota por critério e comparação com o último baseline. A partir
daqui, trocar prompt, modelo ou quantização é decisão com número.

## Contexto

`prompts/opportunity_analysis/v1/examples.json` guarda saídas de referência lidas só por
teste. Não há como dizer se um prompt `v2` é melhor que o `v1`, nem se o `qwen3:8b` é
melhor que o `llama3.2:3b` — só impressão.

## Escopo

- **Casos:** 30 pares vaga/perfil reais, anonimizados, em
  `prompts/opportunity_analysis/eval/cases/NN-descricao.json`. Cada caso guarda o payload
  de entrada completo (snapshot, perfil e, quando existir, o bloco `posting`) e o
  **gabarito**:
  - `verdict` do motor determinístico;
  - `must_mention_risks`: exigências do anúncio ausentes do perfil, marcadas à mão;
  - `must_not_claim`: afirmações que seriam invenção (ex.: remuneração não informada);
  - `language: pt-BR`.
- **Cobertura dos casos:** vaga forte, vaga fraca, ambígua, descrição longa, descrição em
  inglês, sem descrição, remuneração ausente, país não informado.
- **Pontuação por código** (`scripts/eval_analysis.py`):
  - fidelidade: fração dos `evidence` que aparecem literalmente no payload (a partir do
    schema `v2`; no `v1`, não se aplica);
  - cobertura: fração de `must_mention_risks` presentes em `risks` (casamento por termos
    normalizados);
  - invenção: ocorrências de `must_not_claim`;
  - idioma: proporção de palavras de parada em português × inglês nos campos de texto;
  - custo: `prompt_tokens`, `output_tokens`, `total_ms` (do F16-03).
- **Aderência ao veredito:** nota manual 0/1 por caso, preenchida pelo operador numa
  coluna do relatório. Não se pede a outro modelo para julgar.
- **Comando:** `make eval-analysis PROMPT=v1 MODEL=qwen3:8b-q4_K_M` roda os 30 casos contra
  o Ollama local, grava `data/evals/<data>-<prompt>-<modelo>.json` e `.md`, e compara com
  o baseline indicado (`BASELINE=`).
- **Baseline inicial:** `v1` × `llama3.2:3b` e `v1` × `qwen3:8b-q4_K_M`, registrados em
  `docs/pesquisas/`.

## Fora de escopo

- Rodar o conjunto no CI: o CI tem o Ollama falso e não tem GPU.
- Julgamento por outro modelo (LLM-as-judge).

## Notas de implementação

- Anonimizar: trocar nome de empresa, remover URLs, e-mails e nomes de pessoas das
  descrições; manter o conteúdo técnico.
- O comando usa o mesmo adaptador de produção com as mesmas `Settings`, para medir o que
  vai rodar de verdade.
- `seed` fixo (F16-02) torna duas rodadas do mesmo par comparáveis; rodar cada caso uma
  vez só.

## Critérios de aceite

- [ ] 30 casos anonimizados, com gabarito, cobrindo os tipos listados.
- [ ] `make eval-analysis` gera relatório JSON e Markdown com nota por critério e por caso.
- [ ] A comparação com baseline mostra melhora, piora ou empate por critério.
- [ ] Os dois baselines iniciais estão em `docs/pesquisas/`.

## Verificação

- **CI:** testes unitários de cada pontuador com saídas fixas (inclusive casos de
  invenção e de idioma errado); validação de que todo caso do conjunto carrega e tem
  gabarito completo.
- **Máquina de referência:** as duas rodadas de baseline, anexadas ao PR.

## Arquivos prováveis

- `prompts/opportunity_analysis/eval/cases/` (novo)
- `scripts/eval_analysis.py` (novo), `Makefile`
- `tests/backend/matching/test_eval_scoring.py` (novo)
- `docs/pesquisas/*-baseline-analise.md`
