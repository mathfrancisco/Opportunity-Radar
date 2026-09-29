# Coletor "Who is hiring?" (F20-55) — execução real, 2026-09-29

Execução real (não fabricada) na pilha isolada `f20manual` (`docker exec f20manual-api-1`,
API em `127.0.0.1:8001`). A pilha real `opportunity-radar` não foi tocada. Termos e
robots: [`docs/pesquisas/termos-hn-who-is-hiring.md`](../../pesquisas/termos-hn-who-is-hiring.md)
(veredito: viável, com risco residual registrado).

## Como foi executado

O container `f20manual-api-1` tem o pacote instalado em `site-packages` (imagem sem o
código deste card). O código da branch foi copiado para `/tmp/hnsrc` dentro do container e
usado via `PYTHONPATH` — o pacote instalado não foi alterado. Uma `SourceDefinition`
`hacker_news` ("Hacker News - Who is hiring? (F20-55)", `evidence_status=confirmed`,
termos revisados, `collector_local_tested=true`, `minimum_interval_seconds=0.3`) foi criada
por `AcquisitionService.create_source`, executada por `AcquisitionService.execute` e as
vagas normalizadas por `OpportunityService.normalize_run`. Ao final a fonte foi deixada
**desabilitada** (o worker da `f20manual` roda o código antigo, que não conhece o
`source_type`; habilitar exige a imagem nova).

Thread lido: "Ask HN: Who is hiring? (September 2026)", item `49522897`, localizado via
Algolia (1 requisição) e lido via Firebase (1 requisição da story + 1 por comentário
top-level = 301; total 302 requisições HTTP por execução, 0 retentativas, 0 eventos de
rate limit). A story anunciava 300 comentários top-level.

## Duas execuções (a primeira expôs uma falha do parser)

| Execução | Parser | Status | Vistos | Persistidos | Pulados | Inválidos |
| --- | --- | --- | --- | --- | --- | --- |
| `eae7db15-bb97-4a51-b0cb-2f773c5306a2` | v1 (exigia papel no cabeçalho) | PARTIAL | 255 | 166 | 0 | 89 (35%) |
| `4aeb1ae4-6a4f-405b-add7-73f72e728a48` | v1 final (empresa sem papel vira evidência sem título) | PARTIAL | 255 | 77 | 159 | 19 (7%) |

A primeira execução mostrou 89 comentários "sem empresa ou papel identificável"; a
inspeção dos cabeçalhos reais (ver abaixo) mostrou que a maioria tinha empresa clara mas o
papel fora do cabeçalho (`Middesk | Full-time | NYC / SF | Hybrid`). O parser passou a
manter empresa/local/texto como evidência com `title=None` (sem inventar título; o
normalizador rejeita item sem título, resultado `FAILED` = pendência) e a limpar URL e
parênteses no nome da empresa. A segunda execução é a de referência; as 166 já
persistidas foram reconhecidas (159 puladas por hash idêntico).

Nenhuma das duas terminou `SUCCEEDED`: `PARTIAL` é o resultado correto enquanto houver
comentário sem empresa identificável (critério de aceite do card: pendência, não sucesso).
Os 45 comentários restantes de 300 são deletados/mortos e nunca contam como vistos.
`complete=false` nestas duas execuções porque o anúncio de itens ainda era a contagem
bruta de `kids` (300); o coletor foi ajustado depois para anunciar só comentários vivos
(teste `items_announced == 4`), sem nova execução real.

## Resultado do acervo (243 itens brutos, `source_definition` acima)

| Métrica | Valor |
| --- | --- |
| Itens brutos persistidos | 243 |
| Normalização `SUCCEEDED` | 175 (viram oportunidade) |
| Normalização `FAILED` | 61 (empresa identificada, cabeçalho sem papel: sem título, pendência) |
| Normalização `REVIEW_REQUIRED` | 7 |
| Comentários sem empresa identificável (inválidos, nunca persistidos) | 19 de 255 (7,5%) |
| Senioridade das 175 oportunidades | UNKNOWN 124, SENIOR 30, STAFF 10, LEAD 4, JUNIOR 2, INTERN 2, MANAGER 2, DIRECTOR 1 |
| **JUNIOR + INTERN** | **4 de 175 = 2,3%** (1,6% dos 243 itens brutos) |

Títulos JUNIOR/INTERN: "Frontend Engineer (Junior)", "Software Engineering Intern",
"Full-time / internship", "Robotics Software Engineer (Early Career + Experienced)". A
maioria das vagas fica `UNKNOWN` porque o texto livre não declara senioridade; a fonte
não deve ser esperada como fonte de estágio/júnior.

## Propostas de board ATS geradas (dado real)

Três propostas inertes (`enabled=false`, `evidence_status=ats_identified`) com
`discovery_via="hn_who_is_hiring"`, todas de empresas já no catálogo:

| Proposta | ATS | Evidência (URL no comentário) |
| --- | --- | --- |
| Proposed Wikimedia Foundation greenhouse | greenhouse | `job-boards.greenhouse.io/wikimedia/jobs/8140060` |
| Proposed DeepL ashby | ashby | `jobs.ashbyhq.com/DeepL` |
| Proposed LiveKit ashby | ashby | `jobs.ashbyhq.com/livekit/463e2769-...` |

Não foram ativadas nem sondadas (fila do F20-46 decide).

## Comentários não parseados (amostra dos 19, texto real)

`Location: London, UK`; `Software Engineer — Remote (US Only)` (sem empresa);
`Senior Python Backend Engineer | REMOTE (EMEA/APAC)` (sem empresa);
`Hiring: Senior Software Engineers (LATAM/US/Canada-based)`; `We're hiring at Langfuse — ...`
(prosa); `DuckDuckGo - all roles fully remote...` (sem `|`); `Please normalize 4DWW - ...`
(off-topic). Todos ficam contados em `items_invalid`, nenhum vira vaga.

## Limitações conhecidas

- 61 de 236 comentários parseados não trazem papel no cabeçalho; ficam como evidência sem
  título (papel só no corpo do texto — não extraído para não adivinhar).
- Proposta de board ATS (`discovery_via="hn_who_is_hiring"`) só ocorre quando a empresa do
  comentário já existe no catálogo por nome canônico exato (regra do F20-46).
- Agendamento por palavra-chave (`keyword_search`) funciona quando `keywords` é passado ao
  coletor (probe/`make collect`); o worker não rotaciona palavras-chave para esta fonte.
