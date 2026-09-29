# CARD F20-40 — Preservação integral do perfil

- **Status:** Feito — `794b519` cobre os três critérios; conferido nesta fase, sem código pendente.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** D — Varredura produtiva
- **Depende de:** Nenhum
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-07](../../40-roadmap-varredura-produtiva/fase-18/f18-07-preservacao-do-perfil.md)

## Ajustes da Fase 20

- O commit `794b519` já preserva as famílias de cargo-alvo. Conferir cada critério abaixo contra o código e fazer só o que faltar.
- O perfil preservado alimenta o perfil mínimo enviado ao Groq (F20-15).

## Resultado

Editar uma preferência não elimina experiências, projetos, datas das skills ou outros campos do perfil ativo.

## Escopo

- Corrigir o round-trip de leitura/edição/escrita; api.ts hoje envia experiences/projects vazios e omite last_used_at.
- Copiar campos não editados da versão-base, com versão esperada. Preservar futuro target_role_families/target_titles.
- Publicação/ativação mantém controle de conflito; erro intermediário não ativa snapshot parcial. Permitir retomar versão publicada sem duplicação acidental.
- Manter histórico imutável, invalidar avaliações pela nova versão e explicar conflito na UI.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [x] Alterar só país preserva todas as experiências/projetos e last_used_at.
- [x] Duas edições concorrentes não perdem dados nem ativam snapshot parcial.
- [x] Nova versão ativa gera reavaliação; antiga continua consultável.

## Critério → evidência

| Critério | Evidência |
| --- | --- |
| Alterar só país preserva experiências/projetos/last_used_at | `tests/backend/profile/test_profile_preservation.py::test_changing_only_countries_preserves_the_rest_of_the_profile`; `_snapshot()` em `src/opportunity_radar/presentation/http/profile.py` completa campos omitidos a partir de `base_version_id` |
| Concorrência não perde dados nem ativa snapshot parcial | `test_second_edit_from_the_same_version_conflicts_and_loses_nothing`, `test_a_refused_save_leaves_no_version_and_keeps_the_active_one`, `test_a_failure_after_the_draft_rolls_the_whole_write_back` (`ProfileService._commit` faz rollback total) |
| Nova versão ativa gera reavaliação; antiga continua consultável | `tests/backend/matching/test_currency.py::test_moving_any_single_component_makes_the_assessment_stale[profile_version_id]` (a avaliação vira "stale" ao trocar a versão ativa do perfil); `test_changing_only_countries_preserves_the_rest_of_the_profile` confirma que a versão anterior fica `ARCHIVED` e legível via `ProfileService.get_version`; `useSaveProfile` em `apps/web/src/features/profile/useProfile.ts` invalida `inbox`/`overview` ao salvar |

## Verificação

- **CI:** Integração backend e contrato frontend com perfil completo; percurso no navegador em F20-47 a F20-49 (antigo F18-09).
- **Máquina de referência:** Sem dependência de GPU ou fontes externas.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`apps/web/src/features/profile/api.ts`, ProfilePage, API/profile service e testes do contrato.

## Contexto no código

O commit `794b519` (`feat: F18-07 — preserve profile target role families across
updates`) já toca `apps/web/src/features/profile/api.ts`, `useProfile.ts`,
`routes/ProfilePage.tsx`, `profile/domain.py`, `profile/models.py`, `profile/service.py`
e adicionou `tests/backend/profile/test_profile_preservation.py`. Conferindo cada
critério de aceite contra o código hoje:

- **Critério 1 (alterar só país preserva experiências/projetos/`last_used_at`) — já
  atendido.** `ProfilePage.tsx:203-212` monta o `draft` enviado a partir de
  `current?.experiences ?? []`/`current?.projects ?? []` (a versão ativa já carregada),
  e a lista de skills preserva `known.get(canonicalName)` (nível, meses,
  `lastUsedAt`) para todo nome já existente (`ProfilePage.tsx:189-202`).
  `api.ts:serializeDraft` (linhas 190-214) serializa `experiences`/`projects`/
  `last_used_at` sempre a partir do que foi montado, nunca vazio. Teste:
  `tests/backend/profile/test_profile_preservation.py:154`
  (`test_changing_only_countries_preserves_the_rest_of_the_profile`).
- **Critério 2 (duas edições concorrentes não perdem dados nem ativam snapshot
  parcial) — já atendido.** `ProfileService._commit` (`profile/service.py`, adicionado
  no commit) executa `_create_draft` → `_mark_published` → `_mark_active` como uma
  única função `write()`, com `try/except` que faz `session.rollback()` em qualquer
  falha antes do commit — uma queda entre publicar e ativar não deixa versão parcial.
  `_advance_profile` continua comparando a versão esperada e levanta
  `ProfileConflictError` em conflito. Frontend: `saveProfileVersion` chama
  `POST /profile/versions` com `activate: true` (`api.ts:268-277`), então o cliente
  também trata create+publish+activate como uma escrita só. Teste:
  `tests/backend/profile/test_profile_preservation.py:273`
  (`test_second_edit_from_the_same_version_conflicts_and_loses_nothing`) e `:247`
  (`test_a_failure_after_the_draft_rolls_the_whole_write_back`).
- **Critério 3 (nova versão ativa gera reavaliação; antiga continua consultável) — já
  atendido, por design anterior ao commit.** `MatchingService.pending_evaluation_ids`
  (`matching/service.py:157-`) já compara
  `assessment.profile_version_id == profile.id` (o `id` da versão *ativa* atual); ao
  ativar uma nova versão, o `id` muda e toda oportunidade elegível volta a aparecer como
  pendente automaticamente — não é um gatilho explícito, é consequência da identidade da
  avaliação. Teste já existente:
  `tests/backend/matching/test_reevaluation.py:121`
  (`test_activating_a_profile_makes_previous_assessments_pending_again`). A versão
  anterior fica `ARCHIVED`, não apagada (`_mark_active`,
  `tests/backend/profile/test_profile_preservation.py:183-186`).
- **O que falta.** Não há lacuna de backend/frontend encontrada para os três critérios
  declarados. `target_titles` (citado no Escopo como "futuro", junto de
  `target_role_families`) não existe em nenhuma camada (`grep -rn "target_titles"` no
  repositório não retorna nada) — não há nada a preservar ainda, porque o campo não foi
  criado; não é uma lacuna deste card, é um lembrete para quando `target_titles` for
  adicionado por outro card. O percurso de navegador (F20-47 a F20-49, antigo F18-09)
  está fora deste card por definição da própria seção "Verificação".

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Conferir | `apps/web/src/features/profile/api.ts` | round-trip já preserva `experiences`/`projects`/`last_used_at` (linhas 190-214) |
| Conferir | `apps/web/src/routes/ProfilePage.tsx` | `submit` já reaproveita a versão ativa (linhas 186-213) |
| Conferir | `src/opportunity_radar/profile/service.py` | `_commit`/`_create_draft`/`_mark_published`/`_mark_active` já atômicos |
| Conferir | `src/opportunity_radar/matching/service.py` | `pending_evaluation_ids` já reavalia por `profile_version_id` |
| Alterar (se algum teste abaixo falhar) | `tests/backend/profile/test_profile_preservation.py` | fechar qualquer lacuna que a execução real revelar |

Nenhuma migração nova é esperada: `20260925_0020_profile_target_role_families.py` já
cobre o campo que existe hoje.

## Interfaces

Nenhuma interface nova: as usadas hoje já atendem os critérios.

```python
# src/opportunity_radar/profile/service.py (já existente, referência)
class ProfileService:
    def create_active_version(
        self, snapshot: ProfileSnapshot, expected_profile_version: int,
    ) -> ProfileVersion:
        """Create, publish e activate como uma escrita só (já implementado)."""

    def _commit(self, write: Callable[[], ProfileVersionModel]) -> ProfileVersion:
        """Comita `write()` inteiro ou reverte tudo em qualquer exceção (já
        implementado)."""
```

## Passos

1. Rodar `tests/backend/profile/test_profile_preservation.py` e
   `tests/backend/matching/test_reevaluation.py` isoladamente e confirmar que os três
   critérios de aceite têm teste verde e evidência (nomes de teste na seção "Contexto no
   código").
2. Se algum passar por acidente (falso positivo) ou não cobrir exatamente o texto do
   critério, escrever o teste que falta antes de qualquer alteração de produção.
3. Revisitar manualmente o fluxo de conflito na UI: confirmar que `readVersion`
   (`api.ts`) devolve a mensagem de 409 amigável já implementada
   ("Outra edição mudou o perfil...") e que `ProfilePage.tsx` a exibe.
4. Confirmar que `target_titles` de fato não existe em nenhuma camada (repetir o
   `grep -rn "target_titles"`) antes de declarar o critério "futuro" como não aplicável
   nesta rodada; se alguém já o tiver introduzido em paralelo, tratar como escopo deste
   card.
5. Rodar o comando de verificação abaixo. Se tudo estiver verde, marcar os três
   critérios de aceite com as referências acima e não adicionar código novo — o card já
   está feito pelo `794b519`, e código sem lacuna correspondente seria trabalho não
   pedido.
6. Se qualquer teste falhar, tratar como regressão do próprio `794b519` e corrigir na
   camada exata que falhou (backend `service.py` ou frontend `api.ts`/`ProfilePage.tsx`),
   nunca ampliando para o percurso de navegador (fora de escopo aqui).

## Testes a escrever

Nenhum teste novo é esperado se o passo 1 confirmar os três critérios; se a execução
revelar uma lacuna, os testes ficam em:

- `tests/backend/profile/test_profile_preservation.py::test_changing_only_countries_preserves_the_rest_of_the_profile` (já existe — critério de aceite 1).
- `tests/backend/profile/test_profile_preservation.py::test_second_edit_from_the_same_version_conflicts_and_loses_nothing` (já existe — critério de aceite 2).
- `tests/backend/matching/test_reevaluation.py::test_activating_a_profile_makes_previous_assessments_pending_again` (já existe — critério de aceite 3).
- Qualquer lacuna nova encontrada no passo 2 acima vai num teste nomeado pelo
  comportamento específico que faltar, no mesmo arquivo do critério correspondente.

## Não fazer

- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não habilitar fonte sem passar pelo gate de homologação.
- Não fazer chamada real a boards, Groq ou Tavily no CI; usar `httpx.MockTransport` ou os servidores falsos de `tests/e2e/`.
- Não adicionar dependência nova sem registrar o motivo no PR.
- Não usar LLM neste card, salvo quando a seção "Ajustes da Fase 20" disser o contrário.

## Como trabalhar este card

1. Ler "Ajustes da Fase 20" primeiro: eles prevalecem sobre o texto herdado.
2. Ler "Arquivos prováveis" e confirmar cada caminho com `ls`/`grep` antes de editar; caminho inexistente vira nota no PR.
3. Escrever primeiro os testes dos critérios de aceite, depois o código.
4. IDs antigos no texto aparecem como `F20-xx (antigo F1x-yy)`; a tabela completa está no README da Fase 20.
5. O que depende do acervo real ("Máquina de referência") é medido fora do CI e colado no PR.

## Comando de verificação

```bash
docker compose -p f20-40 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/profile/test_profile_preservation.py tests/backend/matching/test_reevaluation.py
docker compose -p f20-40 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-40 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
