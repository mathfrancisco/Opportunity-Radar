# CARD F11-01 — Definir identidade de atualidade

- **Status:** Backlog
- **Fase:** 11 — Reavaliação por mudança de versão
- **Depende de:** F10-01
- **Bloqueia:** F11-02, F11-03
- **Origem no roadmap:** [Fase 11](../../33-roadmap-pos-mvp.md#fase-11--reavaliação-por-mudança-de-versão)

## Resultado

Uma regra única determina se um assessment representa a entrada atual ou está
desatualizado.

## Contexto

Comparar apenas `profile_version_id` deixa passar mudanças na oportunidade, no ruleset e
na taxonomia. A data UTC também participa do `input_hash` atual.

## Escopo

- Definir a identidade com versão da oportunidade, perfil ativo, ruleset, taxonomia e
  data de referência UTC.
- Centralizar a comparação para o worker e os read models.
- Documentar a política de no máximo uma avaliação por oportunidade por dia UTC.

## Fora de escopo

- Executar o backfill.
- Alterar pesos ou regras de matching.
- Remover assessments antigos.

## Notas de implementação

Reusar a construção de entrada de `MatchingService` para evitar que o seletor de
pendências e o serviço calculem identidades diferentes.

## Critérios de aceite

- [ ] Cada componente da identidade está documentado e coberto por cenário próprio.
- [ ] Mudança em qualquer versão marca o assessment anterior como desatualizado.
- [ ] A mesma entrada no mesmo dia UTC continua idempotente.
- [ ] A política não depende de evento mantido somente em memória.

## Verificação

Demonstrar a tabela de casos de atualidade e provar que worker e Inbox usam a mesma
decisão para cada caso.

## Arquivos prováveis

- `src/opportunity_radar/matching/service.py`
- `src/opportunity_radar/matching/repository.py`
- `src/opportunity_radar/dashboard/queries.py`
- `tests/backend/matching/`
- `tests/backend/dashboard/`
