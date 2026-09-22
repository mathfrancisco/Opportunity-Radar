# CARD F11-01 — Definir identidade de atualidade

- **Status:** Done
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

- [x] Cada componente da identidade está documentado e coberto por cenário próprio.
- [x] Mudança em qualquer versão marca o assessment anterior como desatualizado.
- [x] A mesma entrada no mesmo dia UTC continua idempotente.
- [x] A política não depende de evento mantido somente em memória.

## Verificação

Demonstrar a tabela de casos de atualidade e provar que worker e Inbox usam a mesma
decisão para cada caso.

Entregue em `tests/backend/matching/test_currency.py`. Cada caso é afirmado nas duas
implementações — objeto ORM e predicado SQL — porque a falha a evitar não é uma delas
estar errada, é as duas divergirem.

## Decisões de implementação

A regra vive em `matching/currency.py`. A atualidade é definida por quatro componentes:
versão da oportunidade, `ProfileVersion` ativa, ruleset e taxonomia. O dia UTC é o quinto
componente da identidade, mas fica **fora** da atualidade de propósito: um dia novo não
invalida um score, apenas libera uma nova avaliação. Se o dia entrasse na atualidade, toda
a Inbox apareceria desatualizada à meia-noite.

`pending_evaluation_ids` passou a perguntar isso em SQL sobre os componentes, em vez de
reconstruir o hash de snapshot por oportunidade. O read model precisa fazer a mesma
pergunta sobre o catálogo inteiro, e uma regra que só um dos lados consegue expressar é
uma regra em que os dois vão divergir.

O `input_hash` continua sendo a chave de armazenamento e de idempotência do `evaluate`.
Ele cobre o snapshot completo; a atualidade cobre os componentes versionados. São papéis
diferentes e ambos permanecem.

A subquery de taxonomia é correlacionada explicitamente. Aninhada dentro de um `EXISTS`, o
SQLAlchemy acrescentava `opportunity` ao `FROM` dela em vez de referenciar a linha externa,
e o agregado virava silenciosamente todas as skills de todas as oportunidades.

## Arquivos prováveis

- `src/opportunity_radar/matching/service.py`
- `src/opportunity_radar/matching/repository.py`
- `src/opportunity_radar/dashboard/queries.py`
- `tests/backend/matching/`
- `tests/backend/dashboard/`
