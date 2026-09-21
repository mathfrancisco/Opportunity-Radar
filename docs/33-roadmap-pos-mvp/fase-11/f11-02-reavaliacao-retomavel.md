# CARD F11-02 — Executar reavaliação retomável

- **Status:** Backlog
- **Fase:** 11 — Reavaliação por mudança de versão
- **Depende de:** F11-01, F10-01
- **Bloqueia:** F11-04
- **Origem no roadmap:** [Fase 11](../../33-roadmap-pos-mvp.md#fase-11--reavaliação-por-mudança-de-versão)

## Resultado

Mudanças de perfil, oportunidade, ruleset ou taxonomia colocam somente as oportunidades
desatualizadas na fila determinística de avaliação.

## Contexto

Ativar uma nova `ProfileVersion` não reavalia o catálogo. O processo precisa sobreviver
a reinícios e preservar o histórico append-only.

## Escopo

- Selecionar lotes desatualizados com a identidade definida em F11-01.
- Reusar o job `evaluate_pending` da Fase 10.
- Permitir retomada após falha ou reinício.
- Registrar progresso e falha por passada.

## Fora de escopo

- Atualizar linhas antigas.
- Reexecutar análise semântica antes do novo assessment existir.
- Criar fila distribuída.

## Notas de implementação

O bump do ruleset é detectado comparando a versão persistida com a constante ativa. A
claim e os limites de lote seguem o mesmo mecanismo da avaliação automática.

## Critérios de aceite

- [ ] Ativar um perfil novo torna os assessments anteriores pendentes.
- [ ] Atualizar o conteúdo da oportunidade gera assessment para a nova versão.
- [ ] Bump de ruleset ou taxonomia produz o mesmo comportamento.
- [ ] Reinício no meio do lote retoma o trabalho sem duplicar resultado.
- [ ] Assessments anteriores continuam legíveis e inalterados.

## Verificação

Executar cenários controlados para cada tipo de mudança, interromper um lote e comparar
IDs, versões e contagens antes e depois da retomada.

## Arquivos prováveis

- `src/opportunity_radar/worker.py`
- `src/opportunity_radar/matching/service.py`
- `src/opportunity_radar/matching/repository.py`
- `src/opportunity_radar/profile/service.py`
- `tests/backend/matching/`
- `tests/backend/test_worker.py`
