# CARD F19-03 — Orçamento de créditos e telemetria

- **Status:** Backlog
- **Fase:** 19 — Integração Tavily
- **Depende de:** F19-01
- **Bloqueia:** F19-05
- **Origem:** [SPEC 41](../../41-spec-tavily.md), §6

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
- Cada chamada ao cliente do F19-01 soma o custo que `include_usage=true` devolveu a um
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
  (`docs/39-spec-varredura-produtiva.md`, Frente E/F18-04), sem duplicar aqui.
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
