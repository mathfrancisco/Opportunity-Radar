# Roadmap 51 — coleta confiável e busca verificável

**Status geral: Planejado.** Os cards abaixo decompõem a
[SPEC 51](../51-spec-coleta-confiavel-e-busca.md). Nenhum card declara código, configuração ou
teste já executado nesta fase.

| Bloco | Cards | Resultado de saída |
| --- | --- | --- |
| Medir antes de mudar | F51-01, F51-02 | baseline repetível e métricas por fonte |
| Conteúdo Workday | F51-03 a F51-05 | piloto autorizado e backfill idempotente |
| Worker confiável | F51-06 a F51-08 | ownership, retomada, concorrência e quota segura |
| IA consultiva | F51-09 a F51-12 | telemetria completa, fila justa e regras validadas |
| Extração em camadas | F51-13 a F51-16 | inventário preservado e expansão aprovada |
| Busca e operação | F51-17, F51-18 | avaliação FTS e rollout verificável |

| Card | Prioridade | Dependências | Resumo |
| --- | --- | --- | --- |
| [F51-01](cards/f51-01-baseline-benchmark-auditavel.md) | P0 | — | Baseline por fonte e amostra auditável |
| [F51-02](cards/f51-02-metricas-conteudo-frescor-recall.md) | P0 | F51-01 | Métricas persistentes e contratos de completude |
| [F51-03](cards/f51-03-workday-termos-e-contratos-reais.md) | P0 | F51-01 | Termos e resposta real por fonte Workday |
| [F51-04](cards/f51-04-workday-cooldown-orcamento-counters.md) | P0 | F51-03 | 429, quota e telemetria de detalhe |
| [F51-05](cards/f51-05-workday-piloto-backfill.md) | P1 | F51-02, F51-03, F51-04 | Piloto e backfill seguro |
| [F51-06](cards/f51-06-worker-relogio-deadline-progresso.md) | P0 | F51-01 | Relógio por fonte, deadline e cancelamento |
| [F51-07](cards/f51-07-worker-claim-lease-recuperacao.md) | P0 | F51-06 | Claim, lease e fencing sem fila nova |
| [F51-08](cards/f51-08-worker-concorrencia-host-orcamento.md) | P0 | F51-04, F51-07 | Concorrência limitada e reserva atômica |
| [F51-09](cards/f51-09-telemetria-ia-completa.md) | P0 | F51-01 | Tentativas IA completas e sem PII |
| [F51-10](cards/f51-10-fila-ia-justa-retry.md) | P1 | F51-09 | Seleção justa, defer e retry |
| [F51-11](cards/f51-11-gold-regras-v4-reclassificacao.md) | P1 | F51-01 | Gold humano e regras V4 |
| [F51-12](cards/f51-12-ia-seletiva-cache-quotas.md) | P1 | F51-09, F51-10 | IA só para ambiguidade |
| [F51-13](cards/f51-13-contratos-inventario-ats.md) | P0 | F51-02 | Paginação, 304 e run parcial |
| [F51-14](cards/f51-14-descoberta-sitemap-frontier.md) | P2 | F51-13 | Descoberta revisável e segura |
| [F51-15](cards/f51-15-adaptadores-html-priorizados.md) | P2 | F51-13 | Adaptadores HTML por fonte |
| [F51-16](cards/f51-16-browser-seletivo-js.md) | P2 | F51-13, F51-15 | Browser opt-in para JS comprovado |
| [F51-17](cards/f51-17-benchmark-fts-relevancia.md) | P1 | F51-01, F51-02, F51-05, F51-11 | Qualidade de busca FTS |
| [F51-18](cards/f51-18-piloto-operacional-rollout.md) | P0 | F51-05, F51-08, F51-12, F51-13, F51-17 | Evidência operacional e fechamento |

## Ordem de execução crítica

Começar por F51-01, F51-02, F51-03, F51-06, F51-09 e F51-13. Não ativar detalhe Workday,
concorrência, regras V4, adaptadores ou browser sem o respectivo contrato de medição, fonte
permitida e rollback. F51-18 consolida o núcleo obrigatório. F51-14 a F51-16 são expansão condicional: exigem fonte prioritária aprovada e evidência de necessidade; podem ficar adiados com decisão registrada sem impedir o fechamento do núcleo. F51-17 pode iniciar baseline em paralelo, mas sua medição final vem após o enriquecimento/backfill aplicável.

## Definition of Done do roadmap

Um card só pode ser marcado Concluído quando todos os seus ACs forem evidenciados, os cenários negativos
relevantes ao card forem testados, as dependências estiverem fechadas ou registradas como exceção, e a mudança puder ser
desligada sem corromper presença, deduplicação ou decisão determinística. Ver
[SPEC 51, seção 9](../51-spec-coleta-confiavel-e-busca.md#9-definition-of-done-da-spec).
