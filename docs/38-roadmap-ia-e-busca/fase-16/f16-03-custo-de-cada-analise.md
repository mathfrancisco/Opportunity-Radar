# CARD F16-03 — Custo de cada análise: durações e tokens

- **Status:** Backlog
- **Fase:** 16 — Camada local de IA
- **Depende de:** F16-02
- **Bloqueia:** F16-05, F16-06, F16-08, F16-13
- **Origem:** [SPEC da camada de IA](../../36-spec-ollama.md), §3.2, §9

## Resultado

Cada análise grava quanto custou — tempo total, carga do modelo, tokens de entrada e de
saída e o tempo de cada fase — e a API devolve esses números com a análise.

## Contexto

O Ollama devolve em toda resposta `total_duration`, `load_duration`, `prompt_eval_count`,
`prompt_eval_duration`, `eval_count` e `eval_duration` (em nanossegundos). O adaptador
descarta tudo. Hoje não há como dizer quanto uma análise leva, quanto disso é carga de
modelo, nem se o timeout corta respostas que teriam terminado. Todas as metas de latência
da SPEC (§3.2) dependem deste card.

## Escopo

- `AnalysisMetrics` em `matching/analysis.py`: `total_ms`, `load_ms`, `prompt_tokens`,
  `prompt_eval_ms`, `output_tokens`, `eval_ms`, todos opcionais. `AnalysisOutcome` ganha
  `metrics`.
- O adaptador lê os campos da resposta, converte ns → ms e anexa as métricas ao resultado
  — também quando a resposta chegou mas não validou (`SCHEMA_MISMATCH`, `INVALID_JSON`),
  porque uma resposta inválida depois de 40 s é um problema diferente de uma depois de 2 s.
- Migração: seis colunas `Integer` anuláveis em `matching.match_analysis`.
- `AnalysisRecord`, `MatchAnalysisModel` e `add_analysis` carregam os números.
- `MatchAnalysisResponse.metrics` (objeto ou `null`) na API de matching e no detalhe da
  oportunidade.
- Log estruturado do job `analyze` com os mesmos campos por análise.
- `fake_ollama.py` devolve durações e contagens fixas, e o E2E confere que a análise
  gravada tem `metrics.total_ms` preenchido.
- Frontend: no painel da análise, linha discreta "gerada em X s · N tokens", e
  "indisponível" quando `metrics` é `null`.

## Fora de escopo

- Agregados, percentis e endpoint de métricas (F16-13).
- Estimativa de tokens antes do envio (F16-05).

## Notas de implementação

- Resposta servida do cache em memória não é chamada ao modelo: `metrics = null`, nunca
  zeros.
- Campo ausente ou negativo na resposta vira `null`; nada é inventado.
- As linhas antigas ficam com `null` nas seis colunas, e a interface mostra
  "indisponível".

## Critérios de aceite

- [ ] Análise concluída grava as seis medidas quando o servidor as envia.
- [ ] Análise que falhou depois de o modelo responder grava as medidas da resposta.
- [ ] Análise servida de cache e análise que não chegou ao modelo gravam `null`.
- [ ] A API e a tela mostram as medidas, e "indisponível" quando não existem.
- [ ] O E2E confere `metrics.total_ms` numa análise do Ollama falso.

## Verificação

- **CI:** testes do adaptador para resposta com métricas, sem métricas e com schema
  inválido; migração de ida e volta; asserção nova no passo de análise semântica do E2E.
- **Máquina de referência:** registrar no PR o p50 de 10 análises, como primeira medição
  da SPEC §3.2.

## Arquivos prováveis

- `src/opportunity_radar/matching/analysis.py`, `ollama.py`, `service.py`,
  `repository.py`, `models.py`
- `src/opportunity_radar/presentation/http/matching.py`
- `migrations/versions/*_analysis_cost.py`
- `tests/e2e/fake_ollama.py`, `.github/workflows/pipeline.yml`
- `apps/web/src/features/matching/`, painel de análise no detalhe da oportunidade
