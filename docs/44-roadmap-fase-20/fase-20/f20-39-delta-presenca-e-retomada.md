# CARD F20-39 — Delta, presença e retomada

- **Status:** Implementado localmente — critérios de aceite cumpridos e evidenciados; falta confirmar CI verde na branch (ver "Evidência local")
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

- [x] Duas visitas iguais atualizam presença sem conteúdo/IA duplicados. **Confirmado com
      dado real em 2026-09-26:** `make collect` real contra Seedtag (Teamtailor)
      persistiu 19 vagas na 1ª execução e 0 novas (19 revistas) na 2ª, 16s depois. Ver
      `docs/44-roadmap-fase-20/evidencias/homologacao-real-2026-09-26.md` §2.2/§4.
- [x] 304 não fecha vaga nem mascara inventário incompleto.
- [x] Quedas antes/depois do commit retomam idempotentemente. Mecanismo coberto por CI
      com coletores fake. **Atualizado em 2026-09-27:** Workday agora lê `request.cursor`
      como offset e preenche `CollectedItem.cursor` por item (`acquisition/workday.py`);
      confirmado com dado real contra Adobe/Workday na pilha isolada `f20cond` — uma
      coleta real capturou 10 itens (checkpoint `cursor=10`), e uma segunda chamada com
      `cursor="10"` buscou 5 itens genuinamente novos (offset 10-14, sem repetição, 15
      vagas reais distintas ao todo). O caminho de retomada explícita
      (`resume_of_run_id`, exigindo um run `PARTIAL`/`FAILED`) não foi exercido com uma
      queda real do processo nesta sessão — reproduzir uma queda de rede genuína contra o
      board real da Adobe de forma não fabricada ficou fora do tempo desta tarefa; o que
      foi provado é a leitura/escrita real do cursor em si, que é o mecanismo que
      `resume_of_run_id` consome. Os outros 3 coletores (teamtailor/workable/factorial)
      continuam sem paginação real (o board inteiro é uma resposta só), então não há
      "meio de página" para eles. Ver
      `docs/44-roadmap-fase-20/evidencias/http-condicional-2026-09-27.md`.
      **Concluído em 2026-09-28** (pilha isolada `f20resume`, real, não fabricado):
      um `kill -9` real do processo Python no meio de um `execute()` (max_items=100000,
      ~28 páginas reais) não deixou **nenhum** vestígio no banco — nem `SourceRun`, nem
      `RawItem` — confirmando por dado real que o commit é atômico por execução
      (`service.py:1162`) e que `resume_of_run_id` nunca pode nomear um run morto por
      `kill -9` puro (ele nunca chega a existir). Para produzir o `PARTIAL` retomável que
      o critério pede, esta sessão cortou a conexão de verdade (ECONNREFUSED real, TCP,
      não uma exceção levantada à mão) na 2ª chamada HTTP contra a Adobe real, dentro do
      mesmo `execute()`: página 1 (20 vagas reais) persistida, página 2 falha de verdade,
      run `PARTIAL` com `items_persisted=20`. A retomada com `resume_of_run_id` + cursor
      operacional `"20"` sobre um cliente HTTP normal (sem corte) buscou 15 vagas reais
      novas (offset 20-34), `items_skipped=0`, `resumed_from_run_id` gravado, 35
      `RawItem`/35 `external_id` distintos — sem duplicata. Ver
      `docs/44-roadmap-fase-20/evidencias/retomada-real-e-endpoints-2026-09-28.md`.
- [x] Mudança material reprocessa; alteração cosmética não gera onda de análise.

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

## Estado local de implementação

- A migração `20260926_0041` adiciona hash semântico versionado e observações por
  `RawItem`/run; visitas antes da normalização também ficam registradas e são ligadas à
  ocorrência quando ela é criada.
- A revalidação HTTP 304 sem manifesto completo continua incompleta; não autoriza
  encerramento de oportunidades. A migração `20260926_0043` acrescenta o manifesto
  declarado: `CollectionTelemetry.record_manifest`/`record_conditional_response` contam
  quantas representações um coletor declarou e quantas revalidaram 304 na mesma execução;
  `AcquisitionService.execute` só reaproveita a completude de uma execução anterior
  (`repository.has_completed_run`) quando **todas** as representações declaradas
  revalidaram 304 nesta execução, sem cursor de sufixo e sem item novo — uma 304 nua
  (sem manifesto declarado) permanece incompleta como antes.
- Retomada da mesma execução: a mesma migração adiciona `source_run.resumed_from_run_id`.
  Uma execução `PARTIAL`/`FAILED` com evidência persistida (`items_persisted > 0`) pode ser
  nomeada por uma execução seguinte via `CollectionRequest.resume_of_run_id` — sempre junto
  de um `cursor` explícito, nunca derivado automaticamente. É só proveniência: o checkpoint
  do próprio run interrompido continua sem promoção automática
  (`test_partial_run_does_not_promote_checkpoint` permanece intacto e verde), e o prefixo já
  persistido continua protegido pelo dedupe existente, não por uma nova regra.
- Medição operacional: `dashboard/metrics.py` conta, por fonte e por janela,
  `presence_confirmed_without_reprocessing` — revisitas cujo hash bruto bateu com o que já
  existia, ou seja, presença confirmada sem normalização nem IA — exposta em
  `GET /api/source-metrics`. Bytes evitados continuam fora do CI (nenhum coletor real ainda
  envia condicionais), conforme "Fora de escopo".
- **Aceito em 2026-09-27:** armazenamento de variantes de parser (migração
  `20260926_0042`) foi validado contra um banco Postgres real (pilha isolada `f20cond`,
  não a suíte mockada de `test_parser_variants.py` já existente) por
  `test_a_real_parser_upgrade_appends_a_variant_instead_of_colliding`
  (`tests/backend/acquisition/test_parser_variants.py`): três execuções reais de
  `AcquisitionService.execute` sobre o mesmo payload bruto — parser v1, parser v2 (uma
  mudança real de interpretação sobre os mesmos bytes) e v2 de novo (uma revisita simples)
  — confirmam que a chave ampliada aceita as duas primeiras como evidência distinta
  (`items_persisted == 1` cada, dois `RawItem` com `payload_hash` igual e `semantic_hash`
  diferente) e ainda deduplica a terceira (`items_persisted == 0`, presença confirmada).
  A restrição `uq_raw_item_source_identity_hash` ampliada não colidiu nem perdeu evidência
  em nenhum dos três casos. Critério de aceite considerado cumprido; não há mais pendência
  de "validação no banco compartilhado" para esta migração.

### Evidência local

- `tests/backend/acquisition/test_delta_presence_resume.py`: 16 testes Postgres passaram
  (9 anteriores + 3 de manifesto declarado + 2 de retomada explícita + a correção do
  `_Fixture.cleanup()` que também remove observações sem ocorrência vinculada).
- `tests/backend/dashboard/test_metrics.py`: 9 testes Postgres passaram, incluindo
  `test_presence_confirmed_without_reprocessing_counts_matched_revisits`.
- `tests/backend/opportunities/test_delta_normalization.py`: 5 regressões de replay e
  atualização de presença passaram.
- Suíte completa com `RUN_DATABASE_INTEGRATION=1` contra banco Postgres recriado do zero
  (`docker compose -p f20w down --volumes` seguido de `pytest -q`): 858 passaram,
  10 ignorados, 0 falharam. `ruff check .` e `mypy` limpos.
- CI `36279883936`: aprovou backend lint, backend tests, migrations e frontend após
  `973b648`, mas falhou no Compose E2E na asserção de `taxonomy_version` (esperava o
  literal desatualizado `"skills-v1"`; o normalizador usa `"skills-v2"` desde F20-02,
  `docs/pesquisas/curadoria-skills-v2.md`). Reproduzido localmente com
  `docker compose -p f20e2e -f compose.yaml -f compose.ci.yaml` isolado do projeto
  `opportunity-radar`; corrigidos os dois literais em `.github/workflows/pipeline.yml`
  (linhas do fluxo de aquisição manual e de matching). Este card não depende dessa
  correção para seus critérios, mas ela desbloqueia o gate de CI da branch.

### Evidência local — 2026-09-27 (cursor real do Workday, condicionais HTTP, migração 0042)

- Workday (`acquisition/workday.py`) agora lê `request.cursor` como offset e preenche
  `CollectedItem.cursor`; os 8 coletores HTTP (ashby/greenhouse/lever/remotive/workday/
  teamtailor/workable/factorial) enviam `If-None-Match`/`If-Modified-Since` e reportam
  304/`ETag`/`Last-Modified` via `acquisition/http_conditional.py` (helper compartilhado).
- `tests/backend/acquisition/test_{ashby,greenhouse,lever,remotive,teamtailor,workable,
  factorial,workday}_collector.py`: 123 testes verdes na pilha isolada `f20cond`,
  incluindo os novos casos de cabeçalho condicional, 304 e (Workday) cursor/resume.
- `tests/backend/acquisition/test_parser_variants.py::test_a_real_parser_upgrade_appends_a_variant_instead_of_colliding`:
  novo teste de integração com Postgres real, decide o item pendente da migração `0042`
  (ver "Estado local de implementação" acima).
- Suíte completa (`RUN_DATABASE_INTEGRATION=1`, pilha `f20cond`, banco recriado do zero
  pelas migrations): 878 passaram, 10 ignorados, 0 falharam. `ruff check .` e `mypy`
  limpos.
- Medição com dado real (boards públicos, sem tocar `opportunity-radar`): ver
  `docs/44-roadmap-fase-20/evidencias/http-condicional-2026-09-27.md` — 304 real
  confirmado no Greenhouse (Lokalise) e Teamtailor (Seedtag), bytes evitados medidos por
  `curl` direto (19.820 e 345.111 bytes), e cursor real de retomada no Workday (Adobe: 10
  itens + 5 itens novos via `cursor="10"`, 15 vagas reais distintas ao todo, sem
  repetição).

### Evidência local — 2026-09-28 (queda real de processo e retomada via `resume_of_run_id`)

- Pilha isolada `f20resume`. `kill -9` real contra o processo Python em execução real
  (não fabricada) confirmou zero estado persistido para uma morte antes do commit final
  (nenhum `SourceRun`, nenhum `RawItem`) — coerente com
  `test_crash_before_commit_leaves_no_partial_state_and_retry_succeeds`, agora também
  provado fora do CI, com um `kill -9` de verdade, não uma exceção simulada.
- Um corte real de conexão TCP (`ECONNREFUSED`, não fabricado) na 2ª página de uma coleta
  real contra Adobe/Workday produziu um run `PARTIAL` com 20 vagas reais persistidas
  (`d539bab1-84a8-478f-b900-3ce4133467f3`). A retomada via `resume_of_run_id` + cursor
  operacional `"20"` (`48037fbf-7245-4084-bf1d-e23d9e1e19ce`) buscou 15 vagas reais novas,
  sem duplicata (35 `RawItem`/35 `external_id` distintos) e sem itens pulados.
- Nenhuma chamada ao Groq (`AI_ENABLED=false`); nenhuma mutação na pilha real
  `opportunity-radar`. Ver
  `docs/44-roadmap-fase-20/evidencias/retomada-real-e-endpoints-2026-09-28.md`.
