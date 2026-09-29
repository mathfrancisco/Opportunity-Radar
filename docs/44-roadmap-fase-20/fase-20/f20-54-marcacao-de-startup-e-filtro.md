# CARD F20-54 — Marcação "startup" com evidência e filtro na UI

- **Status:** Implementado em `feature/f20-54-startup-tag` (aguardando merge/CI)
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-53
- **Origem:** [SPEC 45](../../45-spec-descoberta-startups.md); pesquisa
  [`docs/pesquisas/descoberta-startups-ats.md`](../../pesquisas/descoberta-startups-ats.md)

## Resultado

Empresa com sinal de startup (batch YC, seed, Series A) coletado por qualquer via
homologada carrega essa evidência de forma auditável, e a Inbox/Overview filtra por "é
startup".

## Contexto

F20-53 produz o sinal só para propostas vindas da busca restrita a domínios de ATS; este
card decide onde o sinal mora e como aparece na UI. A evidência pode vir de qualquer
fonte já homologada, não só de F20-53 — um board já coletado antes pode ganhar a marca
depois, se uma vaga futura citar o sinal.

## Escopo

- Tabela satélite ou coluna JSONB em `company_radar` (a decidir no PR, seguindo o padrão
  de evidência já usado por `discovery_evidence` no F20-46) guardando: tipo de sinal
  (`yc_batch`, `seed_stage`, `series_a`, outro), força (`forte`/`fraco`, do F20-53),
  texto/URL de origem, data de captura.
- Nunca sobrescreve sinal forte com sinal fraco mais recente — evidência forte
  (marca nomeada) tem precedência e persiste mesmo se uma nova coleta só trouxer sinal
  fraco.
- Múltiplas evidências para a mesma empresa acumulam (não substituem), para auditoria —
  mesmo princípio de histórico que outras evidências do radar já seguem.
- Endpoint/campo na API para o filtro (Overview/Inbox) — `apps/web` consome e adiciona um
  filtro "é startup" (e, se houver evidência de batch, mostra o batch).
- **Invariante:** a marca não altera elegibilidade, score, veredito nem fator do
  matching — é metadado de exibição/filtro, igual a qualquer outra marca do radar.

## Decisão de implementação

- **Tabela satélite** `company_radar.company_startup_evidence` (migração `20260929_0054`,
  `down_revision` `20260928_0053`, head única): `signal` (`yc_batch`/`seed_stage`/
  `series_a`/`other`), `strength` (`strong`/`weak`), `source_text`, `source_url`, `batch`
  (ex.: `S24`), `captured_at`. Só insere: nada é sobrescrito.
- **Precedência por derivação**: a força da empresa é lida de todas as linhas
  (`companies/startup.py::summarize`) — qualquer `strong` vence, mesmo com `weak` mais
  recente; o `batch` é o da evidência forte `yc_batch` mais recente. Sighting idêntico é
  idempotente (`record_startup_evidence`).
- **API**: `GET /inbox?only_startups=true` filtra por >= 1 evidência (qualquer força);
  cada item traz `startup_strength`/`startup_batch`; `/companies` traz também a lista
  `startup_evidence` (auditoria). UI: checkbox "Só startups" + selo (batch YC, "sinal
  fraco") na Inbox; atalho "Ver só startups" na Overview.
- **Interface para o F20-53**: `record_startup_evidence(session, company_id, ...)` é o
  único ponto de escrita; este card não detecta sinal nem escreve o coletor.
- **Sem backfill**: o card não define fonte para empresas já existentes (`f20manual`);
  nada foi inventado. A marca aparece quando o F20-53 (ou outro coletor) gravar evidência.

## Fora de escopo

- Detectar o sinal em texto — isso é do F20-53 (e de qualquer coletor futuro que emita o
  mesmo formato de evidência).
- Qualquer alteração ao matching, score ou fator de decisão da vaga.

## Critérios de aceite

- [x] Evidência de sinal de startup fica associada à empresa com tipo, força, origem e
      data — auditável, nunca um booleano sem origem.
- [x] Sinal forte não é sobrescrito por sinal fraco mais recente da mesma empresa.
- [x] Múltiplas evidências para a mesma empresa acumulam, não substituem.
- [x] Filtro "é startup" na Inbox/Overview (`apps/web`) mostra só empresas com pelo menos
      uma evidência.
- [x] Nenhum score, veredito ou fator de matching muda em função da marca de startup
      (teste de regressão contra o matching existente).

## Verificação

- **CI:** testes de precedência de evidência (forte não é sobrescrita por fraca),
  acumulação, e teste de componente do filtro em `apps/web` (`npm run check`).
- **Máquina de referência:** sem dependência de chamada externa.

## Arquivos prováveis

- `src/opportunity_radar/companies/` (modelo e serviço de evidência de startup)
- migração Alembic nova (próximo número livre)
- `apps/web/src/...` (filtro na Inbox/Overview)
- `tests/backend/companies/test_startup_evidence.py` (novo)
- `apps/web/src/.../__tests__/...` (novo, filtro)

## Não fazer

- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora do escopo listado sem registrar o motivo no PR.
- Não usar LLM para inferir o sinal de startup neste card — é extração determinística de
  padrão de texto (marca/estágio citados literalmente), não classificação assistida.

## Comando de verificação

```bash
docker compose -p f20-54 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/companies/test_startup_evidence.py
docker compose -p f20-54 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-54 -f compose.yaml -f compose.dev.yaml run --rm api mypy
cd apps/web && npm run check
```

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa
e o CI está verde.
