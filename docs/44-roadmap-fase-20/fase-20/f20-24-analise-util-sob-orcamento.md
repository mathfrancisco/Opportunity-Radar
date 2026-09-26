# CARD F20-24 — Análise útil sob orçamento de quota

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-39, F20-17, F20-16, F20-12
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-06](../../40-roadmap-varredura-produtiva/fase-18/f18-06-analise-util-sob-orcamento.md), [F16-04](../../38-roadmap-ia-e-busca/fase-16/f16-04-aquecimento-e-fila-por-valor.md)

## Ajustes da Fase 20

- O orçamento é a quota diária do Groq (F20-12), não tempo de GPU.
- Reservar parte da quota para análise pedida na UI; o worker nunca consome essa reserva.
- A fila por valor do F16-04 (elegível, score, frescor, prioridade da empresa) entra aqui; o aquecimento não.
- Arquivos: `src/opportunity_radar/worker.py` (`analyze_pending`), `src/opportunity_radar/matching/service.py` (seleção da fila), `src/opportunity_radar/matching/repository.py`, `src/opportunity_radar/platform/config.py` (`worker_analyze_batch_size`, `worker_analyze_verdicts`, novo `ai_interactive_reserve_requests: int = 100`), `src/opportunity_radar/platform/ai/quota.py` (reserva interativa).
- Reserva interativa: o worker chama `QuotaGuard.reserve` com teto `day_requests - ai_interactive_reserve_requests`; a análise pedida pela UI usa o limite cheio.
- Sugestões de campo deste card são as do F20-23; não criar outra tabela.
- Testes: `tests/backend/matching/test_analysis_queue.py` (ordem por valor, pulo sem mudança, reserva interativa) e `tests/backend/platform/ai/test_quota.py`.

## Resultado

A IA ajuda a decidir sobre vagas novas/alteradas e lacunas relevantes com evidência, dentro da quota diária do Groq.

## Escopo

- Usar identidade completa e reuso do F20-16; mesma vaga sem mudança não paga nova inferência.
- Priorizar recomendadas/alta prioridade e revisão com lacuna; aging e amostra de elegíveis pouco priorizadas avaliam perdas do funil.
- Orçamentos configuráveis de chamadas, tokens e tempo por ciclo/dia. Limite adia com motivo e registra custo de falhas.
- Sugestões de campo ficam separadas do canônico; aplicar exige revisão, trecho/origem e correção versionada. IA não muda score nem navega.
- Medir riscos/lacunas confirmados, falsos alertas, custo por análise útil e tempo humano por amostra. Não tratar clique ou ausência de candidatura como relevância.
- Rollback da política mantém análises históricas; sem Groq, coleta/matching/Inbox continuam.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [ ] Revisita sem mudança não chama IA; alteração material invalida reuso.
- [ ] Budget adia sem perder oportunidade nem bloquear o worker.
- [ ] Sugestão não altera campo/matching antes da confirmação.
- [ ] Relatório compara fila atual e política nova com suporte e custo/qualidade.

## Verificação

- **CI:** Adaptador contador, clock controlado, budget, aging, indisponibilidade e confirmação concorrente com expected_version.
- **Máquina de referência:** Amostra estratificada julgada pelo operador e carga real combinada; efeito sem suporte é inconclusivo.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`matching/service.py`, repository, worker, métricas e painel de análise; esquema separado de sugestões/correções.

## Contexto no código

O job atual é `worker.py:221-296` (`analyze_pending`): ele lê o lote com
`MatchingService.pending_analysis_ids` (`matching/service.py:414-434`), que delega para
`SqlAlchemyMatchingRepository.pending_analysis_ids` (`matching/repository.py:297-347`). Hoje
a fila ordena só por `verdict_rank` (posição em `ANALYSIS_VERDICT_PRIORITY`), depois
`OpportunityModel.published_at` desc, depois `assessed_at` desc, depois `id` — não há peso de
score, prioridade da empresa nem amostra de elegíveis pouco priorizadas. `Company.priority`
já existe (`companies/models.py:39`) e `CompanyPriority`/`company_priority_scores` já
alimentam o score do matching (`matching/domain.py:138`, `224-248`), mas nenhum dos dois
entra na ordenação da fila de análise.

`platform/config.py:51-89` já tem `worker_analyze_batch_size` (default 10),
`worker_analyze_verdicts` e os `analysis_retry_*`, mas **não** tem
`ai_interactive_reserve_requests`. O pacote `platform/ai/` (com `quota.py`, `router.py`
etc.) ainda não existe nesta árvore — é criado pelo F20-12 (`QuotaLimits`, `QuotaGuard`,
`Reservation`, ver a seção "Interfaces" do card F20-12) e usado pelo F20-17. Este card
depende dos dois; se for iniciado antes de ambos aterrarem, tratar `quota.py`/`router.py`
como "Criar" em vez de "Alterar" e registrar a inversão de ordem no PR. O worker hoje ainda
usa `GpuAdmission`/`GPU_ADMISSION` (era Ollama, `worker.py:203-231`) — sua remoção é escopo de
outro card (F20-04 a F20-11), não deste.

Sugestões de campo (F20-23) ficam em `opportunities.field_suggestion`
(`opportunities/suggestions.py`, ainda não criado) — este card não cria outra tabela, só
consome a fila de sugestões pendentes quando ela existir.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/worker.py` | `analyze_pending` chama `QuotaGuard.reserve` com o teto reduzido para o worker |
| Alterar | `src/opportunity_radar/matching/service.py` | `pending_analysis_ids`/`count_pending_analysis` recebem os novos critérios de ordenação |
| Alterar | `src/opportunity_radar/matching/repository.py` | ordenação por valor (score, prioridade da empresa, frescor) e amostra de aging |
| Alterar | `src/opportunity_radar/platform/config.py` | novo `ai_interactive_reserve_requests: int = 100` |
| Alterar | `src/opportunity_radar/platform/ai/quota.py` | reserva com teto `day_requests - ai_interactive_reserve_requests` para o worker (caminho criado pelo F20-12; se ainda não existir, tratar como "Criar" e registrar no PR) |
| Criar | `tests/backend/matching/test_analysis_queue.py` | ordem por valor, pulo sem mudança material, reserva interativa |
| Alterar | `tests/backend/platform/ai/test_quota.py` | teto reduzido do worker vs. limite cheio da UI (caminho criado pelo F20-12) |

## Interfaces

```python
# src/opportunity_radar/platform/config.py
class Settings(BaseSettings):
    ...
    worker_analyze_batch_size: int = 10
    worker_analyze_verdicts: str = "HIGH_PRIORITY,RECOMMENDED,WATCHLIST,REVIEW_REQUIRED"
    # Parte da quota diária do Groq reservada para análise pedida na UI; o worker nunca
    # consome essa reserva (SPEC 43; card F20-12 define QuotaGuard.reserve).
    ai_interactive_reserve_requests: int = 100
    # Fração do lote do worker dedicada a amostra de elegíveis pouco priorizadas, para medir
    # perdas do funil (SPEC 39 secao 9).
    worker_analyze_aging_sample_ratio: float = 0.10


# src/opportunity_radar/matching/repository.py
def pending_analysis_ids(
    self,
    *,
    eligible_verdicts: Sequence[str],
    limit: int,
    now: datetime,
    cooldown: timedelta,
    attempt_window: timedelta,
    max_attempts: int,
    aging_sample_ratio: float = 0.0,
) -> Sequence[UUID]:
    """Ordena por verdict_rank, depois por CompanyPriority e score do assessment,
    depois por frescor (published_at), reservando `aging_sample_ratio` do lote para
    elegíveis fora do topo do ranking (aging da SPEC 39 secao 9)."""


# src/opportunity_radar/platform/ai/quota.py (F20-12; usado por este card)
class QuotaGuard:
    def reserve(
        self, model: str, *, requests: int = 1, tokens_estimate: int = 0,
        ceiling_requests: int | None = None,
    ) -> "Reservation":
        """`ceiling_requests` deixa o chamador expor um teto menor que o do Free Plan —
        o worker passa `day_requests - settings.ai_interactive_reserve_requests`; a
        análise pedida na UI não passa `ceiling_requests` e usa o limite cheio."""
```

## Passos

1. Escrever `tests/backend/matching/test_analysis_queue.py` cobrindo: ordem por valor
   (score/prioridade/frescor), pulo de vaga sem mudança material (reuso do F20-16), e
   amostra de aging respeitando `aging_sample_ratio`.
2. Estender `SqlAlchemyMatchingRepository.pending_analysis_ids`
   (`matching/repository.py:297`) para juntar `Company`/`CompanySource` via
   `OpportunityModel` e ordenar por prioridade da empresa e pelo score do
   `MatchAssessmentModel` antes do `published_at`.
3. Reservar uma fração do lote (`aging_sample_ratio`) para IDs fora do topo do
   ranking, sorteados de forma determinística pelo `id` para reprodutibilidade em teste.
4. Adicionar `ai_interactive_reserve_requests` e `worker_analyze_aging_sample_ratio` a
   `Settings` (`platform/config.py`).
5. Em `MatchingService.pending_analysis_ids`/`count_pending_analysis`
   (`matching/service.py:414-451`), propagar `aging_sample_ratio`.
6. Em `worker.py:analyze_pending`, antes de cada chamada ao adapter, chamar
   `QuotaGuard.reserve(..., ceiling_requests=settings.day_requests - settings.ai_interactive_reserve_requests)`;
   se a reserva falhar, pular a vaga com motivo "budget" e não descartar a oportunidade
   (ela volta na próxima passagem).
7. Confirmar que a análise pedida pela UI (endpoint síncrono, fora deste job) chama
   `QuotaGuard.reserve` sem `ceiling_requests`, usando o limite cheio.
8. Escrever/atualizar `tests/backend/platform/ai/test_quota.py` para o teto reduzido do
   worker vs. o limite cheio da UI, com clock controlado.
9. Rodar o comando de verificação abaixo e confirmar os quatro critérios de aceite.

## Testes a escrever

- `tests/backend/matching/test_analysis_queue.py::test_pending_analysis_orders_by_value` — empresa de alta prioridade e score maior vêm primeiro, mesmo com `published_at` mais antigo.
- `tests/backend/matching/test_analysis_queue.py::test_pending_analysis_skips_without_material_change` — reexecutar `evaluate`/`analyze` sobre a mesma vaga sem mudança não gera novo `assessment_id` pendente (cobre "revisita sem mudança não chama IA").
- `tests/backend/matching/test_analysis_queue.py::test_pending_analysis_reserves_aging_sample` — com `aging_sample_ratio=0.1` e lote de 10, ao menos 1 id fora do topo do ranking aparece no lote.
- `tests/backend/platform/ai/test_quota.py::test_worker_reservation_respects_interactive_ceiling` — `QuotaGuard.reserve(ceiling_requests=...)` nega quando o uso do dia já passou do teto reduzido, mesmo com saldo no limite cheio.
- `tests/backend/platform/ai/test_quota.py::test_interactive_reservation_uses_full_limit` — chamada sem `ceiling_requests` só nega no limite cheio do Free Plan.

## Não fazer

- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não habilitar fonte sem passar pelo gate de homologação.
- Não fazer chamada real a boards, Groq ou Tavily no CI; usar `httpx.MockTransport` ou os servidores falsos de `tests/e2e/`.
- Não adicionar dependência nova sem registrar o motivo no PR.
- Não usar LLM neste card, salvo quando a seção "Ajustes da Fase 20" disser o contrário.

## Como trabalhar este card

1. Ler "Ajustes da Fase 20" primeiro: eles prevalecem sobre o texto herdado.
2. Ler "Arquivos prováveis" e confirmar cada caminho com `ls`/`grep` antes de editar; caminho inexistente vira nota no PR.
3. Escrever primeiro os testes dos critérios de aceite, depois o código.
4. IDs antigos no texto aparecem como `F20-xx (antigo F1x-yy)`; a tabela completa está no README da Fase 20.
5. O que depende do acervo real ("Máquina de referência") é medido fora do CI e colado no PR.

## Comando de verificação

```bash
docker compose -p f20-24 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/matching/test_analysis_queue.py tests/backend/platform/ai/test_quota.py
docker compose -p f20-24 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-24 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
