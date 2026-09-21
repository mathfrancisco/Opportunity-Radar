# CARD F10-01 — Avaliação automática e identidade atual

- **Status:** In progress
- **Fase:** 10 — Ciclo autônomo
- **Depende de:** Nenhum
- **Bloqueia:** F10-02, F10-06
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§7 e 12; ordem prática 41–42

## Resultado

O worker avalia, em lotes limitados, oportunidades `DISCOVERED` e `ACTIVE`
que não têm `MatchAssessment` para a identidade atual da entrada.

## Contexto

Hoje o matching depende de uma chamada manual. Uma avaliação atual é a mesma
combinação de oportunidade e versão, ProfileVersion ativa, versão de rules,
versão da taxonomia e data de referência UTC. A data limita a uma avaliação
por oportunidade por dia UTC; mudanças de versão tornam a oportunidade
pendente imediatamente.

## Escopo

- Definir e consultar a identidade completa de avaliação atual.
- Adicionar o job `evaluate_pending` ao worker, com lote, coalescing e
  correlation id por passada.
- Usar `MatchingService.evaluate` sem alterar suas regras determinísticas.
- Isolar falha por oportunidade e degradar explicitamente quando não há perfil
  ativo.
- Excluir `CLOSED`, `ARCHIVED` e `REJECTED`.
- Garantir idempotência para a identidade completa.

## Fora de escopo

- Análise Ollama automática.
- Reavaliação disparada por ativação de perfil ou mudanças de ruleset e
  taxonomia (Fase 11).
- Interface para disparar avaliação (F10-06).

## Notas de implementação

Preservar assessments como histórico imutável. O job agenda o serviço
existente; não modifica a lógica de score. Persistir ou derivar a identidade
de modo que reinício do worker não crie duplicata.

## Critérios de aceite

- [ ] Seleciona somente `DISCOVERED` e `ACTIVE` sem assessment atual.
- [ ] Cria no máximo um assessment por oportunidade e dia UTC para a mesma
      identidade.
- [ ] Nova versão de oportunidade entra na fila sem esperar o próximo dia.
- [ ] Falha de uma oportunidade não aborta o lote.
- [ ] Ausência de perfil ativo é registrada como estado degradado.
- [ ] Reinício do worker não duplica assessment.
- [ ] Cada passada possui correlation id próprio.

## Verificação

Criar testes de serviço e de job para seleção, identidade diária, mudança de
versão, idempotência, falha isolada e ausência de perfil ativo.

## Arquivos prováveis

- `src/opportunity_radar/worker.py`
- `src/opportunity_radar/matching/service.py`
- `src/opportunity_radar/matching/repository.py`
- `src/opportunity_radar/matching/models.py`
- `tests/` de matching e worker
