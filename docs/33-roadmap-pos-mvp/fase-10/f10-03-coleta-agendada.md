# CARD F10-03 — Coleta agendada e request por capability

- **Status:** In progress
- **Fase:** 10 — Ciclo autônomo
- **Depende de:** F10-04
- **Bloqueia:** F10-06
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§9 e 12–13; ordem prática 45 e 47

## Resultado

O worker coleta fontes habilitadas conforme `schedule`, intervalo mínimo e
capabilities reais de cada collector, com falhas isoladas.

## Contexto

`SourceDefinition.schedule`, `rate_limit_policy.minimum_run_interval_seconds`
e `collection_timezone` já existem. Apenas Remotive aceita palavras-chave;
enviar esse filtro a Ashby, Lever e Greenhouse causa
`INVALID_CONFIGURATION` e mascara cobertura parcial.

## Escopo

- Criar `collect_enabled_sources` no worker.
- Executar somente fonte habilitada, com `schedule` vencido e respeitando o
  intervalo mínimo.
- Aplicar backoff exponencial após falhas consecutivas, limitado a 24 horas, e
  restaurar o intervalo normal após sucesso.
- Montar `CollectionRequest` a partir das capabilities do collector.
- Enviar palavras-chave apenas quando `keyword_search=true`.
- Persistir `RawItem` antes de filtros locais de título ou skill.
- Registrar o resultado de toda fonte elegível, sem abortar as demais por uma
  falha.

## Fora de escopo

- Descoberta ou homologação de novas fontes (Fase 12).
- Novo formato de schedule ou timezone.
- Alterar `execution_trigger`, entregue por F10-04.

## Notas de implementação

`schedule = null` mantém uma fonte habilitada sem execução automática.
`collection_timezone` continua regendo expressões de calendário. O job usa o
mesmo `SourceRun` da coleta sob demanda, distinguido pelo campo de F10-04.

## Critérios de aceite

- [ ] Fonte desabilitada nunca executa pelo relógio.
- [ ] Fonte sem `schedule` não executa automaticamente.
- [ ] O intervalo mínimo entre acessos é respeitado.
- [ ] Backoff dobra após falhas até o teto e sucesso o remove.
- [ ] Remotive recebe palavras-chave; Ashby, Lever e Greenhouse não as recebem.
- [ ] Filtros locais não descartam evidência antes de `RawItem` persistir.
- [ ] Falha de uma fonte não impede as outras.
- [ ] O resumo classifica cada fonte elegível como concluída, falha, pulada ou
      bloqueada.

## Verificação

Criar testes com relógio controlado para schedule, mínimo de intervalo e
backoff; cobrir requests por capability, persistência antes de filtro e falha
isolada por fonte.

## Arquivos prováveis

- `src/opportunity_radar/worker.py`
- `src/opportunity_radar/acquisition/service.py`
- `src/opportunity_radar/acquisition/collectors.py`
- `src/opportunity_radar/acquisition/domain.py`
- `src/opportunity_radar/acquisition/repository.py`
- `tests/` de acquisition e worker
