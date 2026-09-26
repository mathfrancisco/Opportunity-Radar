# CARD F20-26 — Candidato a duplicata (sem sinal vetorial)

- **Status:** WIP parcial — snapshot integrado; critérios de aceite pendentes.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-01
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-08](../../38-roadmap-ia-e-busca/fase-17/f17-08-candidato-a-duplicata.md); SPEC 43 §9

## Ajustes da Fase 20

- Sem embedding nesta fase: só a regra `title_location_window` entra. Ignorar os trechos sobre sinal vetorial, cosseno e vetores fixos.
- O valor `embedding` pode ficar no enum da regra para uso futuro, sem gerador.

## Resultado

A mesma vaga anunciada em duas fontes, em dias diferentes, aparece como "possível
duplicata" para o operador confirmar ou recusar; a confirmação junta as duas, e nada é
juntado sem regra exata ou confirmação humana.

## Contexto

O fingerprint inclui o dia da publicação (`opportunities/domain.py:876`), de propósito,
para não juntar republicações antigas. O efeito colateral é que a mesma vaga, publicada
num board da empresa e numa fonte ampla em dias diferentes, vira duas oportunidades.

## Escopo

- **Tabela `opportunities.duplicate_candidate`:** par ordenado de oportunidades, regra que
  gerou (`title_location_window` ou `embedding`), pontuação, status (`PENDING`,
  `CONFIRMED`, `REJECTED`), quem decidiu e quando.
- **Detecção** depois da normalização:
  - regra exata-relaxada: mesma empresa canônica, mesmo título normalizado, mesma
    localização normalizada, publicações a até 14 dias;
  - ~~sinal vetorial (cosseno ≥ 0,95)~~ — fora da Fase 20 (SPEC 43 §9).
- **Tela:** selo "possível duplicata" na Inbox e, no detalhe, as duas vagas lado a lado
  com as diferenças destacadas e os botões "É a mesma vaga" / "São vagas diferentes".
- **Confirmar** junta as ocorrências na oportunidade mais antiga e marca a outra como
  duplicata dela, preservando procedência e avaliações. **Recusar** grava o par para não
  sugerir de novo.
- **Métrica:** taxa de duplicatas no relatório do F20-01 (antigo F17-01), antes e depois.

## Fora de escopo

- Junção automática. Uma regra aprendida por par de fontes, depois de N confirmações, é
  avaliada num card próprio com os dados deste.

## Notas de implementação

- A junção reaproveita a lógica de `MERGED` da normalização; a oportunidade absorvida não
  é apagada, ganha `duplicate_of`.
- Uma única candidatura ativa na vaga absorvida pode ser movida com histórico.
  Duas candidaturas ativas bloqueiam a junção com conflito acionável; não escolher
  uma nem encerrar outra automaticamente.

## Contrato de junção

- Confirmar exige versões esperadas de ambas as oportunidades, transação única e
  operação idempotente. Confirmar novamente retorna a mesma resolução.
- Preservar procedência, avaliações históricas, marcas e candidaturas; redirecionar
  ids absorvidos. Avaliações antigas não viram avaliações atuais da sobrevivente.
- Registrar antes/depois e ids movidos para permitir correção supervisionada.
  Conflitos de marcação ficam explícitos; não escolher silenciosamente.
- Impedir ciclos de `duplicate_of` e normalizar pares. Candidatos vetoriais exigem
  vetores atuais. Recusa é contextualizada por versão, com política para revisão
  após mudança material; não sugerir o mesmo par inalterado repetidamente.

## Critérios de aceite

- [ ] Pares que atendem a regra viram candidatos, sem juntar nada sozinhos.
- [ ] Confirmar junta ocorrências e preserva procedência; recusar não sugere de novo.
- [ ] A taxa de duplicatas é medida antes e depois.

- [ ] Duas candidaturas ativas geram conflito sem mutação parcial.
- [ ] Repetição, concorrência, ids antigos e ciclo de duplicatas têm cobertura no CI.
- [ ] Junção não perde marcas/histórico e invalida avaliações derivadas quando necessário.

## Verificação

- **CI:** testes da detecção (dentro e fora da janela, empresas diferentes), da junção e
  da recusa; teste do sinal vetorial com vetores fixos.

## Arquivos prováveis

- `src/opportunity_radar/opportunities/duplicates.py` (novo), `service.py`, `models.py`
- `migrations/versions/*_duplicate_candidate.py`
- `src/opportunity_radar/presentation/http/opportunities.py`
- `apps/web/src/routes/InboxPage.tsx`, `OpportunityDetailPage.tsx`

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `src/opportunity_radar/opportunities/duplicates.py` | Regra `title_location_window`, geração de candidatos após a normalização, e a operação de junção/recusa. |
| Alterar | `src/opportunity_radar/opportunities/models.py` | `OpportunityModel` (linha 36-136) não tem coluna `duplicate_of`; adicionar `duplicate_of: Mapped[UUID \| None]` (FK para `opportunity.id`) e criar `DuplicateCandidateModel` (`opportunities.duplicate_candidate`), ao lado de `RelevanceMarkModel` (linha 159) e `SourceOccurrenceModel` (linha 199). |
| Alterar | `src/opportunity_radar/opportunities/service.py` | `OpportunityService` (linha 84) já tem `transition` com versão esperada (linha 382-415, `OpportunityVersionConflictError` na linha 72) — mesmo padrão de UPDATE condicional para `confirm_duplicate`/`reject_duplicate`. Chamar a detecção depois da normalização (perto de `_new_opportunity`, linha 826). |
| Criar | `migrations/versions/20260926_0033_duplicate_candidate.py` | Cria `opportunities.duplicate_candidate` e a coluna `opportunity.duplicate_of`. Número indicativo: `alembic heads` hoje aponta para `20260925_0029`; F20-12/19/23 reservam 0030-0032, então este card usa 0033 ou o que `alembic heads` indicar na hora de escrever. |
| Alterar | `src/opportunity_radar/presentation/http/opportunities.py` | Adicionar rotas `GET /opportunities/{id}/duplicate-candidates`, `POST /opportunities/duplicate-candidates/{id}/confirm` e `.../reject`, no mesmo estilo de `transition`/`mark_relevance` já expostos aqui. |
| Alterar | `apps/web/src/routes/InboxPage.tsx` | Selo "possível duplicata" no card da lista (perto de `RelevanceButtons`, linha 170). |
| Alterar | `apps/web/src/routes/OpportunityDetailPage.tsx` | Comparação lado a lado das duas vagas com diferenças destacadas e os botões "É a mesma vaga" / "São vagas diferentes". |

## Interfaces

```python
# src/opportunity_radar/opportunities/models.py
class DuplicateCandidateModel(Base):
    __tablename__ = "duplicate_candidate"
    __table_args__ = (
        CheckConstraint(
            "rule IN ('title_location_window', 'embedding')",  # 'embedding' reservado, sem gerador nesta fase
            name="ck_duplicate_candidate_rule",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'REJECTED')",
            name="ck_duplicate_candidate_status",
        ),
        CheckConstraint(
            "opportunity_id < duplicate_opportunity_id",  # par ordenado, sem duplicar (a,b)/(b,a)
            name="ck_duplicate_candidate_ordered_pair",
        ),
        UniqueConstraint(
            "opportunity_id", "duplicate_opportunity_id",
            name="uq_duplicate_candidate_pair",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID]
    opportunity_id: Mapped[UUID]           # FK opportunity.id, menor id do par
    duplicate_opportunity_id: Mapped[UUID]  # FK opportunity.id, maior id do par
    rule: Mapped[str]
    score: Mapped[Decimal | None]
    status: Mapped[str]  # default "PENDING"
    decided_by: Mapped[str | None]
    decided_at: Mapped[datetime | None]
    created_at: Mapped[datetime]


# src/opportunity_radar/opportunities/duplicates.py
def find_title_location_window_candidates(
    session: Session, opportunity: OpportunityModel
) -> list[DuplicateCandidateModel]:
    """Mesma empresa canônica, mesmo título e localização normalizados,
    publicações a até 14 dias — nunca junta, só registra o par."""


class DuplicateConflictError(Exception):
    """Duas candidaturas ativas em ambas as oportunidades: a junção para aqui."""


def confirm_duplicate(
    session: Session,
    candidate_id: UUID,
    *,
    expected_version_survivor: int,
    expected_version_absorbed: int,
    decided_by: str,
) -> DuplicateCandidateModel:
    """Idempotente: confirmar de novo retorna a mesma resolução. Preserva
    procedência, marcas e avaliações; redireciona ocorrências para a mais antiga."""


def reject_duplicate(
    session: Session, candidate_id: UUID, *, decided_by: str
) -> DuplicateCandidateModel:
    """Grava o par como REJECTED; a mesma dupla, sem mudança material, não volta a ser sugerida."""
```

## Passos

1. Escrever os testes de `find_title_location_window_candidates` (dentro/fora da janela de 14 dias, empresas diferentes) antes do código.
2. Criar a migração `migrations/versions/20260926_0033_duplicate_candidate.py` com `duplicate_candidate` e a coluna `opportunity.duplicate_of` (nullable, FK para `opportunity.id`, `ondelete="SET NULL"`).
3. Adicionar `DuplicateCandidateModel` a `src/opportunity_radar/opportunities/models.py`, ao lado de `RelevanceMarkModel`.
4. Criar `src/opportunity_radar/opportunities/duplicates.py` com a regra `title_location_window`, usando `normalize_title`/`normalize_company_name`/`normalize_location` (`domain.py`, linhas 288-310) para comparar.
5. Ligar a detecção ao fim da normalização em `service.py` (perto de `_new_opportunity`, linha 826): toda vez que uma oportunidade nova ou atualizada é persistida, procurar candidatos e inserir os que ainda não existem (idempotente por `UniqueConstraint`).
6. Implementar `confirm_duplicate` seguindo o padrão de `transition` (linha 382-415): UPDATE condicional por `version` em ambas as oportunidades numa única transação; reatribuir `SourceOccurrenceModel.opportunity_id` da absorvida para a sobrevivente; marcar `duplicate_of`.
7. Implementar o bloqueio por conflito: se ambas as oportunidades têm candidatura ativa (`ApplicationProcessModel`, `pipeline/models.py`), levantar `DuplicateConflictError` sem mutação parcial (tudo dentro da mesma transação).
8. Implementar `reject_duplicate` gravando `status=REJECTED`, `decided_by`, `decided_at`.
9. Expor as três rotas em `presentation/http/opportunities.py`, devolvendo `409` em `DuplicateConflictError`/`OpportunityVersionConflictError`.
10. Adicionar o selo "possível duplicata" na Inbox e a comparação lado a lado no detalhe, com os botões de confirmar/recusar.
11. Adicionar a métrica de taxa de duplicatas ao relatório do F20-01 (antes/depois), reaproveitando a contagem de `duplicate_candidate`.
12. Escrever os testes de repetição (confirmar duas vezes), concorrência (versão obsoleta), ids antigos redirecionados e ciclo de `duplicate_of` (A→B→A deve ser rejeitado na escrita).

## Testes a escrever

- `tests/backend/opportunities/test_domain.py::test_title_location_window_matches_within_14_days`
- `tests/backend/opportunities/test_domain.py::test_title_location_window_ignores_different_company`
- `tests/backend/opportunities/test_service.py::test_confirm_duplicate_merges_and_preserves_provenance`
- `tests/backend/opportunities/test_service.py::test_reject_duplicate_does_not_resuggest_unchanged_pair`
- `tests/backend/opportunities/test_service.py::test_confirm_duplicate_is_idempotent_on_retry`
- `tests/backend/opportunities/test_service.py::test_confirm_duplicate_rejects_stale_version`
- `tests/backend/opportunities/test_service.py::test_two_active_applications_raise_conflict_without_partial_mutation`
- `tests/backend/opportunities/test_service.py::test_duplicate_of_cycle_is_rejected`
- `tests/backend/dashboard/test_metrics.py::test_duplicate_rate_reported_before_and_after`

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
docker compose -p f20-26 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/opportunities/test_domain.py tests/backend/opportunities/test_service.py tests/backend/dashboard/test_metrics.py
docker compose -p f20-26 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-26 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
