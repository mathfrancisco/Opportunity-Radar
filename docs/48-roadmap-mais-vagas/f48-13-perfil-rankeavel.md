# F48-13 — Perfil ranqueável (V06)

## Resultado

- Nova coluna `employment_preference.accepted_seniorities` (`varchar[]` PostgreSQL, padrão
  `{INTERN, JUNIOR, MID, UNKNOWN}`): declaração de preferência no perfil que chega ao snapshot
  de matching. Senioridades fora da seleção (ex.: SENIOR, STAFF) **nunca são excluídas** pelas
  regras de matching; elas ficam com veredito mais baixo (`WATCHLIST` ou `LOW_MATCH` em lugar
  de `RECOMMENDED`). Nenhuma marcada vale como "não informado" (F20-72): nenhum nível perde
  posição por falta de preferência.
- Script `scripts/seed_profile_target_areas.py` (com `--dry-run`) escreve `target_role_families
  = {SOFTWARE_ENGINEERING, DATA, INFRASTRUCTURE, SECURITY}` no perfil ativo só se o campo
  estiver vazio, respeitando edição manual do usuário. Decisão 1 da SPEC: o proxy técnico
  coincide com a definição da north-star (§1), logo gravá-lo faz a métrica do Inbox e a
  métrica do negócio coincidirem. Tela de perfil avisa se áreas-alvo ou skills estiverem vazias.
- Tela `ProfilePage` permite editar `accepted_seniorities` como checkboxes (Estágio, Júnior,
  Pleno, Sênior, Staff, Lead, Gestão, Direção, Não informada); salva em `PUT /profile/versions`
  com body `{ preferences: { accepted_seniorities: [...] } }`. Aviso de áreas/skills vazio
  aparece se ambos estiverem ausentes.
- Migração `20260929_0058` (re-encadeada para `20260929_0057` no merge): backfill de versões
  existentes com padrão `{INTERN, JUNIOR, MID, UNKNOWN}`.

## Decisão 1: Áreas-alvo iniciais

Gravar o proxy técnico no perfil ativo (decisão 2 da SPEC) por script idempotente
(`seed_profile_target_areas.py --dry-run`) só se estiver vazio. Motivo: hoje ~70 % dos
visíveis são de áreas não técnicas ou sem área útil; o proxy **é** a definição da north-star
(§1 da SPEC), e gravá-lo faz Inbox e métrica coincidirem, é reversível pela UI e não espera
o usuário. Skills e títulos não são preenchidos: são fatos pessoais que não devo inventar.

## Decisão 2: Senioridades aceitas

Padrão INTERN, JUNIOR, MID e UNKNOWN; SENIOR ou mais fica "abaixo, não excluído". Motivo:
é o que F20-72 já assume, e esconder SENIOR seria elegibilidade sem regra explícita. UNKNOWN
é 50,7 % do acervo; deixá-lo no padrão reflete a realidade.

## Limites

- A edição de senioridades é feita na tela de perfil, mas RULES_VERSION (que governa a
  avaliação) é incrementado apenas pelo F48-12; este card deixa a avaliação passada
  como está.
- Script de seed de áreas **não roda** contra o banco real; deve ser executado manualmente
  antes ou como parte do F48-06 (que mede o funil).

## Verificação

Suite completa **1.242 testes passaram, 11 skipped**. Testes da web: **267 testes**. Testes em
`tests/backend/profile/test_accepted_seniorities.py` (parse da preferência do snapshot,
padrão quando ausente), `test_accepted_seniorities_integration.py` (perfil atualiza snapshot,
avaliação respeita preferência), `tests/backend/matching/test_domain.py` (matriz de
conhecimento com seniorities aceitas), `test_profile_without_seniority.py` (perfil sem
preferência não esconde nível), `tests/backend/matching/test_profile_without_seniority.py`
(ponta a ponta), e teste de componente `ProfilePage.test.tsx` (checkboxes, aviso, salva
corretamente).

Não testado contra banco real: script `seed_profile_target_areas.py --dry-run` não foi
executado no banco da stack real. RULES_VERSION **não foi incrementado** neste card; fica
para F48-12. Migração `20260929_0058` foi re-encadeada onto `20260929_0057` no merge da
branch.
