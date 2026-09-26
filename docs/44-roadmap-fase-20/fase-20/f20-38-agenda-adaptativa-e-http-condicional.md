# CARD F20-38 — Agenda por rendimento e orçamento de rede

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** D — Varredura produtiva
- **Depende de:** F20-35
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-04](../../40-roadmap-varredura-produtiva/fase-18/f18-04-agenda-adaptativa-e-http-condicional.md); [SPEC 39](../../39-spec-varredura-produtiva.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Dependências antigas de F17 foram fechadas por F20-01 a F20-03.

## Resultado

A coleta revisita fontes pelo frescor e rendimento, respeitando limites agregados e sem abandonar fontes pouco observadas.

## Escopo

- Estender scheduler/política existentes com next_due_at, motivo, limites min/max e custo recente; persistir cooldown por host/provedor.
- Compartilhar orçamento entre coleta, probe e descoberta. Aging e reserva inicial de 10% para exploração evitam exclusão permanente; teto de política prevalece.
- Requisições condicionais por representação/escopo com ETag/Last-Modified; validar Vary, cache-control e configuração.
- 429/503 respeitam Retry-After em segundos/data, backoff/jitter e estado após restart; falha de uma fonte não bloqueia outras.
- 304 mantém semântica de revalidação, não ausência. Até F20-39 (antigo F18-05) comprovar manifest completo, não usar 304 para encerrar vaga.
- Não adaptar por falta de marcação humana; registrar plano e permitir rollback ao agendamento fixo.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [ ] Nenhum host excede orçamento ao combinar fontes, sondas e descoberta.
- [ ] Fonte pouco observada volta a ser visitada dentro do máximo configurado
      quando há capacidade; insuficiência de orçamento gera atraso explícito,
      sem violar limites do provedor.
- [ ] Cooldown sobrevive a reinício; Retry-After não é ignorado.
- [ ] Mesma coorte mantém cobertura/recall e reduz custo ou atraso medido.

## Verificação

- **CI:** Relógio controlado: concorrência por host, fairness, cooldown/restart, 304, validadores incompatíveis e rollback.
- **Máquina de referência:** Comparação de sete dias antes/depois com requisições, bytes, frescor e cobertura sob mesmos tetos.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`acquisition/scheduling.py`, política HTTP dos coletores, worker e migrations de estado de host/representação.

## Contexto no código

`acquisition/scheduling.py` já é a política pura de agendamento, mas cobre menos do que
o card pede:

- `evaluate_gate` (linhas 117-149) já decide `DUE`/`NOT_SCHEDULED`/`NOT_DUE`/
  `BACKING_OFF`/`RATE_LIMITED` a partir de `SourceSchedulingState`, mas essa avaliação é
  **por fonte**, sem orçamento compartilhado por host/provedor: `worker.py:426-460`
  (`collect_enabled_sources`) itera as fontes uma a uma, cada uma com seu próprio
  `evaluate_gate`, sem noção de quantas outras fontes já gastaram o orçamento do mesmo
  host nesta janela.
- `SourceCheckpointModel` (`acquisition/models.py:359-384`) **já tem** as colunas `etag`
  e `last_modified`, mas nada no código as lê ou escreve — confirmado por busca
  (`grep -rn "\.etag\b\|\.last_modified\b\|If-None-Match\|304"` em `service.py`/
  `repository.py` não retorna nada). `acquisition/service.py:806-815` só promove
  `checkpoint.cursor`; os dois campos de HTTP condicional estão mortos.
- `backoff_delay`/`DEFAULT_BACKOFF_BASE`/`DEFAULT_BACKOFF_CEILING`
  (`scheduling.py:19-24`, `104-114`) dobram o atraso por falha consecutiva, mas não
  distinguem 429 (`Retry-After`) de qualquer outro erro, e o estado não sobrevive a um
  reinício além do que já está persistido em `SourceRunModel` (histórico de runs) — não
  há uma coluna "resume_at"/"next_due_at" persistida que o worker leia antes de decidir.
- Cada coletor já lê `Retry-After` e faz o retry dentro da própria chamada
  (`ashby.py:201-224`, mesmo padrão em `greenhouse.py`/`lever.py`/`remotive.py`), mas
  isso é o retry *dentro* de uma execução, não o cooldown entre execuções que o
  scheduler consulta — o card pede o segundo, persistido.
- `default_schedule_for_priority` (`scheduling.py:74-90`) já liga a prioridade da
  empresa (`Company.priority`, `companies/models.py:39`) à cadência padrão — a extensão
  de orçamento compartilhado deve continuar respeitando esse vínculo, não substituí-lo.
- Não há tabela de orçamento por host/provedor nem de descoberta (F20-36 também
  consome rede e ainda não existe) — o compartilhamento pedido pelo card é sobre uma
  estrutura nova.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/acquisition/scheduling.py` | `next_due_at`, motivo, cooldown por host, orçamento compartilhado |
| Alterar | `src/opportunity_radar/acquisition/service.py` | ler/escrever `etag`/`last_modified` no checkpoint; enviar `If-None-Match`/`If-Modified-Since` |
| Alterar | `src/opportunity_radar/worker.py` | `collect_enabled_sources` soma orçamento por host antes de disparar cada fonte |
| Criar | `migrations/versions/20260926_0040_host_budget_state.py` | tabela de estado de host/cooldown persistido (numeração indicativa; cabeça atual `20260925_0029`, 0030-0032 reservados ao Bloco B, 0033-0039 ao Bloco C) |
| Criar | `tests/backend/acquisition/test_host_budget_scheduling.py` | concorrência por host, fairness, cooldown/restart, 304, rollback |

## Interfaces

```python
# src/opportunity_radar/acquisition/scheduling.py
@dataclass(frozen=True, slots=True)
class HostBudgetState:
    """Estado persistido por host/provedor, sobrevive a reinício (SPEC 39 §7)."""

    host: str
    window_start: datetime
    requests_used: int
    requests_ceiling: int
    cooldown_until: datetime | None      # de Retry-After, em segundos ou data
    exploration_reserve_ratio: float = 0.10  # 10% para fontes novas/pouco observadas


@dataclass(frozen=True, slots=True)
class SourceSchedulingState:
    schedule: str | None
    timezone: str
    history: SourceRunHistory = SourceRunHistory()
    last_http_attempt_at: datetime | None = None
    minimum_run_interval_seconds: float | None = None
    # Novo: o host desta fonte e o estado de orçamento compartilhado já lido pelo caller.
    host: str | None = None
    host_budget: HostBudgetState | None = None


@dataclass(frozen=True, slots=True)
class ConditionalRequestHeaders:
    if_none_match: str | None
    if_modified_since: str | None


def next_due_at(
    state: SourceSchedulingState, *, now: datetime,
    backoff_base: timedelta = DEFAULT_BACKOFF_BASE,
    backoff_ceiling: timedelta = DEFAULT_BACKOFF_CEILING,
) -> tuple[datetime | None, str]:
    """Quando a fonte volta a ser elegível, e o motivo (para a UI/telemetria)."""


def evaluate_gate(
    state: SourceSchedulingState, *, now: datetime,
    backoff_base: timedelta = DEFAULT_BACKOFF_BASE,
    backoff_ceiling: timedelta = DEFAULT_BACKOFF_CEILING,
) -> CollectionGate:
    """Mesma assinatura de hoje; passa a consultar `state.host_budget` antes de `DUE`,
    devolvendo `CollectionGate.RATE_LIMITED` quando o host já esgotou o orçamento
    compartilhado, mesmo com a fonte individualmente due."""
```

## Passos

1. Escrever `tests/backend/acquisition/test_host_budget_scheduling.py` com relógio
   controlado cobrindo: duas fontes do mesmo host dividindo o orçamento, fairness para
   fonte pouco observada (reserva de 10%), cooldown que sobrevive a "reinício" (estado
   lido do banco, não da memória), 304 revalidando sem fechar vaga, e validadores
   incompatíveis (ETag de uma representação usado para outra).
2. Criar a migração `20260926_0040_host_budget_state.py` com a tabela de estado por
   host/provedor (contagem de requisições na janela, teto, `cooldown_until`), seguindo o
   formato de `20260925_0029_allowed_countries.py` (docstring, `revision`,
   `down_revision`, schema `acquisition`).
3. Estender `SourceSchedulingState` e `evaluate_gate` em `scheduling.py` para receber
   `host_budget: HostBudgetState | None` e devolver `RATE_LIMITED` quando o host está
   sem saldo, preservando o comportamento atual quando `host_budget` é `None` (não
   regredir `tests/backend/acquisition/test_scheduling.py`).
4. Implementar `next_due_at`, calculando o próximo instante elegível e o motivo
   (frescor, cooldown, orçamento) para expor na API/dashboard.
5. Em `acquisition/service.py:806-815`, promover `checkpoint.etag`/`checkpoint.last_modified`
   junto do cursor, lidos da resposta HTTP quando o coletor os expuser.
6. Adicionar `ConditionalRequestHeaders` e enviar `If-None-Match`/`If-Modified-Since` na
   próxima chamada quando o checkpoint tiver os validadores da mesma representação/
   escopo; respeitar `Vary` e não compartilhar validadores entre escopos diferentes.
7. Tratar HTTP 304 como revalidação daquela representação (não fechamento de vaga);
   isso é consumido pelo F20-39, que decide o que uma revalidação completa autoriza.
8. Persistir `Retry-After` (segundos ou data) e `cooldown_until` na tabela nova, lidos
   pelo scheduler antes de qualquer fonte do mesmo host ser avaliada como `DUE`.
9. Em `worker.py:collect_enabled_sources`, agregar o orçamento por host antes do loop
   de fontes, para que uma fonte falhando não bloqueie as demais do mesmo host nem
   estoure o teto do provedor.
10. Documentar no PR o plano de rollback para o agendamento fixo (reverter para
    `evaluate_gate` sem `host_budget` é reversível por configuração).
11. Rodar o comando de verificação e confirmar os quatro critérios de aceite.

## Testes a escrever

- `tests/backend/acquisition/test_host_budget_scheduling.py::test_two_sources_same_host_share_budget_without_exceeding_ceiling` — critério de aceite 1.
- `tests/backend/acquisition/test_host_budget_scheduling.py::test_low_yield_source_gets_revisited_within_configured_maximum` — critério de aceite 2, incluindo o caso de orçamento insuficiente gerando atraso explícito em vez de furar o teto.
- `tests/backend/acquisition/test_host_budget_scheduling.py::test_cooldown_survives_restart` — estado lido de uma nova instância do estado (simulando reinício) ainda respeita `cooldown_until`/`Retry-After` — critério de aceite 3.
- `tests/backend/acquisition/test_host_budget_scheduling.py::test_304_revalidates_without_asserting_full_coverage` — resposta 304 marca revalidação, não fecha vaga nem prova board completo.
- `tests/backend/acquisition/test_host_budget_scheduling.py::test_same_cohort_reduces_cost_or_delay_without_regressing_coverage` — critério de aceite 4, com fixture determinística (sem depender do acervo real).
- `tests/backend/acquisition/test_scheduling.py` (existente) — confirmar que continua verde sem `host_budget` (regressão zero no comportamento por fonte).

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
docker compose -p f20-38 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/acquisition/test_host_budget_scheduling.py tests/backend/acquisition/test_scheduling.py
docker compose -p f20-38 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-38 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
