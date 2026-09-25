# CARD F20-36 — Descoberta limitada de sites e sitemaps

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** D — Varredura produtiva
- **Depende de:** F20-27, F20-35
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-02](../../40-roadmap-varredura-produtiva/fase-18/f18-02-descoberta-limitada-de-sites.md); [SPEC 39](../../39-spec-varredura-produtiva.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Dependências antigas de F17 foram fechadas por F20-01 a F20-03.

## Resultado

Empresas cuja página não revela ATS ganham pesquisa limitada de links/sitemaps, com proposta rastreável e custo controlado.

## Escopo

- Reutilizar assinaturas/propostas de F20-27 (antigo F17-09). Semear pela página de carreiras cadastrada e seguir apenas links pertinentes dentro da allowlist.
- Aplicar os limites de profundidade, respostas, tamanho descomprimido e URLs da SPEC; registrar parada por limite, erro, política ou site dinâmico.
- Deduplicar URL normalizada sem remover query identificadora; persistir origem, evidência e data da tentativa.
- Robots/termos, agente identificável, validação de DNS/destino e de cada redirect. Recusar rede privada e XML com entidades externas.
- Resultado negativo tem próxima revisão semanal/backoff. ATS externo vira proposta inerte; nenhuma navegação livre ou habilitação por IA.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [ ] Loops, sitemaps grandes e múltiplos redirects param dentro do orçamento.
- [ ] Nenhum destino privado ou fora da allowlist é acessado.
- [ ] Limite/erro não significa empresa sem vagas.
- [ ] Proposta existente é reutilizada com histórico da descoberta.

## Verificação

- **CI:** Servidor falso com sitemap/index/loop, URL com query, redirect privado, robots indisponível, XML inválido e orçamento esgotado.
- **Máquina de referência:** Medir empresas novas com endpoint encontrado e requisições por descoberta numa coorte fixa.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`acquisition/probing.py`, `proposals.py`, novo módulo de descoberta limitada, scripts/discover_sources.py, fixtures HTTP.

## Contexto no código

Nada disto existe ainda na árvore atual — confirmado por busca (`grep -rl "robots\|robotparser"` e `grep -rl "ipaddress\|is_private"` em `src/opportunity_radar/` não retornam nada): não há guarda de SSRF (validação de IP privado/loopback/link-local), não há leitor de `robots.txt`, não há parser de sitemap e não há orçamento de profundidade/URLs. O card parte do zero sobre os seguintes blocos existentes:

- `acquisition/proposals.py` (`proposal_for`, `is_inert`, `is_outdated`, `follow_correction`) já sabe transformar um `CompanySource` corrigido numa `SourceDefinition` inerte — a descoberta limitada deve produzir o mesmo tipo de proposta, não uma tabela paralela.
- `acquisition/domain.py:140-176` (`CollectionNetworkPolicy`) já valida limites de retry/intervalo para os coletores; a descoberta limitada precisa de uma política equivalente, mas com dimensões diferentes (profundidade, nº de sitemaps, bytes descomprimidos, nº de URLs) — não reaproveitar `CollectionNetworkPolicy` diretamente, ela não tem esses campos.
- `acquisition/domain.py:13-28` (`AcquisitionErrorCode`) não tem um código para "parada por limite/política/site dinâmico"; a descoberta limitada precisa dos seus próprios motivos de parada, distintos dos códigos de coleta.
- `companies/models.py:81-125` (`CompanySource`) já tem `verification_method`, `verification_status`, `evidence_note`, `last_verified_at` e histórico de revisão (`CompanySourceRevision`) — é o destino de qualquer endpoint encontrado, igual ao F20-27.
- F20-27 (Bloco C, ainda não implementado) cria `companies/discovery.py` com o detector de assinaturas por ATS (`jobs.ashbyhq.com`, `boards.greenhouse.io`, `jobs.lever.co` etc.) e a tabela `company_radar.discovery_attempt`; este card **reaproveita** esse detector e essa tabela para o rastreamento de mais de uma página — se F20-27 ainda não tiver aterrado, tratar `companies/discovery.py` e a migração de `discovery_attempt` como pré-requisito e registrar a ordem no PR.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `src/opportunity_radar/acquisition/limited_discovery.py` | política de limites, leitura de `robots.txt`, parser de sitemap, guarda de SSRF/allowlist |
| Alterar | `src/opportunity_radar/acquisition/proposals.py` | aceitar propostas originadas da descoberta limitada (mesmo formato do F20-27) |
| Alterar | `src/opportunity_radar/acquisition/probing.py` | nenhuma mudança de contrato esperada; confirmar que `PROBE_TYPES` não precisa crescer aqui |
| Criar | `scripts/discover_sources.py` | comando `make discover-sites` (job opcional, desligado por padrão) |
| Alterar | `Makefile` | novo target `discover-sites` |
| Criar | `tests/e2e/fake_discovery_site.py` | servidor falso com sitemap/index/loop/redirect privado/robots indisponível/XML inválido |
| Criar | `tests/backend/acquisition/test_limited_discovery.py` | testes unitários dos limites e da guarda de rede |

Nenhuma migração de tabela nova é esperada aqui: a persistência de tentativa reaproveita
`company_radar.discovery_attempt` do F20-27. Se a descoberta multi-página precisar de uma
coluna adicional (por exemplo, profundidade alcançada), registrar a necessidade como
`migrations/versions/20260926_0040_<slug>.py` (numeração indicativa: a cabeça atual é
`20260925_0029`; 0030-0032 são reservados a outros cards do Bloco B e o Bloco C pode usar
0033-0039).

## Interfaces

```python
# src/opportunity_radar/acquisition/limited_discovery.py
from dataclasses import dataclass, field
from enum import StrEnum


class DiscoveryStopReason(StrEnum):
    EXHAUSTED = "EXHAUSTED"        # fila de candidatos esgotada dentro do orçamento
    LIMIT_REACHED = "LIMIT_REACHED"  # profundidade, respostas, bytes ou URLs
    POLICY = "POLICY"              # robots.txt, allowlist ou termos
    ERROR = "ERROR"
    DYNAMIC_SITE = "DYNAMIC_SITE"   # indício de renderização via JS, sem headless
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class DiscoveryLimits:
    """Limites conservadores do projeto (SPEC 39 §5), não do protocolo."""

    max_depth: int = 2
    max_html_responses: int = 20
    max_sitemap_files: int = 5
    max_html_bytes: int = 2 * 1024 * 1024
    max_sitemap_decompressed_bytes: int = 5 * 1024 * 1024
    max_urls_examined: int = 5_000
    concurrency_per_host: int = 1


@dataclass(frozen=True, slots=True)
class DiscoveredEndpoint:
    company_id: "UUID"
    seed_url: str
    discovered_url: str
    method: str  # "sitemap" | "html_link" | "iframe" | "script"
    fetched_at: "datetime"
    evidence_excerpt: str
    confidence_reason: str


@dataclass(frozen=True, slots=True)
class DiscoveryOutcome:
    stop_reason: DiscoveryStopReason
    endpoints: tuple[DiscoveredEndpoint, ...]
    urls_examined: int
    http_requests: int
    next_attempt_at: "datetime | None"  # backoff/semanal (SPEC 39 §5)


def is_public_destination(host: str, resolved_ips: tuple[str, ...]) -> bool:
    """Recusa rede privada/loopback/link-local em cada conexão e redirect (SPEC 39 §5)."""


def normalize_discovery_url(url: str) -> str:
    """Normaliza sem remover query que identifica a vaga (SPEC 39 §5)."""


async def run_limited_discovery(
    seed_url: str, *, company_id: "UUID", limits: DiscoveryLimits,
    allowlist: frozenset[str],
) -> DiscoveryOutcome: ...
```

## Passos

1. Escrever `tests/e2e/fake_discovery_site.py` com rotas para: sitemap index normal,
   sitemap com loop (referencia a si mesmo), redirect para IP privado, `robots.txt`
   indisponível (500), XML com entidade externa e página com evidência de renderização
   dinâmica (ex.: corpo vazio + script bundle).
2. Escrever `tests/backend/acquisition/test_limited_discovery.py` cobrindo os quatro
   critérios de aceite antes de qualquer código de produção.
3. Implementar `DiscoveryLimits`, `DiscoveryStopReason` e `normalize_discovery_url`
   (URL canônica preservando query que identifica a vaga, igual ao critério de dedupe da
   SPEC §5) em `acquisition/limited_discovery.py`.
4. Implementar `is_public_destination` usando `ipaddress` da stdlib, chamada antes de
   cada conexão e antes de seguir cada redirect — nenhum destino privado/loopback/
   link-local, nenhuma credencial em URL, nenhum esquema fora de HTTP(S).
5. Implementar leitura de `robots.txt` com `urllib.robotparser`, identificando o agente
   do radar (RFC 9309); falha temporária em obter a política suspende a navegação até
   resolver, com o motivo exposto.
6. Implementar o parser de sitemap com limite de descompressão/profundidade e sem
   resolução de entidades externas (`defusedxml` ou `xml.etree` com resolver
   desabilitado — se precisar de dependência nova, registrar o motivo no PR).
7. Implementar a busca por links pertinentes a partir da `careers_page` cadastrada,
   respeitando `max_depth`/`max_html_responses`/`concurrency_per_host`.
8. Reaproveitar o detector de assinaturas do F20-27 (`companies/discovery.py`) para
   decidir se uma página encontrada revela um ATS; se F20-27 não tiver aterrado ainda,
   implementar aqui um detector equivalente e registrar a duplicação temporária no PR.
9. Ligar o resultado a `acquisition/proposals.py`: endpoint encontrado gera/atualiza
   `CompanySource` com `verification_method="discovery"` e evidência; a proposta segue
   inerte até a homologação humana (nenhuma navegação livre, nenhuma habilitação por IA).
10. Persistir cada tentativa em `company_radar.discovery_attempt` (empresa, URL, status,
    ATS encontrado, motivo de parada, próxima tentativa) para não repetir antes do
    intervalo configurado.
11. Criar `scripts/discover_sources.py` e o target `make discover-sites`, desligado por
    padrão (job opcional de baixa frequência).
12. Rodar o comando de verificação e confirmar os quatro critérios de aceite.

## Testes a escrever

- `tests/backend/acquisition/test_limited_discovery.py::test_sitemap_loop_stops_within_budget` — sitemap que referencia a si mesmo para em `LIMIT_REACHED`, não em erro não tratado.
- `tests/backend/acquisition/test_limited_discovery.py::test_redirect_to_private_ip_is_refused` — redirect para `127.0.0.1`/`169.254.x.x` interrompe a descoberta com `DiscoveryStopReason.POLICY` e nenhuma requisição extra.
- `tests/backend/acquisition/test_limited_discovery.py::test_url_with_identifying_query_is_not_deduplicated_away` — duas URLs iguais exceto pela query de identificação da vaga não colapsam em uma.
- `tests/backend/acquisition/test_limited_discovery.py::test_robots_unavailable_suspends_navigation` — `robots.txt` retornando 500 impede novas requisições até resolver, com motivo visível.
- `tests/backend/acquisition/test_limited_discovery.py::test_limit_or_error_does_not_mean_no_jobs` — `stop_reason in {LIMIT_REACHED, ERROR}` não seta nenhuma flag de "empresa sem vagas" no `CompanySource`.
- `tests/backend/acquisition/test_limited_discovery.py::test_existing_proposal_is_reused_with_discovery_history` — segunda tentativa sobre o mesmo `CompanySource` atualiza o histórico em vez de criar uma proposta duplicada.

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
docker compose -p f20-36 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/acquisition/test_limited_discovery.py
docker compose -p f20-36 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-36 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
