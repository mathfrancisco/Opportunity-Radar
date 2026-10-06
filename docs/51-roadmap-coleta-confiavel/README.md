# Roadmap 51 — coleta confiável e busca verificável

**Status geral: em implementação, nenhum card concluído (2026-10-06).** O estado por card
está em "Estado por card" abaixo. Os cards abaixo decompõem a
[SPEC 51](../51-spec-coleta-confiavel-e-busca.md). O texto de cada card continua descrevendo o
plano; o que já existe em código e o que falta está no
[checkpoint de implementação](implementation-checkpoint.md).

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

## Estado por card (2026-10-06)

Nenhum card tem todos os critérios de aceite com teste ou evidência. "Parcial" quer dizer
código mesclado em `main` com critério ainda aberto.

| Card | Estado | O que falta |
| --- | --- | --- |
| F51-01 | Parcial | Três execuções completas por fonte e contagem de descrição útil: vêm da janela de sete dias, que não foi aberta |
| F51-02 | Parcial | Recall com amostra humana; observação da janela de sete dias |
| F51-03 | Aberto | Aprovação do dono por fonte Workday e resposta real por fonte |
| F51-04 | Parcial | AC02 tem teste (PR #45, `test_host_budget_reservation_integration.py`). Falta conferir se AC01, AC03, AC04, AC05a e AC05b têm o teste que o card propõe |
| F51-05 | Não iniciado | Script de piloto e backfill com dry-run; piloto nos 5 tenants (autorizado em stack descartável) |
| F51-06 | Parcial | AC03 (disputa de duas execuções) e AC04 (integração em banco) |
| F51-07 | Parcial | Tabela e métodos de claim existem; falta ligar ao serviço e testar |
| F51-08 | Não iniciado | Worker ainda em série. Decisão: um run por host, concorrência padrão de 4 hosts, configurável |
| F51-09 | Parcial | Teste do relatório de coorte (`operation_cohort`) |
| F51-10 | Parcial | Testes de erro por item, quota global e concorrência |
| F51-11 | Em andamento | Proposta de rótulos e comando do portão prontos (PR #41); falta a confirmação do dono |
| F51-12 | Parcial | Só o teto de requisições no router foi feito |
| F51-13 | Não iniciado | Paginação, 304 e run parcial |
| F51-14 a F51-16 | **Adiados** | Decisão do dono em 2026-10-06, como a SPEC 51 §9 permite: sem fonte prioritária aprovada nem evidência de necessidade. Não bloqueiam o núcleo |
| F51-17 | Parcial | Benchmark pareado, latência fria (cinco reinícios do `postgres` em stack descartável) e gold no formato novo com revisão do dono |
| F51-18 | Parcial | Validador pronto; falta montar o pacote e abrir a janela de sete dias |

Atualização de 2026-10-06 (segunda sessão): só o F51-04 avançou, com o teste do AC02. Os
demais cards de código (F51-05 a F51-10, F51-12, F51-13, F51-17) não foram tocados.

**Janela de sete dias: não aberta.** A regra é abrir no merge do último PR de código da SPEC
51. Em 2026-10-06 só o PR #41 (leitor do gold) tocou código desta SPEC; F51-05, F51-07,
F51-08 e F51-13 ainda têm código por escrever, e abrir a janela antes deles deixaria a
evidência do F51-18 sem valor.

## Ordem de execução crítica

Começar por F51-01, F51-02, F51-03, F51-06, F51-09 e F51-13. Não ativar detalhe Workday,
concorrência, regras V4, adaptadores ou browser sem o respectivo contrato de medição, fonte
permitida e rollback. F51-18 consolida o núcleo obrigatório. F51-14 a F51-16 são expansão condicional: exigem fonte prioritária aprovada e evidência de necessidade; podem ficar adiados com decisão registrada sem impedir o fechamento do núcleo. F51-17 pode iniciar baseline em paralelo, mas sua medição final vem após o enriquecimento/backfill aplicável.

## Definition of Done do roadmap

Um card só pode ser marcado Concluído quando todos os seus ACs forem evidenciados, os cenários negativos
relevantes ao card forem testados, as dependências estiverem fechadas ou registradas como exceção, e a mudança puder ser
desligada sem corromper presença, deduplicação ou decisão determinística. Ver
[SPEC 51, seção 9](../51-spec-coleta-confiavel-e-busca.md#9-definition-of-done-da-spec).
