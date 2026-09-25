# CARD F20-43 — Orçamento de créditos Tavily e telemetria

- **Status:** Backlog
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
docker compose -p f20-43 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-43 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-43 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
