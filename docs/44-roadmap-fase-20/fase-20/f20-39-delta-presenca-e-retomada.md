# CARD F20-39 — Delta, presença e retomada

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** D — Varredura produtiva
- **Depende de:** F20-38
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-05](../../40-roadmap-varredura-produtiva/fase-18/f18-05-delta-presenca-e-retomada.md); [SPEC 39](../../39-spec-varredura-produtiva.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Dependências antigas de F17 foram fechadas por F20-01 a F20-03.

## Resultado

Revisitar confirma presença sem duplicar conteúdo ou IA; queda de execução retoma sem perda e sem encerramento incorreto.

## Escopo

- Persistir observação por run/item mesmo quando dedupe reaproveita RawItem. Separar hash bruto e hash semântico versionado.
- Hash semântico remove só ruído definido; mudança material invalida derivados, mudança cosmética não obriga inferência.
- 304 só reutiliza inventário completo persistido se toda a representação/manifest de páginas foi revalidada no mesmo escopo; resto fica parcial/desconhecido.
- Commit atômico de evidência, observações e checkpoint. Cursores de retomada, rotação de termos e watermark são distintos.
- Nova rodada completa começa do início; replay antigo não regride last_seen/content e payload expirado permanece explicitamente indisponível.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [ ] Duas visitas iguais atualizam presença sem conteúdo/IA duplicados.
- [ ] 304 não fecha vaga nem mascara inventário incompleto.
- [ ] Quedas antes/depois do commit retomam idempotentemente.
- [ ] Mudança material reprocessa; alteração cosmética não gera onda de análise.

## Verificação

- **CI:** Falhas injetadas entre fetch/commit, cursor repetido, 304 parcial/completo, dedupe, replay fora de ordem e retenção.
- **Máquina de referência:** Medir proporção de bytes, normalizações e inferências evitadas, preservando recall amostral.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`acquisition/service.py`, repository/models, opportunities/service.py, migrations de observações e fixtures.

## Contexto no código

O ponto central deste card já está localizado: `AcquisitionService._persist_item`
(`acquisition/service.py:870-914`) chama
`repository.identical_raw_item_exists(source_id, identity_key, payload_hash)`
(`acquisition/repository.py:103-112`); quando o conteúdo é idêntico, a função devolve
`False` e **nenhuma linha é escrita** — nem `RawItem`, nem qualquer observação de
presença. É exatamente o comportamento que o card pede para mudar: revisitar sem mudança
deve confirmar presença (por exemplo, avançar `last_seen_at`) sem duplicar conteúdo.

- `RawItemModel` (`acquisition/models.py:163-230`) só tem `payload_hash` (hash do
  payload bruto, `canonical_payload_hash` em `service.py:935-942`); não existe um campo
  de hash semântico separado. `uq_raw_item_source_identity_hash` é
  `(source_definition_id, identity_key, payload_hash)` — uma mudança cosmética no HTML
  já muda o `payload_hash` e portanto passaria pelo dedupe atual como "novo", mesmo que
  o conteúdo relevante não tenha mudado.
- `SourceOccurrenceModel` (`opportunities/models.py:199-`) tem
  `UniqueConstraint("raw_item_id", ...)` — uma ocorrência por `raw_item`, com
  `first_seen_at`, `last_seen_at` e `last_seen_run_id` (`opportunities/models.py:245-253`,
  adicionado pela migração `20260925_0025_run_completeness_and_last_seen.py`, card
  F17-07). Isso já separa "visto" de "processado", mas só quando um `RawItem` novo é
  gravado — se o dedupe barra a escrita antes disso (como acontece hoje), `last_seen_at`
  nunca avança.
- `SourceRunModel.complete`/`items_announced` (mesma migração 0025) já marcam se um run
  leu o board inteiro; nenhuma consulta hoje combina isso com "o manifesto de páginas foi
  revalidado por inteiro" para decidir se um 304 pode reaproveitar um inventário completo
  — essa combinação é nova.
- `NormalizationResultModel.identity_decision` já tem o valor `'REFRESHED'`
  (`opportunities/models.py:290-291`), sinal de que o conceito de "mesma identidade,
  conteúdo atualizado" já existe na normalização — o card estende isso com a distinção
  hash bruto vs. hash semântico, não substitui o enum.
- `SourceCheckpointModel.cursor` (`acquisition/models.py:359-384`) é o único cursor de
  retomada hoje; card F20-38 adiciona `etag`/`last_modified` (colunas já existentes, mas
  mortas) — este card consome o resultado desses validadores para decidir o que um 304
  prova, mas não implementa o envio deles (isso é F20-38).

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/acquisition/service.py` | `_persist_item` grava observação de presença mesmo quando o dedupe reaproveita o `RawItem` |
| Alterar | `src/opportunity_radar/acquisition/repository.py` | `identical_raw_item_exists` passa a devolver o `RawItem` reaproveitado, não só `bool` |
| Alterar | `src/opportunity_radar/opportunities/models.py` | `SourceOccurrenceModel` ganha campo(s) de hash semântico e/ou tabela de observação por execução |
| Alterar | `src/opportunity_radar/opportunities/service.py` | decide reprocessamento por hash semântico, não por hash bruto |
| Criar | `migrations/versions/20260926_0041_semantic_hash_and_observation.py` | coluna(s) de hash semântico e/ou tabela de observação (numeração indicativa; ver nota da cabeça no card F20-38) |
| Criar | `tests/backend/acquisition/test_delta_presence_resume.py` | falha entre fetch/commit, cursor repetido, 304 parcial/completo, replay fora de ordem |

## Interfaces

```python
# src/opportunity_radar/acquisition/domain.py (ou novo módulo de delta)
@dataclass(frozen=True, slots=True)
class ContentHashes:
    raw_hash: str        # já existe: canonical_payload_hash(payload)
    semantic_hash: str    # novo: hash dos campos relevantes, ruído versionado excluído
    semantic_hash_version: str  # ex.: "semantic-hash-v1"


def semantic_hash(payload: Mapping[str, Any], *, version: str = "semantic-hash-v1") -> str:
    """Remove só o ruído definido e versionado (espaço, ordem de atributo HTML
    conhecida); mudança material invalida derivados, cosmética não."""


# src/opportunity_radar/acquisition/repository.py
def identical_raw_item_exists(
    self, *, source_id: UUID, identity_key: str, payload_hash: str,
) -> "RawItemModel | None":
    """Assinatura muda de bool para o RawItem reaproveitado, para que o chamador
    grave uma observação de presença apontando para ele."""


# src/opportunity_radar/opportunities/models.py
class SourceOccurrenceObservationModel(Base):
    """Uma linha por (source_occurrence, source_run): presença confirmada, mesmo
    quando o RawItem é reaproveitado do dedupe."""

    source_occurrence_id: "UUID"
    source_run_id: "UUID"
    observed_at: "datetime"
    raw_item_id: "UUID"          # sempre aponta para a evidência existente
    content_hash_matched: bool    # True quando o raw_hash bateu (nenhum conteúdo novo)
```

## Passos

1. Escrever `tests/backend/acquisition/test_delta_presence_resume.py` primeiro, com os
   quatro critérios de aceite como casos: duas visitas idênticas, 304 parcial vs.
   completo, falha injetada entre fetch e commit (idempotência), e replay fora de ordem
   não regredindo `last_seen_at`/conteúdo.
2. Criar a migração para o hash semântico (coluna em `raw_item` ou em
   `normalization_result`, o que for mais barato de popular) e para a tabela de
   observação por execução, seguindo o formato de `20260925_0025_...py`.
3. Implementar `semantic_hash`/`ContentHashes`, com uma lista explícita e versionada de
   ruído excluído (não um filtro heurístico); registrar as duas decisões (hash bruto e
   hash semântico) juntas.
4. Mudar `identical_raw_item_exists` para devolver o `RawItemModel` reaproveitado em vez
   de `bool`, preservando o comportamento de dedupe para os chamadores que só checavam a
   verdade booleana.
5. Em `_persist_item` (`service.py:870-914`), quando o item é idêntico, gravar uma
   `SourceOccurrenceObservationModel` apontando para o `RawItem` existente e avançar
   `SourceOccurrenceModel.last_seen_at`/`last_seen_run_id`, na mesma transação do commit
   do run (evidência, observação e checkpoint atômicos — critério de aceite 3).
6. Definir a regra de reuso de 304: só reaproveitar um inventário completo persistido
   quando `SourceRunModel.complete` for verdadeiro **e** o manifesto de páginas daquele
   escopo tiver sido revalidado por inteiro na mesma execução; qualquer 304 parcial
   marca o resto como parcial/desconhecido, nunca ausente.
7. Garantir que uma nova execução completa começa do início (ignora o cursor de
   execuções anteriores) e que a retomada usa o cursor da mesma execução interrompida —
   os três estados (cursor, rotação de termos, watermark de delta) continuam distintos.
8. Garantir que mudança de `parser_version`/normalizador reprocessa sem rebaixar a
   evidência corrente e sem prometer replay de payload já expirado pela retenção
   (`RawItemPayloadModel.expired_at`, `acquisition/models.py:238-260`).
9. Rodar o comando de verificação e confirmar os quatro critérios de aceite.

## Testes a escrever

- `tests/backend/acquisition/test_delta_presence_resume.py::test_two_identical_visits_update_presence_without_duplicate_content_or_ai` — critério de aceite 1.
- `tests/backend/acquisition/test_delta_presence_resume.py::test_304_does_not_close_job_or_mask_incomplete_inventory` — critério de aceite 2, com um caso de 304 parcial e um de manifesto completo revalidado.
- `tests/backend/acquisition/test_delta_presence_resume.py::test_crash_before_and_after_commit_resumes_idempotently` — injeta falha antes e depois do commit; a repetição não duplica observação nem perde o avanço do checkpoint (critério de aceite 3).
- `tests/backend/acquisition/test_delta_presence_resume.py::test_material_change_reprocesses_cosmetic_does_not` — mudança material dispara nova inferência a jusante; mudança cosmética (hash semântico igual, hash bruto diferente) não (critério de aceite 4).
- `tests/backend/acquisition/test_delta_presence_resume.py::test_out_of_order_replay_does_not_regress_last_seen` — replay de um run antigo não move `last_seen_at`/`last_seen_run_id` para trás.

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
docker compose -p f20-39 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/acquisition/test_delta_presence_resume.py tests/backend/acquisition/test_collection_job.py
docker compose -p f20-39 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-39 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
