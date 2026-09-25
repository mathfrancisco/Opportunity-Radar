# CARD F20-32 — Coletor Gupy

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-27, F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-10](../../38-roadmap-ia-e-busca/fase-17/f17-10-coletores-novos.md)

## Ajustes da Fase 20

- Este card é o sub-card de **Gupy** do F17-10. Aplicar o escopo e os critérios abaixo só a Gupy.
- A revisão de termos vem primeiro; se o endpoint proíbe automação, o card fecha como "não viável" com a revisão registrada.
- A ordem entre os cinco coletores segue o relatório do F20-27 e o mapa do F20-35; a numeração não é prioridade.

## Resultado

Os ATS que mais destravam empresas do catálogo ganham coletor, um de cada vez, na ordem
que a descoberta do F20-27 (antigo F17-09) medir, cada um com termos revisados antes de ser escrito.

## Contexto

Hoje o catálogo tem 12 empresas em ATS sem coletor: Workday 4, Teamtailor 3, Workable 2,
Factorial 2, Gupy 1. O F20-27 (antigo F17-09) deve aumentar esses números. Gupy, com pouca presença no
catálogo, é muito usado no mercado brasileiro e pode subir na ordem depois da descoberta.

## Escopo

Este card é um guarda-chuva: **cada ATS vira um sub-card próprio** (F17-10a, F17-10b, …)
quando for iniciado, na ordem do relatório do F20-27 (antigo F17-09). Cada sub-card entrega:

1. **Revisão de termos** do endpoint público, registrada em `docs/pesquisas/` antes de
   qualquer código. Endpoint que proíbe acesso automatizado encerra o sub-card.
2. **Coletor** com a interface dos atuais: `source_type`, `CollectorCapabilities`,
   `discover`, telemetria, política de rede, retentativa, validador de chave.
3. **Board falso** em `tests/e2e/` ou fixture equivalente, com paginação e erro.
4. **Integração** com o resto da Fase 14: `PROBE_TYPES` da sonda, `IDENTIFIER_KEYS` das
   propostas, padrões de chave do F20-03 (antigo F17-04) e assinaturas do F20-27 (antigo F17-09), `SUPPORTED_ATS` do
   cadastro de empresa, formulário de criação de fonte.
5. **Mapeamento** de departamento (F20-03 (antigo F17-02)) e senioridade (F20-02 (antigo F17-06)) só para campos que o
   endpoint realmente expõe.

Endpoints candidatos, **a confirmar na revisão de termos** (não são fato até lá):

| ATS | Forma provável do endpoint público |
| --- | --- |
| Workday | busca JSON por tenant e site (`/wday/cxs/<tenant>/<site>/jobs`), paginada, com detalhe por vaga |
| Teamtailor | página pública de vagas por empresa, com feed |
| Workable | widget público por conta |
| Factorial | página pública de vagas por empresa |
| Gupy | portal público de vagas por empresa |

## Fora de escopo

- Qualquer fonte que exija login ou proíba automação.
- Coletar por raspagem de HTML quando existe endpoint estruturado.

## Notas de implementação

- A ordem sai do relatório do F20-27 (antigo F17-09)/F20-35 (antigo F18-01): empresas canônicas desbloqueadas,
  vagas únicas úteis, custo de integração/manutenção e disponibilidade do endpoint.
  Quantidade de empresas é hipótese de rendimento, não garantia.
- Paginação, detalhe ausente, 429/Retry-After, duplicatas entre páginas e mudança
  de schema entram no contrato de cada coletor; falha nunca parece board vazio.
- Coletor novo só é habilitado depois do F20-03 (antigo F17-02), pela mesma razão do F20-25 (antigo F17-05).

## Critérios de aceite (por sub-card)

- [ ] Termos revisados e registrados antes do código.
- [ ] Coletor com teste contra board falso, incluindo paginação e erro.
- [ ] Sonda, proposta, cadastro e formulário reconhecem o ATS.
- [ ] Pelo menos uma empresa real do catálogo homologada e coletando.

## Verificação

- **CI:** testes do coletor contra o board falso; teste de integração da sonda com o tipo
  novo.
- **Máquina de referência:** primeira coleta real registrada no PR do sub-card.

## Arquivos prováveis

- `src/opportunity_radar/acquisition/<ats>.py` (novo por sub-card)
- `src/opportunity_radar/acquisition/registry.py`, `probing.py`, `proposals.py`
- `src/opportunity_radar/companies/registration.py`
- `apps/web/src/components/SourceCreateForm.tsx`
- `tests/backend/acquisition/`, `tests/e2e/`

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `docs/pesquisas/termos-gupy.md` | Revisão dos termos de uso do endpoint público do Gupy, antes de qualquer código. Se o endpoint proibir automação, este documento é o entregável final do sub-card e ele fecha como "não viável". |
| Criar | `src/opportunity_radar/acquisition/gupy.py` | Coletor do Gupy, no formato de `src/opportunity_radar/acquisition/lever.py` (`LeverCollector`: `source_type`, `capabilities`, `healthcheck`, `discover`, retentativa com `Retry-After`, `validate_*`). |
| Alterar | `src/opportunity_radar/acquisition/registry.py` | `build_collector_registry` (linhas 12-26) monta a tupla de coletores do worker e da API; adicionar `GupyCollector()`. |
| Alterar | `src/opportunity_radar/acquisition/probing.py` | `PROBE_TYPES` (linha 24) e `PUBLIC_ENDPOINT_REFERENCES` (linhas 25-30) só cobrem `ashby`, `lever`, `greenhouse`, `remotive`; adicionar `"gupy"` e a referência ao endpoint público. `probe_request` (linhas 43-62) precisa de um novo `elif source_type == "gupy"` que monte `company_reference` a partir de `configuration["company_identifier"]`. |
| Alterar | `src/opportunity_radar/acquisition/proposals.py` | `IDENTIFIER_KEYS` (linhas 22-26) só mapeia `ashby`/`lever`/`greenhouse`; adicionar `"gupy": "company_identifier"` — nome de campo a confirmar na revisão de termos. |
| Alterar | `src/opportunity_radar/companies/registration.py` | `SUPPORTED_ATS` (linha 48) e o dicionário de `validators` em `_source_values` (linhas 373-376) só cobrem os três ATS atuais; adicionar `"gupy"` e `GupyCollector.validate_company_identifier` (ou o nome que a revisão de termos confirmar). |
| Alterar | `apps/web/src/components/SourceCreateForm.tsx` | `configFields` (linhas 21-58) e `typeLabels` (linhas 60-66) só têm entradas para `ashby`/`lever`/`greenhouse`/`remotive`/`manual`; adicionar `gupy` com o campo `company_identifier` (obrigatório) e `company_name` (opcional), e o rótulo `"Gupy"`. |
| Alterar | `apps/web/src/features/sources/api.ts` | `sourceTypes` (linhas 204-205) é a lista fechada de `SourceType`; adicionar `"gupy"`. |
| Criar | `tests/backend/acquisition/test_gupy_collector.py` | Testes do coletor contra um board falso, no formato de `tests/backend/acquisition/test_lever_collector.py`. |
| Criar | `tests/e2e/fake_gupy_board.py` | Servidor falso do Gupy (paginação, erro, 429), no formato de `tests/e2e/fake_job_board.py`. |

Endpoint provável do Gupy: portal público de vagas por empresa — **a confirmar na revisão de termos**, não é fato até lá.

## Interfaces

```python
# src/opportunity_radar/acquisition/gupy.py
class GupyCollector:
    """Lê vagas públicas do Gupy. Nomes de campo e forma do endpoint dependem
    da revisão de termos em docs/pesquisas/termos-gupy.md."""

    source_type = "gupy"
    capabilities = CollectorCapabilities(company_jobs=True, pagination=True)

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        client_factory: (
            Callable[[], AbstractAsyncContextManager[httpx.AsyncClient]] | None
        ) = None,
        max_retries: int = 2,
        retry_after_seconds: float = 1.0,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None: ...

    async def healthcheck(
        self, context: HealthcheckContext | None = None
    ) -> HealthResult: ...

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        """mecanismo de paginação (se algum) a confirmar na revisão de termos. Falha nunca deve parecer board vazio: página curta só
        conta como fim quando o coletor sabe que é o fim (mesmo contrato do Lever,
        linha 138-142), não só um retorno vazio."""

    @staticmethod
    def validate_company_identifier(value: str) -> str:
        """Formato do identificador a confirmar na revisão de termos."""
```

## Passos

1. Escrever a revisão de termos em `docs/pesquisas/termos-gupy.md` antes de qualquer código: o que o endpoint público permite, exige atribuição, limite de taxa, e se proíbe automação. Se proibir, parar aqui e fechar o sub-card como "não viável", registrando o motivo no card.
2. Confirmar a forma real do endpoint contra a documentação pública encontrada (ou, se preciso, uma chamada manual isolada, nunca dentro do CI) e atualizar a tabela deste card se a forma prevista estiver errada.
3. Escrever os testes do coletor (`tests/backend/acquisition/test_gupy_collector.py`) contra o board falso, cobrindo item válido, paginação, schema alterado e erro HTTP — antes do código do coletor.
4. Criar `tests/e2e/fake_gupy_board.py`, no formato de `tests/e2e/fake_job_board.py`, com paginação e um caminho de erro (404, 429 com `Retry-After`, 500).
5. Implementar `src/opportunity_radar/acquisition/gupy.py`, seguindo a forma de `LeverCollector` (`source_type`, `capabilities`, retentativa com `Retry-After`, classificação de erro HTTP em `AcquisitionErrorCode`, `validate_company_identifier`).
6. Registrar o coletor em `build_collector_registry` (`registry.py`, linhas 12-26).
7. Adicionar `"gupy"` a `PROBE_TYPES` e `PUBLIC_ENDPOINT_REFERENCES` em `probing.py`, e o ramo correspondente em `probe_request`.
8. Adicionar `"gupy": "company_identifier"` a `IDENTIFIER_KEYS` em `proposals.py`.
9. Adicionar `"gupy"` a `SUPPORTED_ATS` e o validador correspondente em `registration.py`.
10. Adicionar o tipo ao formulário (`SourceCreateForm.tsx`) e a `sourceTypes` (`api.ts`).
11. Mapear departamento (F20-03) e senioridade (F20-02) só para os campos que o endpoint do Gupy realmente expõe — não inventar correspondência para campo ausente.
12. Homologar pelo menos uma empresa real do catálogo pela fila de homologação (F20-25) e registrar a primeira coleta real no PR do sub-card.
13. Rodar os comandos de verificação e confirmar que a sonda (`probing.py`) reconhece o novo tipo em um teste de integração.

## Testes a escrever

- `tests/backend/acquisition/test_gupy_collector.py::test_parses_listed_jobs_and_preserves_payload`
- `tests/backend/acquisition/test_gupy_collector.py::test_paginates_until_short_page`
- `tests/backend/acquisition/test_gupy_collector.py::test_retries_rate_limit_using_retry_after`
- `tests/backend/acquisition/test_gupy_collector.py::test_classifies_http_errors`
- `tests/backend/acquisition/test_gupy_collector.py::test_rejects_invalid_identifier_and_schema`
- `tests/backend/acquisition/test_gupy_collector.py::test_skips_malformed_listed_job_and_reports_it`
- `tests/backend/acquisition/test_service.py::test_probe_recognizes_gupy_source_type`
- `tests/backend/companies/test_importer.py::test_registration_accepts_gupy_source_type` (ou equivalente em `test_domain.py`, conforme onde `SUPPORTED_ATS` for exercitado)

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
docker compose -p f20-32 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/acquisition/test_gupy_collector.py tests/backend/acquisition/test_service.py
docker compose -p f20-32 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-32 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
