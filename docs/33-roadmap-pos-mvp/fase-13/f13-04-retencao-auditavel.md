# CARD F13-04 — Retenção auditável de payload

- **Status:** Backlog
- **Fase:** 13 — Operação contínua
- **Depende de:** F13-03
- **Bloqueia:** F13-06
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§24–26 e risco 5

## Resultado

O conteúdo de `RawItemPayload` expira de forma configurável e auditável, com retenção
padrão de 12 meses, sem apagar o envelope ou a procedência.

## Contexto

Retenção reduz dados brutos antigos, mas não pode quebrar o histórico de aquisição nem
mascarar que o reprocessamento já não está disponível.

## Escopo

- Definir política de retenção configurável, com padrão de 12 meses.
- Expirar somente payload de item com normalização terminal e sem reprocessamento
  pendente.
- Registrar cada expiração append-only com `raw_item_id`, data, versão da política e
  hash.
- Expor na API e na interface se o payload está retido ou expirado.

## Fora de escopo

- Apagar `RawItem`, `SourceRun`, `SourceOccurrence`, hash ou executar retenção de
  qualquer outra entidade.

## Notas de implementação

Faça a operação idempotente e em lotes. Preserve um marcador de expiração no payload
ou no envelope, sem reintroduzir conteúdo apagado. Trate payload ausente como estado
explícito, não como erro de serialização.

## Critérios de aceite

- [ ] Política padrão expira somente payload com mais de 12 meses.
- [ ] Itens pendentes ou sem normalização terminal não expiram.
- [ ] Envelope e procedência permanecem disponíveis após a expiração.
- [ ] Toda expiração grava histórico append-only com os campos exigidos.
- [ ] Reexecutar a retenção não cria histórico duplicado.
- [ ] API e UI informam indisponibilidade de reprocessamento após expiração.

## Verificação

Use relógio controlado com payloads elegíveis e não elegíveis; confirme remoção apenas
dos elegíveis, histórico único, e apresentação correta na API e interface.

## Arquivos prováveis

- `src/opportunity_radar/acquisition/models.py`
- `src/opportunity_radar/acquisition/service.py`
- `src/opportunity_radar/worker.py`
- `apps/web/src/`
