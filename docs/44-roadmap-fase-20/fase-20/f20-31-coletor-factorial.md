# CARD F20-31 — Coletor Factorial

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-27, F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-10](../../38-roadmap-ia-e-busca/fase-17/f17-10-coletores-novos.md)

## Ajustes da Fase 20

- Este card é o sub-card de **Factorial** do F17-10. Aplicar o escopo e os critérios abaixo só a Factorial.
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

- [x] Termos revisados e registrados antes do código.
- [x] Coletor com teste contra board falso, incluindo paginação e erro.
- [x] Sonda, proposta, cadastro e formulário reconhecem o ATS.
- [ ] Pelo menos uma empresa real do catálogo homologada e coletando. **Pendente** — precisa da
      fila de homologação rodando contra a stack real (fora do CI); não simulado. Ver
      "Pendências" abaixo.

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
| Criar | `docs/pesquisas/termos-factorial.md` | Revisão dos termos de uso do endpoint público do Factorial, antes de qualquer código. Se o endpoint proibir automação, este documento é o entregável final do sub-card e ele fecha como "não viável". |
| Criar | `src/opportunity_radar/acquisition/factorial.py` | Coletor do Factorial, no formato de `src/opportunity_radar/acquisition/lever.py` (`LeverCollector`: `source_type`, `capabilities`, `healthcheck`, `discover`, retentativa com `Retry-After`, `validate_*`). |
| Alterar | `src/opportunity_radar/acquisition/registry.py` | `build_collector_registry` (linhas 12-26) monta a tupla de coletores do worker e da API; adicionar `FactorialCollector()`. |
| Alterar | `src/opportunity_radar/acquisition/probing.py` | `PROBE_TYPES` (linha 24) e `PUBLIC_ENDPOINT_REFERENCES` (linhas 25-30) só cobrem `ashby`, `lever`, `greenhouse`, `remotive`; adicionar `"factorial"` e a referência ao endpoint público. `probe_request` (linhas 43-62) precisa de um novo `elif source_type == "factorial"` que monte `company_reference` a partir de `configuration["company_identifier"]`. |
| Alterar | `src/opportunity_radar/acquisition/proposals.py` | `IDENTIFIER_KEYS` (linhas 22-26) só mapeia `ashby`/`lever`/`greenhouse`; adicionar `"factorial": "company_identifier"` — nome de campo a confirmar na revisão de termos. |
| Alterar | `src/opportunity_radar/companies/registration.py` | `SUPPORTED_ATS` (linha 48) e o dicionário de `validators` em `_source_values` (linhas 373-376) só cobrem os três ATS atuais; adicionar `"factorial"` e `FactorialCollector.validate_company_identifier` (ou o nome que a revisão de termos confirmar). |
| Alterar | `apps/web/src/components/SourceCreateForm.tsx` | `configFields` (linhas 21-58) e `typeLabels` (linhas 60-66) só têm entradas para `ashby`/`lever`/`greenhouse`/`remotive`/`manual`; adicionar `factorial` com o campo `company_identifier` (obrigatório) e `company_name` (opcional), e o rótulo `"Factorial"`. |
| Alterar | `apps/web/src/features/sources/api.ts` | `sourceTypes` (linhas 204-205) é a lista fechada de `SourceType`; adicionar `"factorial"`. |
| Criar | `tests/backend/acquisition/test_factorial_collector.py` | Testes do coletor contra um board falso, no formato de `tests/backend/acquisition/test_lever_collector.py`. |
| Criar | `tests/e2e/fake_factorial_board.py` | Servidor falso do Factorial (paginação, erro, 429), no formato de `tests/e2e/fake_job_board.py`. |

Endpoint provável do Factorial: página pública de vagas por empresa — **a confirmar na revisão de termos**, não é fato até lá.

## Interfaces

```python
# src/opportunity_radar/acquisition/factorial.py
class FactorialCollector:
    """Lê vagas públicas do Factorial. Nomes de campo e forma do endpoint dependem
    da revisão de termos em docs/pesquisas/termos-factorial.md."""

    source_type = "factorial"
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

1. Escrever a revisão de termos em `docs/pesquisas/termos-factorial.md` antes de qualquer código: o que o endpoint público permite, exige atribuição, limite de taxa, e se proíbe automação. Se proibir, parar aqui e fechar o sub-card como "não viável", registrando o motivo no card.
2. Confirmar a forma real do endpoint contra a documentação pública encontrada (ou, se preciso, uma chamada manual isolada, nunca dentro do CI) e atualizar a tabela deste card se a forma prevista estiver errada.
3. Escrever os testes do coletor (`tests/backend/acquisition/test_factorial_collector.py`) contra o board falso, cobrindo item válido, paginação, schema alterado e erro HTTP — antes do código do coletor.
4. Criar `tests/e2e/fake_factorial_board.py`, no formato de `tests/e2e/fake_job_board.py`, com paginação e um caminho de erro (404, 429 com `Retry-After`, 500).
5. Implementar `src/opportunity_radar/acquisition/factorial.py`, seguindo a forma de `LeverCollector` (`source_type`, `capabilities`, retentativa com `Retry-After`, classificação de erro HTTP em `AcquisitionErrorCode`, `validate_company_identifier`).
6. Registrar o coletor em `build_collector_registry` (`registry.py`, linhas 12-26).
7. Adicionar `"factorial"` a `PROBE_TYPES` e `PUBLIC_ENDPOINT_REFERENCES` em `probing.py`, e o ramo correspondente em `probe_request`.
8. Adicionar `"factorial": "company_identifier"` a `IDENTIFIER_KEYS` em `proposals.py`.
9. Adicionar `"factorial"` a `SUPPORTED_ATS` e o validador correspondente em `registration.py`.
10. Adicionar o tipo ao formulário (`SourceCreateForm.tsx`) e a `sourceTypes` (`api.ts`).
11. Mapear departamento (F20-03) e senioridade (F20-02) só para os campos que o endpoint do Factorial realmente expõe — não inventar correspondência para campo ausente.
12. Homologar pelo menos uma empresa real do catálogo pela fila de homologação (F20-25) e registrar a primeira coleta real no PR do sub-card.
13. Rodar os comandos de verificação e confirmar que a sonda (`probing.py`) reconhece o novo tipo em um teste de integração.

## Testes a escrever

- `tests/backend/acquisition/test_factorial_collector.py::test_parses_listed_jobs_and_preserves_payload`
- `tests/backend/acquisition/test_factorial_collector.py::test_paginates_until_short_page`
- `tests/backend/acquisition/test_factorial_collector.py::test_retries_rate_limit_using_retry_after`
- `tests/backend/acquisition/test_factorial_collector.py::test_classifies_http_errors`
- `tests/backend/acquisition/test_factorial_collector.py::test_rejects_invalid_identifier_and_schema`
- `tests/backend/acquisition/test_factorial_collector.py::test_skips_malformed_listed_job_and_reports_it`
- `tests/backend/acquisition/test_service.py::test_probe_recognizes_factorial_source_type`
- `tests/backend/companies/test_importer.py::test_registration_accepts_factorial_source_type` (ou equivalente em `test_domain.py`, conforme onde `SUPPORTED_ATS` for exercitado)

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
docker compose -p f20-31 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/acquisition/test_factorial_collector.py tests/backend/acquisition/test_service.py
docker compose -p f20-31 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-31 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Evidências F20-31

- **Revisão de termos:** `docs/pesquisas/termos-factorial.md`. Conclusão: viável, com
  correção de forma. Achado que corrige a hipótese da tabela deste card e da tabela do
  F17-10: **não existe endpoint JSON público** — a única API pública documentada
  (`api.factorialhr.com`) é a API de administração de RH, autenticada por Bearer token por
  empresa, fora de escopo ("fonte que exige login"). A forma real é uma página HTML
  server-renderizada por empresa (`https://<slug>.factorialhr.com/`), com todas as vagas já
  embutidas na resposta inicial, uma `<li class="job-offer-item">` por vaga, com os fatos
  estruturados em atributos `data-*` (`data-job-postings-url`, `data-team-id`,
  `data-location-id`, `data-is-remote`, `data-contract-type`) e o título/time/local em três
  `<div>` de texto em ordem fixa — verificado ao vivo contra três boards reais de tamanhos
  bem diferentes (`agentero.factorialhr.com`, 2 vagas; `careers.factorialhr.com`, 70+ vagas;
  `currency-solutions.factorialhr.com`). `robots.txt` (idêntico nos três) permite tudo
  (`Allow: /`). Sem paginação real (nenhum parâmro de página nem "carregar mais", nem no
  board de 70+ vagas). Sem campo estruturado de senioridade nem descrição na listagem —
  a descrição completa exigiria uma requisição extra por vaga à página de detalhe, que este
  coletor não faz (YAGNI); nenhum mapeamento F20-02 foi aplicado (nada para mapear). O nome
  do time (F20-03) é a única agregação estruturada exposta e vai em `metadata.team_name`
  para um mapeamento downstream usar.
- **Parser:** lê só os atributos `data-*` documentados e o texto dos três `<div>` de rótulo,
  via `html.parser.HTMLParser` da biblioteca padrão — nenhuma dependência nova adicionada.
  Uma resposta 200 que não é uma página de listagem (falta o marcador `data-controller=
  'job-filters'`) nunca é lida como board vazio; é `PARSER_SCHEMA_CHANGED`.
- **Identificador:** ao contrário de Teamtailor (hostname inteiro, per-domínio), não há
  evidência de que o Factorial suporte domínio customizado para o board público; o
  `company_identifier` é o slug do subdomínio (ex.: `acme` em `acme.factorialhr.com`),
  mesmo formato que Ashby/Lever/Greenhouse, validado por
  `FactorialCollector.validate_company_identifier`.
- **Capacidades:** `CollectorCapabilities(company_jobs=True, pagination=False)` —
  `pagination=False` reflete o achado da revisão de termos, não a hipótese original da
  interface do card (`pagination=True`).

| Critério | Evidência |
| --- | --- |
| Termos revisados e registrados antes do código | `docs/pesquisas/termos-factorial.md` |
| Coletor com teste contra board falso, incluindo paginação e erro | `tests/backend/acquisition/test_factorial_collector.py` (9 testes: item válido, ausência real de paginação — `test_does_not_attempt_a_second_page` —, retentativa com `Retry-After`, 401/403/404/500, timeout/erro de transporte, identificador/schema inválidos, item malformado ignorado e reportado, `max_items`); `tests/e2e/fake_factorial_board.py` (board falso HTTP real, HTML no formato do Factorial, com `?fail=404/429/500/schema`) |
| Sonda, proposta, cadastro e formulário reconhecem o ATS | `probing.py` (`PROBE_TYPES`, `PUBLIC_ENDPOINT_REFERENCES`, ramo `factorial` em `probe_request`) + `tests/backend/acquisition/test_service.py::test_probe_recognizes_factorial_source_type`; `proposals.py` (`IDENTIFIER_KEYS["factorial"]`); `registration.py` (`SUPPORTED_ATS`, validador) + `tests/backend/companies/test_registration.py::test_registration_accepts_factorial_source_type`/`test_registration_rejects_invalid_factorial_identifier`; `apps/web/src/components/SourceCreateForm.tsx` (`configFields.factorial`, `typeLabels.factorial`) e `apps/web/src/features/sources/api.ts` (`sourceTypes`) |
| Pelo menos uma empresa real do catálogo homologada e coletando | **Pendente**, ver "Pendências" |

## Pendências

- Homologação de uma empresa real (critério 4) não foi feita: exige a fila de homologação
  (F20-25) rodando contra a stack real e uma chamada de rede de verdade a um board real, o
  que este worker não faz fora do CI por instrução explícita do card ("nunca fazer chamada
  real a boards... no CI"; a máquina de referência é medida fora do CI). Candidatos do
  catálogo já citados em `docs/pesquisas/auditoria-186-empresas.md`: Agentero
  (`agentero.factorialhr.com`, `company_identifier=agentero`) e a própria Factorial
  (`careers.factorialhr.com`, `company_identifier=careers`). Próximo passo: rodar a fila de
  homologação apontando `company_identifier` para um desses slugs e colar o resultado real
  no PR.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
