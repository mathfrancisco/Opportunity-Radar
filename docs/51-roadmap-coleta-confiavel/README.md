# Roadmap 51 — coleta confiável e busca verificável

**Status geral: em implementação, nenhum card concluído (2026-10-07). Janela de sete dias aberta em 2026-10-07, no merge do PR #68.** O estado por card
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

## Estado por card (2026-10-07)

Nenhum card tem todos os critérios de aceite com teste ou evidência. "Parcial" quer dizer
código mesclado em `main` com critério ainda aberto.

| Card | Estado | O que falta |
| --- | --- | --- |
| F51-01 | Parcial | Três execuções completas por fonte e contagem de descrição útil: vêm da janela de sete dias, que não foi aberta |
| F51-02 | Parcial | Recall com amostra humana; observação da janela de sete dias |
| F51-03 | Aberto | Aprovação do dono por fonte Workday e resposta real por fonte |
| F51-04 | Critérios com teste | AC02 no PR #45; AC01, AC03, AC04, AC05a e AC05b no PR #55 (`test_workday_detail_budget_integration.py`), sem mudança de código. Os testes não foram conferidos quebrando o código de propósito. O fechamento depende da janela do F51-18 |
| F51-05 | Parcial | Script de piloto e backfill em `main` (PR #62); a recoleta não apaga mais a descrição (PR #65). Falta o piloto nos 5 tenants, que depende da aprovação por fonte do F51-03 |
| F51-06 | Critérios com teste | AC03 e AC04 no PR #57 (`test_source_run_claim_fencing.py`). AC01, AC02 e AC05 têm teste anterior com nome diferente do proposto no card |
| F51-07 | Parcial | Claim, lease, fencing e recuperação ligados ao serviço, ao worker, ao `scripts/collect.py` e à rota HTTP (PR #57), atrás de `collection_claim_enabled` (padrão ligado). O fechamento passou a ser guardado pelo token de fencing (AC02, PR #65). Execução abandonada com lease vencido volta à fila na passada seguinte (PR #68). Abertos: os eventos do card são registros de log; o custo do commit por item não foi medido |
| F51-08 | Critérios com teste | Um run por host, 4 hosts ao mesmo tempo por padrão, configurável (PR #64). Teste de banco real de uma passada concorrente no PR #68. Medido na base de dev em 2026-10-07: 139 fontes em 10 min 48 s, nenhum `429`. O fechamento depende da janela do F51-18 |
| F51-09 | Parcial | Causa do consumo sem registro encontrada (ver o card F51-12). Invariante de reserva testado e dois caminhos latentes corrigidos (PR #54). Teste do `operation_cohort` em `main` (PR #58). AC05 alinhado no PR #68: o código já dava os números do card quando a operação que caiu é mais velha que a carência; o teste anterior punha as duas dentro dela |
| F51-10 | Critérios com teste | Erro por item, quota global adiada e dois workers no mesmo item (PR #58); AC04 e AC03 no PR #65; AC06 no PR #68, com claim de sugestão por advisory lock do PostgreSQL. O fechamento depende da janela do F51-18 |
| F51-11 | Em andamento | Gold confirmado pelo dono (PRs #48 e #49). Nenhuma regra por descrição passa no portão: de 0 a 8 emissões por regra contra o mínimo de 20; 12 casos `unknown` e Remotive com 18 vagas bloqueiam a população. Falta amostra com suporte e rótulo novo do dono |
| F51-12 | Parcial | Em `main` (PR #52): fila automática sem vaga fechada nem descrição de até 200 caracteres; chave de análise sem versão de regra. Em `main` (PR #58): teto diário com folga de 20%, sugestão só para campo `UNKNOWN` em vaga de topo, ACs 01 a 06. Falta a definição de "resultado útil" do AC06 |
| F51-13 | Parcial | Contratos de inventário em `main` (PR #61). Os critérios não foram conferidos um a um nesta sessão; na passada de 2026-10-07 o worker recebeu 11 respostas `304` |
| F51-14 a F51-16 | **Adiados** | Decisão do dono em 2026-10-06, como a SPEC 51 §9 permite: sem fonte prioritária aprovada nem evidência de necessidade. Não bloqueiam o núcleo |
| F51-17 | Parcial | Benchmark pareado e grupo frio em `main` (PR #62). O reinício real não foi rodado: o manifesto congelado exige gold com dois revisores, que depende do dono |
| F51-18 | Em observação | Janela de sete dias aberta em 2026-10-07; fecha em 2026-10-14. O pacote é montado com os dados da janela |

Atualização de 2026-10-06 (segunda sessão): só o F51-04 avançou, com o teste do AC02. Os
demais cards de código (F51-05 a F51-10, F51-12, F51-13, F51-17) não foram tocados.

Atualização de 2026-10-06 (terceira sessão, PRs #48 e #49): o dono aprovou as duas
propostas de rótulo e o portão do F51-11 rodou com o gold confirmado; nenhuma regra passou e
`GATED_RULES` não mudou. O F51-12 ganhou a medição de partida do uso de IA. Nenhum outro
card da SPEC 51 foi tocado: F51-04 a F51-10, F51-13, F51-17 e F51-18 continuam como na
tabela.

Atualização de 2026-10-07 (quarta sessão, PRs #51 a #57 mesclados, #58 aberto): F51-04 e
F51-06 ficaram com teste para todos os critérios; o F51-07 foi ligado ao serviço e ao worker
com uma decisão aberta (fence no fechamento); F51-09, F51-10 e F51-12 avançaram e dependem
do PR #58. F51-05, F51-08, F51-13 e F51-17 não foram tocados. A amostra nova do F51-11 foi
preparada e não publicada. Nenhum card foi marcado como concluído: todos dependem da janela
de sete dias ou têm critério aberto.

Atualização de 2026-10-07 (quinta sessão, PRs #65 a #68): ver o
[checkpoint](implementation-checkpoint.md). Nenhum card foi marcado como concluído: os que têm
teste para todos os critérios dependem da janela, e F51-03, F51-05, F51-11, F51-12 e F51-17
dependem de decisão ou rótulo do dono.

**Janela de sete dias: aberta em 2026-10-07, no merge do PR #68**, o último PR de código da
SPEC 51. Fecha em 2026-10-14. Qualquer PR de código da SPEC 51 mesclado antes disso reabre a
janela na data do merge. O pacote do F51-18 (`f51-18-runbook-offline.md`) só pode ser
preenchido com os dados observados até o fim da janela.

## Ordem de execução crítica

Começar por F51-01, F51-02, F51-03, F51-06, F51-09 e F51-13. Não ativar detalhe Workday,
concorrência, regras V4, adaptadores ou browser sem o respectivo contrato de medição, fonte
permitida e rollback. F51-18 consolida o núcleo obrigatório. F51-14 a F51-16 são expansão condicional: exigem fonte prioritária aprovada e evidência de necessidade; podem ficar adiados com decisão registrada sem impedir o fechamento do núcleo. F51-17 pode iniciar baseline em paralelo, mas sua medição final vem após o enriquecimento/backfill aplicável.

## Definition of Done do roadmap

Um card só pode ser marcado Concluído quando todos os seus ACs forem evidenciados, os cenários negativos
relevantes ao card forem testados, as dependências estiverem fechadas ou registradas como exceção, e a mudança puder ser
desligada sem corromper presença, deduplicação ou decisão determinística. Ver
[SPEC 51, seção 9](../51-spec-coleta-confiavel-e-busca.md#9-definition-of-done-da-spec).
