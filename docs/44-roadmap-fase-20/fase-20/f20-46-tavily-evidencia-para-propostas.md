# CARD F20-46 — Evidência da Tavily para propostas de fonte

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** E — Tavily
- **Depende de:** F20-44, F20-25
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F19-05](../../42-roadmap-tavily/fase-19/f19-05-evidencia-para-propostas.md); [SPEC 41](../../41-spec-tavily.md)

## Ajustes da Fase 20

- Sem mudança de escopo. A Tavily é busca e extração, não LLM; o orçamento de créditos é separado da quota do Groq.

## Resultado

Quando a Tavily encontra um resultado que aponta para um board de ATS já coberto pelo
radar (Ashby, Greenhouse, Lever) numa empresa sem `CompanySource` habilitada para esse
board, a evidência vira proposta de fonte na mesma fila que `scripts/discover_sources.py`
já alimenta — sem ingestão duplicada e sem pular sonda/homologação.

## Contexto

O F20-44 (antigo F19-02) já marca esses resultados como `source_proposal_candidate` em vez de segui-los
como ingestão comum. Este card decide o que fazer com a marca: hoje ela não vira nada, e
a evidência se perde ao fim da execução.

## Escopo

- Rotina que lê os `CollectedItem` marcados `source_proposal_candidate=True` ao fim de
  uma execução da Tavily e cria (ou atualiza, se já existir e ainda estiver inerte) uma
  `SourceDefinition` proposta — mesmo formato de evidência que a F12-03 já usa: URL, ATS
  detectado, método de detecção (`"tavily_search"`), e o trecho que sustenta a
  identificação.
- Toda proposta nasce inerte: `terms_reviewed=false`, `collector_local_tested=false`,
  como qualquer proposta de `discover_sources.py` — este card não homologa nem habilita
  nada.
- Reexecução idempotente: a mesma URL/empresa não duplica proposta; evidência nova para
  uma proposta ainda inerte segue o mesmo caminho de correção que `proposals.py`
  (`follow_correction`) já define para propostas nascidas de `CompanySource`.
- Registro de qual via originou a proposta (Tavily vs. descoberta em HTML do F20-27 (antigo F17-09) vs.
  varredura do F20-36 (antigo F18-02)), para poder medir taxa de acerto por via depois.

## Fora de escopo

- Marcar termos como revisados ou testar localmente.
- Homologar ou habilitar a fonte proposta.
- Ingestão da vaga encontrada como oportunidade — a Tavily não coleta o board inteiro,
  só aponta a existência dele; quem coleta é o collector nativo do ATS, depois de
  habilitado.
- Alterar a fila de homologação da F20-25 (antigo F17-05) — este card só alimenta a mesma fila.

## Notas de implementação

- Reusar `IDENTIFIER_KEYS` de `acquisition/proposals.py` para extrair a chave do board a
  partir da URL, no mesmo padrão por ATS que a Frente A da SPEC de busca já define
  (`jobs.ashbyhq.com/<chave>`, `boards.greenhouse.io/<chave>`, `jobs.lever.co/<chave>`).
  Link fora do padrão não gera proposta automática — vira pendência, com o motivo, como
  a mesma Frente A já trata para links de pesquisa manual.
- A evidência guarda a consulta e o `rank`/`score` que a Tavily devolveu (metadata do
  F20-44 (antigo F19-02)), para auditoria de por que aquele resultado apareceu.
- Duas empresas diferentes apontando para o mesmo board por engano é erro de dado, não
  de proposta — a rotina não tenta resolver ambiguidade de empresa aqui.

## Critérios de aceite

- [ ] Resultado marcado `source_proposal_candidate` vira proposta inerte com evidência
      auditável (URL, ATS, método, trecho).
- [ ] Proposta nasce com `terms_reviewed=false` e `collector_local_tested=false`.
- [ ] Reexecução sobre o mesmo resultado não duplica proposta.
- [ ] URL fora do padrão de chave conhecido vira pendência registrada, não proposta
      malformada.
- [ ] A via de origem (Tavily) fica registrada na proposta, distinta de F20-27 (antigo F17-09)/F20-36 (antigo F18-02).

## Verificação

- **CI:** fixture com URL de board conhecido gera uma única proposta inerte auditável;
  fixture com URL fora do padrão vira pendência; segunda execução sobre os mesmos dados
  não duplica; teste de idempotência com `proposals.py`.
- **Máquina de referência:** sem chamada real à Tavily; usa fixtures de `CollectedItem`
  já marcados pelo F20-44 (antigo F19-02).

## Arquivos prováveis

- `src/opportunity_radar/acquisition/proposals.py`
- `src/opportunity_radar/acquisition/tavily.py`
- `scripts/discover_sources.py` (se a rotina reusar o mesmo script)
- `tests/acquisition/test_tavily_proposals.py` (novo)

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/acquisition/proposals.py` | reusar `IDENTIFIER_KEYS` (`proposals.py:20-24`) para a nova rotina de evidência |
| Alterar | `src/opportunity_radar/acquisition/service.py` | novo método em `AcquisitionService`, ao lado de `propose_company_source` (`service.py:260-298`), que reusa `create_source` (mesmo método que `propose_company_source` já chama) |
| Alterar | `src/opportunity_radar/acquisition/tavily.py` | reusar `detect_ats_board()` do F20-44 na leitura dos itens marcados |
| Criar | `tests/backend/acquisition/test_tavily_proposals.py` | testes deste card (não `tests/acquisition/`, ver nota do F20-42) |

Nenhuma migração: a via de origem (`"discovery_via": "tavily_search"`) entra na coluna
JSONB `configuration` de `SourceDefinitionModel` que já existe (`models.py:59-63`), no
mesmo padrão que `discovery_evidence` já usa (`service.py:297`, `proposals.py:96`).

## Interfaces

```python
# acquisition/service.py — ao lado de propose_company_source (service.py:260)
class AcquisitionService:
    def propose_from_tavily_evidence(
        self, items: Iterable[CollectedItem]
    ) -> TavilyProposalReport:
        """Lê os CollectedItem com metadata["source_proposal_candidate"] is True,
        detecta o board via detect_ats_board() (F20-44) e cria/atualiza uma proposta
        inerte por par (source_type, board_key) — nunca duplica, nunca homologa."""
        ...

@dataclass(frozen=True, slots=True)
class TavilyProposalOutcome:
    url: str
    outcome: Literal["created", "already_proposed", "unmatched_pattern", "company_not_found"]
    proposal_id: UUID | None = None

@dataclass(frozen=True, slots=True)
class TavilyProposalReport:
    outcomes: tuple[TavilyProposalOutcome, ...]
```

A ambiguidade de qual `Company` corresponde a um `CollectedItem.company_name` de texto
livre não tem resolvedor existente no código (nenhuma função de match de empresa por
nome foi encontrada em `companies/`); **a confirmar**: este card usa igualdade exata
com `Company.canonical_name` como primeira aproximação e trata "sem correspondência
exata" como `company_not_found` (pendência registrada, não proposta malformada), e não
resolvedor difuso — decisão a documentar no PR, coerente com "Fora de escopo" já dizer
que ambiguidade entre empresas não é resolvida aqui.

## Exemplos

Item de entrada (emitido pelo F20-44, com o campo de proposta marcado):

```python
CollectedItem(
    source_type="tavily_search",
    url="https://boards.greenhouse.io/acme/jobs/12345",
    company_name="Acme Corp",
    metadata={
        "query": "backend engineer remote brazil",
        "rank": 0,
        "score": 0.87,
        "source_proposal_candidate": True,
    },
)
```

Configuração resultante da `SourceDefinitionModel` proposta (mesmo formato de
`propose_company_source`, `service.py:288-298`, mais a via de origem):

```json
{
  "company_name": "Acme Corp",
  "board_token": "acme",
  "discovery_evidence": "https://boards.greenhouse.io/acme/jobs/12345",
  "discovery_via": "tavily_search",
  "discovery_query": "backend engineer remote brazil",
  "discovery_rank": 0,
  "discovery_score": 0.87
}
```

`evidence_status="ats_identified"`, `terms_reviewed=False`, `collector_local_tested=False`
— os mesmos valores que `create_source`/`propose_company_source` já produzem.

## Passos

1. Escrever `tests/backend/acquisition/test_tavily_proposals.py` para cada critério de
   aceite (ver "Testes a escrever") — falham até a rotina existir.
2. Implementar `propose_from_tavily_evidence` em `service.py`, filtrando os
   `CollectedItem` com `metadata.get("source_proposal_candidate") is True`.
3. Para cada item, chamar `detect_ats_board(item.url)` (F20-44); sem casar, registrar
   `TavilyProposalOutcome(outcome="unmatched_pattern")` — nunca criar proposta
   malformada.
4. Resolver a `Company` por `canonical_name` exato contra `item.company_name`; sem
   correspondência, registrar `outcome="company_not_found"` (pendência).
5. Verificar se já existe `SourceDefinitionModel` com aquele `source_type` +
   `IDENTIFIER_KEYS[source_type]` na `configuration` — se sim, `already_proposed`
   (idempotência).
6. Caso contrário, chamar `create_source(...)` com `evidence_status="ats_identified"`,
   igual a `propose_company_source`, incluindo `discovery_via="tavily_search"` e a
   evidência (query/rank/score) do `metadata` do item.
7. Reexecutar sobre o mesmo `CollectedItem` não deve duplicar — cobrir com teste de
   idempotência (ver "Testes a escrever").
8. Se a proposta já existir e ainda estiver inerte (`is_inert`, `proposals.py:56-61`) e
   a nova evidência apontar para uma chave diferente, seguir o mesmo caminho de
   `follow_correction` (`proposals.py:71-98`) em vez de criar uma segunda proposta.
9. Escrever os testes até verdes; `ruff check .`; `mypy`.

## Testes a escrever

`tests/backend/acquisition/test_tavily_proposals.py`:

- `test_known_board_url_becomes_inert_proposal_with_auditable_evidence` — cobre
  "Resultado marcado `source_proposal_candidate` vira proposta inerte com evidência
  auditável".
- `test_new_proposal_starts_terms_unreviewed_and_untested` — cobre "Proposta nasce com
  `terms_reviewed=false` e `collector_local_tested=false`".
- `test_rerun_over_same_result_does_not_duplicate_proposal` — cobre "Reexecução sobre o
  mesmo resultado não duplica proposta".
- `test_url_outside_known_pattern_becomes_pending_not_malformed_proposal` — cobre "URL
  fora do padrão de chave conhecido vira pendência registrada".
- `test_proposal_records_tavily_as_origin_distinct_from_html_and_sitemap_discovery` —
  cobre "A via de origem (Tavily) fica registrada na proposta, distinta de
  F20-27/F20-36".
- `test_company_not_found_becomes_pending_outcome` — cobre a decisão "a confirmar" do
  passo 4.

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
docker compose -p f20-46 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/acquisition/test_tavily_proposals.py
docker compose -p f20-46 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-46 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
