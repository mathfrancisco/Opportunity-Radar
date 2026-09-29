# CARD F20-33 — Palavras-chave do perfil

- **Status:** Feito
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-03, F20-40
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-11](../../38-roadmap-ia-e-busca/fase-17/f17-11-palavras-chave-do-perfil.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Não usar LLM para gerar as palavras-chave nesta fase.

## Resultado

As fontes que buscam por termo passam a buscar pelo que o perfil procura — cargos-alvo e
skills de maior peso —, em rotação, e novas fontes amplas entram só depois de pesquisadas
e com o filtro de área ativo.

## Contexto

A Remotive é a única fonte com busca por termo, e as palavras vêm fixas de
`configuration["keywords"]` (`worker.py:356`). Mudar o foco da busca exige editar a fonte.
O perfil não tem campo de cargos-alvo.

## Escopo

- **Perfil:** preferência `target_titles` (lista curta de cargos, ex.: "backend engineer",
  "engenheiro de software") ao lado das áreas do F20-03 (antigo F17-02).
- **Palavras derivadas:** cargos-alvo + as skills do perfil de maior nível, normalizadas e
  sem duplicata. `configuration["keywords"]` continua valendo como complemento explícito.
- **Rotação:** o limite de 10 termos por requisição (`CollectionRequest`) vira rotação —
  cada coleta usa o próximo bloco de até 10, e o estado da rotação fica no checkpoint da
  fonte.
- **Fontes amplas candidatas:** pesquisa em `docs/pesquisas/` de fontes com API pública e
  busca por termo, cada uma com a mesma revisão de termos do F20-28 a F20-32 (antigo F17-10). A pesquisa é
  entregável; os coletores, sub-cards como no F20-28 a F20-32 (antigo F17-10).
- **Ordem obrigatória:** nenhuma fonte ampla é habilitada antes do F20-03 (antigo F17-02) estar ativo.

## Fora de escopo

- Buscar em sites que proíbem automação.
- Gerar palavras-chave com modelo de linguagem.

## Notas de implementação

- A mudança de perfil passa a mudar a busca na próxima coleta; registrar na execução quais
  termos foram usados, para explicar por que uma vaga entrou.
- Cursor de paginação e rotação de termos são estados separados. Chave de execução
  inclui perfil, conjunto de termos e escopo. Só avançar rotação após confirmação
  durável da página/lote; falha/reinício não pula termos.
- Respeitar capacidades: ATS de board completo não recebe keyword_search.
  Cobrir cargos e sinônimos pt/en por rotação explícita, medindo sobreposição e
  vagas únicas por consulta. Nenhum termo fica permanentemente sem visita.

## Critérios de aceite

- [x] O perfil declara cargos-alvo. Evidência: `test_target_titles_round_trip_through_database`.
- [x] A Remotive busca pelos termos derivados do perfil, em rotação, e a execução
      registra os termos usados. Evidência: `test_derive_keywords_combines_target_titles_and_top_skills`,
      `test_rotate_wraps_around_after_last_block`,
      `test_keyword_rotation_checkpoint_advances_only_after_confirmed_batch` e
      `test_receives_keywords_derived_from_profile`.
- [x] A pesquisa de fontes amplas está registrada em
      `docs/pesquisas/2026-09-fontes-amplas.md` (commit `1c10543`): aceita Remotive como já
      integrada, propõe Adzuna e USAJOBS como sub-cards condicionados, e rejeita Jooble,
      Remote OK e Arbeitnow.
- [x] Nenhuma fonte ampla é habilitada antes do filtro de área. Verificação manual, não
      teste: esta mudança não cria nem habilita fontes; o filtro F20-03 existe e o gate de
      homologação não foi alterado. **Confirmado com evidência real (2026-09-27):** roteiro
      reprodutível de 4 passos em
      `docs/44-roadmap-fase-20/rotulagem/f20-33-verificacao-criterio-4.md` — `role_family`
      ativo (76/648 = 11,7% `UNKNOWN`), nenhum `source_type` amplo novo no banco (21 linhas,
      só `ashby`/`greenhouse`/`lever`/`manual`/`remotive`), Remotive é a única fonte
      `enabled=true` com busca por termo, e
      `git diff --stat b7f432e~1..e9be146 -- scripts/enable_sources.py` retorna vazio
      (confirmado nesta sessão): o gate de homologação não foi tocado no intervalo de
      commits do card.

## Verificação

- **CI:** teste da derivação de termos, da rotação entre execuções e do registro dos
  termos na execução; teste do coletor Remotive recebendo os termos derivados.

## Arquivos prováveis

- `src/opportunity_radar/profile/domain.py`, `profile/models.py`
- `src/opportunity_radar/worker.py`, `acquisition/scheduling.py`
- `apps/web/src/routes/ProfilePage.tsx`
- `docs/pesquisas/*-fontes-amplas.md` (novo)

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/profile/domain.py` | `EmploymentPreference` declara `target_titles`; `ProfileSnapshot.validate` rejeita duplicatas. |
| Alterar | `src/opportunity_radar/profile/models.py` | `EmploymentPreferenceModel.target_titles` usa `ARRAY(String(128))`, não nulo e com defaults vazios. |
| Criar | `migrations/versions/20260926_0035_target_titles.py` | Adiciona e remove `target_titles` em `profile.employment_preference`; revisa `20260926_0034`, única head confirmada antes da criação. |
| Alterar | `src/opportunity_radar/profile/service.py` | `_apply_snapshot` grava `target_titles`; `_to_domain` carrega o campo para respostas e edições subsequentes. |
| Alterar | `src/opportunity_radar/presentation/http/profile.py` | `PreferenceBody` normaliza e deduplica cargos sem vocabulário fechado; `_preferences` passa a lista ao domínio. |
| Criar | `src/opportunity_radar/profile/keywords.py` | Derivação de palavras-chave (cargos-alvo + skills de maior nível, normalizadas, sem duplicata) e a rotação em blocos de até 10. |
| Alterar | `src/opportunity_radar/acquisition/models.py` | Reusar `SourceCheckpointModel` (`checkpoint_type` e `cursor`); nenhum campo novo. |
| Alterar | `src/opportunity_radar/worker.py` | `_scheduled_request` deriva termos Remotive do perfil e complemento de configuração; checkpoint só avança após lote `SUCCEEDED` confirmado. |
| Alterar | `apps/web/src/features/profile/api.ts` | Adicionar `targetTitles` a tipos, parse, defaults e serialização da API. |
| Alterar | `apps/web/src/routes/ProfilePage.tsx` | Adicionar campo "Cargos-alvo" ao lado de áreas de interesse e enviar com o perfil salvo. |
| Criar | `docs/pesquisas/2026-09-fontes-amplas.md` | Pesquisa de fontes com API pública e busca por termo, cada uma com a mesma revisão de termos do F20-28 a F20-32. Entregável do card; os coletores ficam para sub-cards futuros. |

## Interfaces

```python
# src/opportunity_radar/profile/domain.py
@dataclass(frozen=True)
class EmploymentPreference:
    ...
    target_titles: tuple[str, ...] = ()  # cargos-alvo, ex.: "backend engineer"


# src/opportunity_radar/profile/keywords.py
def derive_keywords(preferences: EmploymentPreference, skills: tuple[Skill, ...]) -> tuple[str, ...]:
    """Cargos-alvo + skills de maior nível, normalizados e sem duplicata.
    `configuration["keywords"]` (worker.py:356, texto herdado) continua valendo
    como complemento explícito, não substituído."""


def rotate(terms: tuple[str, ...], *, block_index: int, block_size: int = 10) -> tuple[str, ...]:
    """Bloco de até `block_size` termos a partir de `block_index`, dando a volta
    quando o índice passa do fim — nenhum termo fica permanentemente sem visita."""


@dataclass(frozen=True, slots=True)
class KeywordRotationState:
    block_index: int
    terms_used: tuple[str, ...]
```

## Passos

1. Escrever os testes da derivação de termos (`derive_keywords`) e da rotação (`rotate`) antes do código, cobrindo cargos-alvo, skills de maior nível e o retorno ao início da lista.
2. Adicionar `target_titles` a `EmploymentPreference` (`domain.py`, linha 63-78) e validar duplicata em `ProfileSnapshot.validate` (linha 129-130).
3. Adicionar a coluna `target_titles` a `EmploymentPreferenceModel` (`models.py`, linha 252-257) e a migração correspondente.
4. Adicionar `target_titles` a `PreferenceBody` (`presentation/http/profile.py`, linha 56-77) e ao `_preferences` (linha 203-212).
5. Criar `src/opportunity_radar/profile/keywords.py` com `derive_keywords` e `rotate`, sem usar nenhum modelo de linguagem (a "Ajustes da Fase 20" proíbe LLM aqui).
6. Reaproveitar `SourceCheckpointModel` (`acquisition/models.py`, linha 359-384) com `checkpoint_type="keyword_rotation"` para guardar o índice do próximo bloco; escrever o teste de que o índice só avança após confirmação durável (falha/reinício não pula termos).
7. Alterar `_scheduled_request` (`worker.py`, linha 531-559) para, no coletor Remotive, derivar os termos do perfil ativo via `derive_keywords`, aplicar `rotate` com o índice do checkpoint, e registrar os termos usados na execução (`SourceRunModel` ou telemetria equivalente).
8. Escrever o teste do coletor Remotive recebendo os termos derivados (reaproveitando `tests/backend/acquisition/test_remotive_collector.py`).
9. Adicionar o campo "Cargos-alvo" a `ProfilePage.tsx`, ao lado das áreas de interesse.
10. Escrever a pesquisa `docs/pesquisas/2026-09-fontes-amplas.md`: fontes com API pública e busca por termo, cada uma com revisão de termos própria.
11. Confirmar que nenhuma fonte ampla é habilitada antes do F20-03 estar ativo (mesma regra do F20-25) — teste ou verificação manual documentada no PR.
12. Rodar os comandos de verificação.

## Testes a escrever

- `tests/backend/profile/test_domain.py::test_target_titles_reject_duplicates`
- `tests/backend/profile/test_keywords.py::test_derive_keywords_combines_target_titles_and_top_skills`
- `tests/backend/profile/test_keywords.py::test_rotate_wraps_around_after_last_block`
- `tests/backend/acquisition/test_scheduling.py::test_keyword_rotation_checkpoint_advances_only_after_confirmed_batch`
- `tests/backend/acquisition/test_remotive_collector.py::test_receives_keywords_derived_from_profile`
- `tests/backend/profile/test_profile_preservation.py::test_target_titles_round_trip_through_preference_body`
- `tests/backend/profile/test_profile_preservation.py::test_target_titles_round_trip_through_database`
- `apps/web/src/routes/ProfilePage.test.tsx::shows and saves target titles`

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
docker compose -p f20-33 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/profile/ tests/backend/acquisition/test_scheduling.py tests/backend/acquisition/test_remotive_collector.py
docker compose -p f20-33 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-33 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Evidências F20-33

- `test_target_titles_reject_duplicates` cobre rejeição de cargos duplicados.
- `test_target_titles_round_trip_through_preference_body` cobre normalização e deduplicação
  no contrato HTTP.
- `test_target_titles_round_trip_through_database` cria perfil ativo, salva cargos, confirma
  valores em resposta de escrita, leitura de `/profile` e carregamento do repositório.
- `test_receives_keywords_derived_from_profile` usa perfil falso e `httpx.MockTransport`;
  prova os termos entregues ao coletor sem chamada real à Remotive.
- `worker.py` registra `run_id` e `terms_used` no evento de conclusão da execução. A rotação
  persiste o próximo bloco em `SourceCheckpointModel.cursor` com
  `checkpoint_type="keyword_rotation"`; nenhum campo novo foi adicionado.
- `ProfilePage.test.tsx` confirma que a tela carrega cargos e envia a lista editada na gravação.
- O endpoint `/profile` já declarava o campo na resposta. `test_target_titles_round_trip_through_database`
  agora também prova que o campo chega nele após leitura do banco.
- O critério 4 tem verificação manual documentada acima; não há teste que simule o gate de área.
- `docs/pesquisas/2026-09-fontes-amplas.md` foi entregue separadamente no commit `1c10543`;
  este trabalho não alterou o arquivo.
- Comandos rodados: `pytest -q tests/backend/profile tests/backend/acquisition/test_scheduling.py
  tests/backend/acquisition/test_remotive_collector.py` (dentro dos 99 passed do escopo
  combinado com F20-34); `ruff check .` e `mypy` limpos; `cd apps/web && npm run check`
  agora passa inteiro (lint, typecheck, 134 testes, build) — o bloqueio anterior era o
  `apps/web/src/features/profile/api.test.ts` sem `target_titles` no fixture de
  `preferences`, corrigido junto com o trabalho de F20-34.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
