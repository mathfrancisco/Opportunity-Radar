# CARD F20-25 — Fila de homologação

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-05](../../38-roadmap-ia-e-busca/fase-17/f17-05-fila-de-homologacao.md); [SPEC 37](../../37-spec-busca.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Dependências antigas F17-02, F17-04 e F17-07 são fechadas pelo F20-03.

## Resultado

O operador homologa dezenas de propostas em sequência numa única tela — testar,
revisar termos, habilitar, próxima — sem abrir fonte por fonte, e sem que nenhum passo do
gate seja pulado.

## Contexto

Com o F20-03 (antigo F17-04), o número de propostas sobe de 6 para algumas dezenas. A tela de fontes da
Fase 14 homologa uma por vez, abrindo o painel de cada cartão. A sonda do F14-06 impõe 60 s
entre testes da mesma fonte, não entre fontes diferentes.

## Escopo

- Visão **"Fila de homologação"** na tela de fontes: lista das propostas desabilitadas,
  ordenadas pela prioridade da empresa, com o estado de cada uma (sem sonda, sonda falhou,
  evidência confirmada, pronta para habilitar).
- **Modo sequencial:** mostra uma proposta por vez, com a empresa, a evidência da pesquisa,
  o link do board e três ações em ordem — "Testar o collector", "Termos revisados" com a
  data, "Habilitar" — e "Pular" / "Próxima".
- **Testar várias:** botão que sonda as propostas selecionadas uma de cada vez, respeitando
  `Retry-After` quando houver 429, com progresso e resultado por linha. Só a sonda roda
  em lote; termos e habilitação continuam um por um.
- Contadores no topo: quantas sem sonda, com sonda falha, confirmadas, habilitadas.

## Fora de escopo

- Marcar termos revisados ou habilitar em lote: é afirmação humana sobre cada fonte.
- Coletar logo após habilitar: o agendamento do worker cuida disso.

## Notas de implementação

- Usar as mesmas rotas do F14-02 e do F14-06; nenhum endpoint novo além, se preciso, de um
  filtro `?status=proposed` na listagem de fontes.
- O lote de sondas no frontend é sequencial (`for … await`), para não disparar requisições
  paralelas contra a API.
- As fontes habilitadas em massa só devem ir ao ar depois do F20-03 (antigo F17-02), para a Inbox filtrar
  as áreas; o card declara essa dependência e a tela avisa se o perfil não tem áreas de
  interesse.

## Critérios de aceite

- [ ] A fila lista as propostas por estado e prioridade.
- [ ] O modo sequencial leva de uma proposta à próxima sem voltar à lista.
- [ ] O lote de sondas respeita `Retry-After` e mostra o resultado de cada uma.
- [ ] Termos e habilitação nunca acontecem em lote.

## Verificação

- **CI:** testes de componente da fila (estados, sequência, lote com 429 simulado); teste do
  filtro de listagem, se criado.
- **Máquina de referência:** homologar as propostas do F20-03 (antigo F17-04) pela fila e registrar no PR
  quantas foram confirmadas e quantas falharam, com o motivo.

## Arquivos prováveis

- `apps/web/src/routes/SourcesPage.tsx`, `apps/web/src/components/HomologationQueue.tsx`
  (novo)
- `apps/web/src/features/sources/`
- `src/opportunity_radar/presentation/http/acquisition.py` (filtro, se preciso)

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `apps/web/src/routes/HomologationQueuePage.tsx` | Rota "Fila de homologação": contadores, lista por estado/prioridade e o modo sequencial. |
| Criar | `apps/web/src/components/HomologationQueue.tsx` | Componente da fila (lista + card sequencial + botão "Testar várias"), reaproveitado pela rota. |
| Alterar | `apps/web/src/routes/SourcesPage.tsx` | Hoje monta a lista de fontes a partir de `useSourceHealth()` (linha 248) e mostra `source.evidenceStatus` por cartão (linha 127). Adicionar o link/aba para a nova rota da fila. |
| Alterar | `apps/web/src/features/sources/api.ts` | `sourceTypes`/`SourceHealth` já existem (linha 204+); adicionar o campo `retryAfterSeconds` no tipo de resultado do probe e, se o filtro for feito aqui, o parâmetro `status` em `getSourceHealth`. |
| Alterar | `apps/web/src/features/sources/useSources.ts` | `useSourceHealth()` (linha 18-19) e `useProbeSource` (linha 102-105) já existem; adicionar hook `useProbeQueue` que roda os probes selecionados em sequência (`for … await`), aguardando `retryAfterSeconds` entre um 429 e o próximo probe do lote. |
| Alterar | `src/opportunity_radar/presentation/http/dashboard.py` | `list_sources_health` (linha 348) só aceita `only_failing`; adicionar `status: str \| None = None` e repassar para `list_source_health`. |
| Alterar | `src/opportunity_radar/dashboard/queries.py` | `list_source_health(session, *, only_failing=False)` (linha 708) monta a consulta por `SourceDefinitionModel` sem filtrar por `enabled`/`evidence_status` nem ordenar por prioridade da empresa; adicionar filtro `status="proposed"` (equivalente a `enabled is False`) e `ORDER BY` pela prioridade de `Company` via `company_source_id` → `CompanySource.company_id` → `Company.priority`. |
| Alterar | `src/opportunity_radar/acquisition/probing.py` | `ProbeOutcome` (linha 33-40) não guarda o `Retry-After` da resposta; adicionar `retry_after_seconds: float \| None = None` e preenchê-lo em `_failed` quando `error_code == "SOURCE_RATE_LIMITED"`. |
| Alterar | `src/opportunity_radar/presentation/http/acquisition.py` | `SourceProbeResult` (linha 103-113) espelha `ProbeOutcome`; adicionar o mesmo `retry_after_seconds` para o frontend usar no lote. |

## Interfaces

```python
# src/opportunity_radar/acquisition/probing.py
@dataclass(frozen=True, slots=True)
class ProbeOutcome:
    ok: bool
    detail: str
    items_seen: int = 0
    http_requests: int = 0
    error_code: str | None = None
    last_http_attempt_at: datetime | None = None
    retry_after_seconds: float | None = None  # novo: só quando error_code == SOURCE_RATE_LIMITED


# src/opportunity_radar/dashboard/queries.py
def list_source_health(
    session: Session,
    *,
    only_failing: bool = False,
    status: Literal["proposed"] | None = None,  # novo: "proposed" == enabled is False
) -> tuple[SourceHealth, ...]: ...
```

```typescript
// apps/web/src/features/sources/api.ts
interface QueueCounters {
  withoutProbe: number
  probeFailed: number
  confirmed: number
  enabled: number
}

interface BatchProbeResult {
  sourceId: string
  ok: boolean
  detail: string
  errorCode: string | null
  retryAfterSeconds: number | null
}
```

## Passos

1. Escrever os testes de componente da fila (estados, sequência, lote com 429 simulado) antes do código, cobrindo cada critério de aceite.
2. Em `src/opportunity_radar/acquisition/probing.py`, adicionar `retry_after_seconds` a `ProbeOutcome` e preenchê-lo em `_failed`/`run_probe` a partir do cabeçalho `Retry-After` quando o `AcquisitionError` tiver `code == AcquisitionErrorCode.SOURCE_RATE_LIMITED`.
3. Em `src/opportunity_radar/presentation/http/acquisition.py`, espelhar o campo em `SourceProbeResult` e no `_probe_response` (linha 395).
4. Em `src/opportunity_radar/dashboard/queries.py`, adicionar o parâmetro `status` a `list_source_health` e o `JOIN` até `Company.priority` para a ordenação; escrever o teste em `tests/backend/dashboard/test_queries.py`.
5. Em `src/opportunity_radar/presentation/http/dashboard.py`, repassar `status` em `list_sources_health` (linha 348).
6. Criar `apps/web/src/components/HomologationQueue.tsx` com os contadores do topo, a lista por estado/prioridade e o card do modo sequencial (empresa, evidência, link do board, "Testar o collector" / "Termos revisados" / "Habilitar" / "Pular" / "Próxima").
7. Adicionar em `apps/web/src/features/sources/useSources.ts` o hook `useProbeQueue`, que chama `useProbeSource` para cada fonte selecionada em um laço `for … await`, aguardando `retryAfterSeconds` (ou um atraso padrão) antes do próximo probe quando `errorCode === 'SOURCE_RATE_LIMITED'`.
8. Criar `apps/web/src/routes/HomologationQueuePage.tsx`, montando `HomologationQueue` a partir de `useSourceHealth({ status: 'proposed' })`.
9. Ligar a nova rota a `apps/web/src/routes/SourcesPage.tsx` (link/aba), sem remover o fluxo atual de um cartão por vez.
10. Adicionar o aviso da tela quando o perfil não tem áreas de interesse (dependência do F20-03), reaproveitando o texto de "Notas de implementação".
11. Rodar os comandos de verificação e colar no PR a homologação real das propostas do F20-03 pela fila (quantas confirmadas, quantas falharam e o motivo).

## Testes a escrever

- `tests/backend/dashboard/test_queries.py::test_list_source_health_filters_by_status_proposed` — só fontes desabilitadas com evidência pendente aparecem.
- `tests/backend/dashboard/test_queries.py::test_list_source_health_orders_by_company_priority` — prioridade alta da empresa aparece primeiro.
- `tests/backend/acquisition/test_service.py::test_probe_reports_retry_after_on_rate_limit` — `ProbeOutcome.retry_after_seconds` reflete o cabeçalho `Retry-After` de uma resposta 429 simulada com `httpx.MockTransport`.
- `apps/web/src/components/HomologationQueue.test.tsx::lista as propostas por estado e prioridade` — critério de aceite 1.
- `apps/web/src/components/HomologationQueue.test.tsx::modo sequencial avança sem voltar à lista` — critério de aceite 2.
- `apps/web/src/components/HomologationQueue.test.tsx::lote de sondas respeita Retry-After e mostra resultado por linha` — critério de aceite 3, com 429 simulado.
- `apps/web/src/components/HomologationQueue.test.tsx::termos e habilitação nunca disparam em lote` — critério de aceite 4.

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
docker compose -p f20-25 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/dashboard/test_queries.py tests/backend/acquisition/test_service.py
docker compose -p f20-25 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-25 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
