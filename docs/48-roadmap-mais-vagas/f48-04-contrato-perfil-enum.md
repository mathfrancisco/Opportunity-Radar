# F48-04 — Contrato do perfil casa com o enum (V03)

## Resultado

`_optional_enum` (`matching/service.py`) normaliza hífen e espaços para `_` antes de resolver o
enum. `full-time`, `part-time`, `internship`, ` Full Time ` e `FULL_TIME` resolvem para o mesmo
membro, então `accepted_contract_types` deixa de ficar vazio e `CONTRACT_COMPATIBLE` deixa de ser
`UNKNOWN` quando os dois lados têm valor.

## Contexto

O perfil guarda `full-time`, que virava `FULL-TIME` e falhava contra `FULL_TIME`
(`docs/48-spec-mais-vagas.md` §4.3).

## Escopo

- `src/opportunity_radar/matching/service.py`: `_optional_enum`.
- A normalização vale para todos os enums lidos por essa função (modo de trabalho, período,
  prioridade); valores que já eram canônicos não mudam. Reavaliar avaliações antigas é outro card.

## Critérios de aceite

- [x] `full-time`, `part-time`, `internship` e `FULL_TIME` resolvem para o mesmo enum.
- [x] `CONTRACT_COMPATIBLE` deixa de ser `UNKNOWN` quando ambos os lados têm valor.

## Verificação

Testes em `tests/backend/matching/test_domain.py`
(`test_profile_contract_spellings_resolve_to_the_same_enum`,
`test_a_hyphenated_profile_contract_makes_contract_compatible_known`).

```
docker compose -p f48w1 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/matching/test_domain.py
23 passed
```