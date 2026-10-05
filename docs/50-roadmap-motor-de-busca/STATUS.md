# SPEC 50 — estado da implementação

- **Atualizado em:** 2026-10-05
- **Branch:** `f50-motor-de-busca`, criada de `75d688b`. Nada foi enviado ao remoto nem aplicado
  na stack `spec46full`.
- **Verificação:** suíte completa com integração em banco `_test` descartável:
  `1498 passed, 10 skipped`. `ruff check .`, `mypy` e `export_prompt_schema.py --check` sem erros.

## Decisões do dono (2026-10-05)

- **Q1:** detalhe do Workday não revisado; adiado.
- **Q2:** piso de 30%, medido nas três últimas execuções completas.
- **Q3:** sim, como na spec. Fuso e autorização de trabalho viram `NOT_APPLICABLE`; país
  desconhecido só bloqueia se o perfil marcar `sponsorship_required`.
- **Q4:** embeddings só investigados; o job continua desligado.
- **Q5:** áreas-alvo `SOFTWARE_ENGINEERING` e `DATA`, contrato `full-time`.

## Cards

| Card | Estado | Commit | Falta |
|---|---|---|---|
| F50-01 | Script e linha de base entregues | `06199c0`, `55a5adf` | Gold rotulado por pessoa: 200 vagas, 50 por fonte. Precisão não medida. |
| F50-02 | Não iniciado | — | Bloqueado pelo gold. Mecânica a fazer: ligar por regra e reclassificar em lote. |
| F50-03 | Adiado (Q1) | — | A classificação pelo título na coleta entrou com o F50-04. |
| F50-04 | Entregue | `6e85c93` | Medir o aceite depois de três execuções completas por fonte. |
| F50-05 | Entregue | `3248382` | `ai` medido em 24,1% do catálogo, contra a meta de menos de 15%. Amostra rotulada de 100 vagas. |
| F50-06 | Não iniciado | — | Decisão Q3 tomada. Incrementa `RULES_VERSION`. |
| F50-07 | Entregue | `bce10f6` | `EXPLAIN ANALYZE` da fila em base de produção. |
| F50-08 | Não iniciado | — | Depende do F50-07, já entregue. |
| F50-09 | Entregue como `v3`, desligado | `bc6a4a3` | Rodar a avaliação `v1` contra `v3` no Groq e trocar `AI_ANALYSIS_PROMPT`. |
| F50-10 | Não iniciado | — | Depende do F50-07, já entregue. |
| F50-11 | Investigado | — | Registrar na spec: embeddings removidos de propósito em `9f54964` (F20-05, SPEC 43 §9). |
| F50-12 | Item 1 entregue | `51c7271` | Itens 2 e 3: medir e decidir. |

## Pontos abertos por card

**F50-04**
- A parcela por fonte usa as três últimas execuções completas, mesmo medidas com áreas-alvo
  antigas. Depois de trocar as áreas do perfil, o filtro leva até três execuções para refletir.
- As execuções do Hacker News agora terminam completas, então a fonte passa a poder fechar
  vagas que somem do tópico.

**F50-05**
- A palavra solta `ml` também saiu da regra de `ai`.
- Uma vaga que só cita LLM ou RAG recebe também `ai`.
- "React Native" também conta como `react`.
- Os identificadores novos têm espaço (`spring boot`, `react native`); um perfil que grave
  `springboot` não casa.

**F50-07**
- Faixas de recência: até 3, 7, 14 e 30 dias, copiadas de `_recency_measurement`.
- `input_hash` ainda inclui o dia; uma avaliação manual em outro dia grava uma linha nova.
- A fila roda um `NOT EXISTS` por vaga elegível a cada passada (cerca de 25 mil). Custo não
  medido.
- No primeiro ciclo depois do deploy, toda vaga que cruzou uma faixa desde a última avaliação
  volta à fila uma vez.

**F50-09**
- Já existia um prompt `v2` (F20-18); o novo é `v3`, com base no `v1`.
- Tokens de entrada estimados: 1.058 no `v1`, 865 no `v3`, redução de 18%. A meta de 800 não
  foi atingida. O que resta é o prompt de sistema, o snapshot da vaga e `deterministic_result`.
- Limites de itens: `strengths` 4, `risks` 5, `inferences` 3, `unknowns` 4.
- Teto de saída de 600 tokens só com `v3`. Risco: resposta truncada se o modelo gastar tokens
  de raciocínio; uma lista acima do limite falha em vez de ser cortada. Nenhum dos dois foi
  testado contra o provedor.

## Medições no `spec46full` (somente leitura, 2026-10-05)

- Cobertura das regras de conteúdo em 14.593 vagas com descrição: `seniority` 62,2%,
  `work_mode` 39,3%, `allowed_countries` 11,5%. A meta de 60% para país não é alcançável com
  as regras atuais.
- Catálogo nas áreas-alvo: 27,7% (6.970 de 25.124).
- Vagas das áreas-alvo com descrição e ao menos uma skill pela taxonomia nova: 4.279 de 5.177
  (82,7%). Isso é teto para `TECHNOLOGY_FIT` conhecido, não a taxa do fator.

## Ordem sugerida para o que falta

1. F50-06, F50-08 e F50-10. F50-08 e F50-10 tocam leitura e escrita de avaliações; fazer o
   F50-10 depois do F50-08.
2. Mecânica do F50-02, com a flag desligada.
3. F50-12 itens 2 e 3 e o registro do F50-11 na spec.
4. Atualizar o §1 e o status da SPEC 50.
