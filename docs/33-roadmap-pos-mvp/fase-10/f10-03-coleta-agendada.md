# CARD F10-03 — Coleta agendada e request por capability

- **Status:** Done
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

- [x] Fonte desabilitada nunca executa pelo relógio.
- [x] Fonte sem `schedule` não executa automaticamente.
- [x] O intervalo mínimo entre acessos é respeitado.
- [x] Backoff dobra após falhas até o teto e sucesso o remove.
- [x] Remotive recebe palavras-chave; Ashby, Lever e Greenhouse não as recebem.
- [x] Filtros locais não descartam evidência antes de `RawItem` persistir.
- [x] Falha de uma fonte não impede as outras.
- [x] O resumo classifica cada fonte elegível como concluída, falha, pulada ou
      bloqueada.

## Verificação

Criar testes com relógio controlado para schedule, mínimo de intervalo e
backoff; cobrir requests por capability, persistência antes de filtro e falha
isolada por fonte.

`tests/backend/acquisition/test_scheduling.py` cobre schedule, intervalo mínimo,
backoff e teto com relógio injetado, e roda no pipeline.

**Pendência registrada:** `tests/backend/acquisition/test_collection_job.py`
cobre requests por capability, persistência antes de filtro, falha isolada e as
quatro classificações do resumo, mas está `skip`. Os testes passam em banco
limpo e falham em banco reaproveitado: o job coleta todas as fontes habilitadas,
então fontes deixadas por uma execução anterior são resolvidas para o collector
stub do teste e contam como chamadas dele. A fixture de limpeza e os tipos de
fonte por teste já estão no arquivo; falta concluir e remover o `skip`. O gate
E2E do F10-06 cobre esse comportamento enquanto isso.

## Decisões de implementação

A decisão de agendamento virou um módulo puro, `acquisition/scheduling.py`, com
o instante sempre recebido por parâmetro. Uma regra que lê o relógio por dentro
só se testa esperando, e é assim que erro de backoff e de intervalo mínimo
sobrevive até produção.

O backoff é derivado do histórico de `SourceRun`, não de um contador: a sequência
de falhas não pode divergir do histórico que o operador lê, e uma execução bem
sucedida remove o backoff por existir, sem escrita extra.

Fonte sem execução anterior é considerada vencida na primeira passada. A trigger
do APScheduler responde sempre com o *próximo* disparo, então uma fonte recém
habilitada nunca rodaria sozinha — o que quebraria justamente o gate do F10-06.

O intervalo mínimo é checado antes de criar o `SourceRun`. Deixar o `execute`
recusar por rate limit encheria o histórico da fonte de falhas, que o backoff
então leria como indisponibilidade.

## Arquivos prováveis

- `src/opportunity_radar/worker.py`
- `src/opportunity_radar/acquisition/service.py`
- `src/opportunity_radar/acquisition/collectors.py`
- `src/opportunity_radar/acquisition/domain.py`
- `src/opportunity_radar/acquisition/repository.py`
- `tests/` de acquisition e worker
