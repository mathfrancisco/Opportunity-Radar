# CARD F20-43 — Orçamento de créditos Tavily e telemetria

- **Status:** Feito
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** E — Tavily
- **Depende de:** F20-42
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F19-03](../../42-roadmap-tavily/fase-19/f19-03-orcamento-de-creditos.md); [SPEC 41](../../41-spec-tavily.md)

## Ajustes da Fase 20

- Sem mudança de escopo. A Tavily é busca e extração, não LLM; o orçamento de créditos é separado da quota do Groq.

## Resultado

Uma execução da Tavily nunca gasta mais créditos do que o teto configurado; ao atingir o
teto, ela para de chamar a API e termina como execução parcial, com o gasto registrado.

## Contexto

Créditos da Tavily são finitos (1.000/mês no plano gratuito) e compartilhados entre
`/search` e `/extract`. Sem teto por execução, uma consulta ampla pode esgotar o plano em
poucas rodadas sem ninguém perceber até a fonte parar de funcionar por outro motivo.

## Escopo

- `tavily_credit_budget_per_run: int` em `Settings`, com um padrão conservador
  documentado no próprio campo.
- Cada chamada ao cliente do F20-42 (antigo F19-01) soma o custo que `include_usage=true` devolveu a um
  acumulador da execução corrente.
- Ao ultrapassar o teto, a execução para de iniciar novas chamadas a `/search` ou
  `/extract` e termina com `SourceRunStatus.PARTIAL` — nunca `FAILED`: o teto atingido é
  uma parada esperada de orçamento, não uma falha de rede ou de dado.
- Persistência do gasto: decidir entre estender `SourceRun` com um campo de créditos ou
  registrar em `metadata` estruturado existente, documentando a escolha no PR — nenhuma
  das duas duplica `http_requests`/`retry_count`, que continuam contando chamadas HTTP,
  não créditos.
- Estado do teto atingido reportado separado de 429 e de erro de rede — mesmo dado de
  `SourceRun`, mas com `error_code`/`summary` que deixam claro que a causa foi orçamento.

## Fora de escopo

- Compra ou gestão de plano Tavily fora do radar.
- Orçamento por host/provedor entre fontes diferentes — fica com o scheduler geral
  (`docs/39-spec-varredura-produtiva.md`, Frente E/F20-38 (antigo F18-04)), sem duplicar aqui.
- Redistribuir crédito não gasto de uma execução para outra.

## Notas de implementação

- O acumulador de créditos vive por execução (`SourceRun`), não globalmente — duas
  execuções concorrentes de fontes diferentes não competem pelo mesmo contador.
- `record_http_activity` do `SourceRun` já existe para HTTP; o card decide se créditos
  entram como contador irmão ou como campo de `metadata`, mas não reaproveita
  `http_requests` para isso — são unidades diferentes.

## Critérios de aceite

- [ ] O teto configurado é respeitado: nenhuma chamada nova começa depois de
      ultrapassado.
- [ ] Execução que atinge o teto termina `PARTIAL`, nunca `FAILED`.
- [ ] O gasto acumulado da execução fica auditável no `SourceRun` (campo ou metadata
      documentado).
- [ ] Teto atingido é distinguível de 429 e de erro de rede no relatório da execução.

## Verificação

- **CI:** teste de integração simulando várias chamadas com custo somado até ultrapassar
  o teto configurado, conferindo `PARTIAL` e o registro do gasto; teste de execução que
  fica abaixo do teto e termina `SUCCEEDED` normalmente.
- **Máquina de referência:** sem dependência de chamada real.

## Arquivos prováveis

- `src/opportunity_radar/platform/config.py`
- `src/opportunity_radar/acquisition/domain.py` (se estender `SourceRun`)
- `src/opportunity_radar/acquisition/tavily.py`
- `tests/acquisition/test_tavily_budget.py` (novo)

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/platform/config.py` | `tavily_credit_budget_per_run: int` com padrão conservador |
| Alterar | `src/opportunity_radar/acquisition/domain.py` | `SourceRun.credits_spent` + `record_credits()`; `AcquisitionErrorCode.CREDIT_BUDGET_EXCEEDED` novo (distinto de `SOURCE_QUOTA_EXHAUSTED`/433, que é limite do provedor, não teto do radar) |
| Alterar | `src/opportunity_radar/acquisition/models.py` | `SourceRunModel.credits_spent` (coluna nova, `class SourceRunModel` em `models.py:91`) |
| Criar | `migrations/versions/20260926_0050_source_run_credits.py` | `down_revision = "20260925_0029"` (head atual, confirmado — nenhum outro arquivo referencia `20260925_0029` como `down_revision`); numeração 0050+ é indicativa, não definitiva |
| Alterar | `src/opportunity_radar/acquisition/service.py` | `_copy_run` (`service.py:917`) grava `model.credits_spent = run.credits_spent`; ponto de decisão do teto na execução da Tavily |
| Alterar | `src/opportunity_radar/acquisition/tavily.py` | acumulador de créditos por execução usando o `TavilyClient` do F20-42 |
| Criar | `tests/backend/acquisition/test_tavily_budget.py` | testes deste card (não `tests/acquisition/`, ver nota do F20-42) |

## Interfaces

```python
# platform/config.py
# 1000 créditos/mês no plano gratuito (SPEC 41 §3.3); teto conservador por execução para
# sobrar margem para várias execuções antes do fim do ciclo de faturamento.
tavily_credit_budget_per_run: int = 100

# acquisition/domain.py — StrEnum AcquisitionErrorCode: acrescentar
CREDIT_BUDGET_EXCEEDED = "CREDIT_BUDGET_EXCEEDED"
# distinto de SOURCE_QUOTA_EXHAUSTED (F20-42, 433 = limite mensal do provedor
# esgotado) e de SOURCE_RATE_LIMITED (429 = throttling passageiro); aqui a causa é o
# teto por execução que o próprio radar configurou.

# acquisition/domain.py — SourceRun (dataclass, domain.py:~257)
@dataclass(slots=True)
class SourceRun:
    ...
    credits_spent: int = 0

    def record_credits(self, amount: int) -> None:
        self._require_running()
        if amount < 0:
            raise ValueError("credits cannot be negative")
        self.credits_spent += amount

# acquisition/tavily.py — acumulador usado pelo collector do F20-44 antes de cada chamada
class TavilyBudgetGuard:
    def __init__(self, *, budget: int) -> None: ...
    @property
    def spent(self) -> int: ...
    def would_exceed(self, run: SourceRun) -> bool:
        return run.credits_spent >= self._budget
    def record(self, run: SourceRun, response_usage: TavilyUsage | None) -> None:
        if response_usage is not None and response_usage.credits is not None:
            run.record_credits(response_usage.credits)
```

## Exemplos

O acumulador lê o mesmo bloco `usage` que o F20-42 já parseia
(`TavilyUsage`, SPEC 41 §3.3):

```json
{
  "...": "corpo de /search ou /extract, ver F20-42 seção Exemplos",
  "usage": {"...": "a confirmar — nome exato da chave de créditos; ver F20-42"}
}
```

Fluxo de teto atingido (pseudocódigo do que o `SourceRun` registra ao final):

```python
run.record_credits(cost_of_last_call)  # soma o custo desta chamada
if guard.would_exceed(run):
    run.finish(
        SourceRunStatus.PARTIAL,
        error=AcquisitionError(
            AcquisitionErrorCode.CREDIT_BUDGET_EXCEEDED,
            f"tavily_credit_budget_per_run atingido: {run.credits_spent} créditos gastos",
        ),
    )
```

## Passos

1. Escrever `tests/backend/acquisition/test_tavily_budget.py` para cada critério de
   aceite (ver "Testes a escrever") — falham até o acumulador existir.
2. Adicionar `tavily_credit_budget_per_run` em `Settings`.
3. Adicionar `SourceRun.credits_spent` e `record_credits()` em `domain.py`.
4. Adicionar `AcquisitionErrorCode.CREDIT_BUDGET_EXCEEDED` em `domain.py`; registrar no
   PR por que não reutiliza `SOURCE_QUOTA_EXHAUSTED` (causas diferentes: provedor vs.
   teto do radar).
5. Criar a migração `20260926_0050_source_run_credits.py` (`op.add_column` em
   `acquisition.source_run`, `credits_spent integer not null default 0`, mais um
   `CheckConstraint` próprio — não reaproveitar `ck_source_run_counters`, que é de
   contadores de HTTP).
6. Adicionar `credits_spent` em `SourceRunModel` (`models.py:91`), com o mesmo padrão
   de `items_announced`/`complete` já existentes na classe.
7. Atualizar `_copy_run` (`service.py:917`) para copiar `run.credits_spent`.
8. Implementar `TavilyBudgetGuard` (ou lógica equivalente) em `tavily.py`, chamado pelo
   `TavilySearchCollector` do F20-44 antes de cada nova chamada a `/search`/`/extract`.
9. Ao ultrapassar o teto, parar de iniciar chamadas novas e terminar a execução como
   `PARTIAL` com `CREDIT_BUDGET_EXCEEDED` (nunca `FAILED`).
10. Escrever os testes de integração de soma de custo e teto até verdes.
11. `ruff check .` e `mypy`.

## Testes a escrever

`tests/backend/acquisition/test_tavily_budget.py`:

- `test_run_stays_below_budget_finishes_succeeded` — cobre a execução que não atinge o
  teto e termina `SUCCEEDED` normalmente (ver "Verificação").
- `test_accumulated_cost_stops_new_calls_at_budget` — cobre "nenhuma chamada nova
  começa depois de ultrapassado".
- `test_budget_exceeded_finishes_partial_never_failed` — cobre "Execução que atinge o
  teto termina `PARTIAL`, nunca `FAILED`".
- `test_credits_spent_is_auditable_on_source_run` — cobre "gasto acumulado ... fica
  auditável no `SourceRun`" (lê `SourceRunModel.credits_spent` após persistir).
- `test_budget_exceeded_error_code_differs_from_rate_limit_and_network_error` — cobre
  "Teto atingido é distinguível de 429 e de erro de rede".
- `test_record_credits_rejects_negative_amount` — cobre a validação de `record_credits`.

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
docker compose -p f20-43 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/acquisition/test_tavily_budget.py
docker compose -p f20-43 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-43 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
