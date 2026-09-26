# CARD F20-27 — Descoberta de ATS

- **Status:** WIP parcial — snapshot integrado; critérios de aceite pendentes.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-09](../../38-roadmap-ia-e-busca/fase-17/f17-09-descoberta-de-ats.md)

## Ajustes da Fase 20

- Sem mudança de escopo. O relatório deste card define a ordem de F20-28 a F20-32.

## Resultado

Para as empresas que só têm página de carreiras, o radar descobre o ATS por trás dela
quando a página o revela, e registra a descoberta como evidência para virar proposta de
fonte.

## Contexto

115 empresas do catálogo têm página de carreiras confirmada e nenhum ATS conhecido; outras
52 estão em backlog. Muitas dessas páginas são uma casca em volta de um board Ashby,
Greenhouse, Lever, Gupy ou Teamtailor, embutido por link, iframe ou script.

## Escopo

- Comando `make discover-ats` (e job opcional de baixa frequência, desligado por padrão):
  para cada empresa com página de carreiras e sem ATS, faz **uma** requisição GET à página
  registrada.
- **Assinaturas** por ATS no HTML (links, `iframe src`, `script src`): `jobs.ashbyhq.com`,
  `boards.greenhouse.io`/`job-boards.greenhouse.io`, `jobs.lever.co`, `*.gupy.io`,
  `*.teamtailor.com`, `apply.workable.com`, `*.myworkdayjobs.com`, `*.factorialhr.com`.
- **Resultado** vira `CompanySource` com `verification_method = "discovery"`,
  `verification_status = "ats_identified"`, a URL encontrada e o trecho do HTML como
  evidência — o mesmo formato da F14-05, com revisão registrada.
- **Tentativas** em `company_radar.discovery_attempt` (empresa, URL, status HTTP, ATS
  encontrado, data), para não repetir antes do intervalo configurado (padrão 30 dias).
- **Boas maneiras:** respeita `robots.txt` (`urllib.robotparser`), `User-Agent` que
  identifica o radar, uma requisição por segundo no total, timeout curto, nunca segue
  links para dentro do site.
- Relatório: quantas páginas revelaram ATS, por tipo — é o que reordena o F20-28 a F20-32 (antigo F17-10).

## Fora de escopo

- Navegador headless para páginas renderizadas por JavaScript (SPEC §16).
- Habilitar fonte: a descoberta produz evidência; a proposta passa pela sonda e pela
  homologação.

## Continuidade

Este card mantém a descoberta de ATS em uma página. F20-36 (antigo F18-02) amplia para links e
sitemaps com limites, aproveitando as mesmas assinaturas e propostas. Resultado
negativo não significa empresa sem vagas; guardar motivo e próxima pesquisa.

## Notas de implementação

- A descoberta é pesquisa, não coleta: não cria `SourceRun` nem `RawItem`.
- Página que redireciona para domínio de ATS também conta: registrar a URL final.
- A chave do board é extraída pelos mesmos padrões do F20-03 (antigo F17-04).

## Critérios de aceite

- [ ] Uma execução percorre as empresas elegíveis com uma requisição cada, respeitando
      `robots.txt` e o ritmo.
- [ ] ATS encontrado vira `CompanySource` com evidência e método `discovery`.
- [ ] Tentativas ficam registradas e não se repetem antes do intervalo.
- [ ] O relatório por tipo de ATS está em `docs/pesquisas/`.

## Verificação

- **CI:** testes do detector de assinaturas com páginas de exemplo de cada ATS (HTML fixo)
  e páginas sem ATS; teste do respeito a `robots.txt` com servidor falso; teste do
  intervalo entre tentativas.
- **Máquina de referência:** execução real sobre o catálogo, com o relatório anexado.

## Arquivos prováveis

- `src/opportunity_radar/companies/discovery.py` (novo)
- `scripts/discover_ats.py` (novo), `Makefile`
- `migrations/versions/*_discovery_attempt.py`
- `tests/backend/companies/`

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `src/opportunity_radar/companies/discovery.py` | Assinaturas por ATS no HTML, elegibilidade (empresa com `CompanySource` `source_type="careers"`/`verification_status="careers_confirmed"` e sem ATS — mesmo padrão usado por `scripts/import_research_catalog.py:263,325-326,385`), respeito a `robots.txt`, e o registro do resultado. |
| Alterar | `src/opportunity_radar/companies/models.py` | `CompanySource` (linha 79-125) e `CompanySourceRevision` (linha 128-156) já guardam evidência e histórico; adicionar `DiscoveryAttemptModel` (`company_radar.discovery_attempt`) no mesmo arquivo. |
| Criar | `migrations/versions/20260926_0033_discovery_attempt.py` | Cria `company_radar.discovery_attempt`. Número indicativo: latest hoje é `20260925_0029`; F20-12/19/23 reservam 0030-0032 — usar 0033 ou o que `alembic heads` indicar. |
| Criar | `scripts/discover_ats.py` | Script chamado por `make discover-ats`, no formato de `scripts/discover_sources.py` (lê `DATABASE_URL`, abre uma `Session`, imprime um relatório JSON). |
| Alterar | `Makefile` | Hoje sem alvo `discover-ats`; adicionar um alvo no formato de `discover-sources`/`enable-sources` (linhas 56-61), rodando dentro do container via `docker compose run`. |
| Alterar | `docs/pesquisas/` | Novo relatório `docs/pesquisas/descoberta-ats-<data>.md` com a contagem por tipo de ATS (entregável do card, não CI). |

Este card **não** toca `src/opportunity_radar/companies/registration.py`: `add_source`/`_source_values` (linhas 224-258, 362-399) só aceita os ATS já suportados (`SUPPORTED_ATS = ("ashby", "lever", "greenhouse")`, linha 48) e exige uma chave validada por collector existente. Um ATS descoberto sem collector (Workday, Teamtailor, Workable, Factorial, Gupy) ainda não tem validador, então `discovery.py` grava o `CompanySource` diretamente — como o importador já faz em `import_research_catalog.py` — sem passar por `_source_values`.

## Interfaces

```python
# src/opportunity_radar/companies/discovery.py
ATS_SIGNATURES: dict[str, tuple[str, ...]] = {
    "ashby": ("jobs.ashbyhq.com",),
    "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io"),
    "lever": ("jobs.lever.co",),
    "gupy": (".gupy.io",),
    "teamtailor": (".teamtailor.com",),
    "workable": ("apply.workable.com",),
    "workday": (".myworkdayjobs.com",),
    "factorial": (".factorialhr.com",),
}


@dataclass(frozen=True, slots=True)
class DiscoveryOutcome:
    company_id: UUID
    checked_url: str
    final_url: str
    http_status: int | None
    ats_found: str | None
    evidence_snippet: str | None


def eligible_companies(session: Session) -> list[Company]:
    """Empresas com página de carreiras confirmada e nenhum ATS conhecido, que não
    foram verificadas dentro do intervalo configurado (padrão 30 dias)."""


def detect_ats(html: str) -> str | None:
    """Casa `ATS_SIGNATURES` contra links, `iframe src` e `script src`."""


async def discover_one(
    company: Company,
    *,
    client: httpx.AsyncClient,
    robots_checker: Callable[[str], bool],
    user_agent: str,
) -> DiscoveryOutcome:
    """Uma requisição GET; nunca segue links para dentro do site."""


def record_discovery_attempt(
    session: Session, outcome: DiscoveryOutcome
) -> DiscoveryAttemptModel: ...


def record_ats_identified(
    session: Session, outcome: DiscoveryOutcome
) -> CompanySource:
    """CompanySource com verification_method='discovery',
    verification_status='ats_identified', endpoint=final_url, evidence_note=snippet."""


# src/opportunity_radar/companies/models.py
class DiscoveryAttemptModel(Base):
    __tablename__ = "discovery_attempt"
    __table_args__ = ({"schema": SCHEMA},)  # SCHEMA = "company_radar"

    id: Mapped[uuid.UUID]
    company_id: Mapped[uuid.UUID]  # FK company.id
    checked_url: Mapped[str]
    http_status: Mapped[int | None]
    ats_found: Mapped[str | None]
    attempted_at: Mapped[datetime]
```

## Passos

1. Escrever os testes de `detect_ats` com HTML fixo de cada assinatura e páginas sem ATS, antes do código.
2. Criar a migração `migrations/versions/20260926_0033_discovery_attempt.py` com `company_radar.discovery_attempt` (empresa, URL, status HTTP, ATS encontrado, data).
3. Adicionar `DiscoveryAttemptModel` a `src/opportunity_radar/companies/models.py`.
4. Criar `src/opportunity_radar/companies/discovery.py`: `ATS_SIGNATURES`, `detect_ats` (busca em links, `iframe src`, `script src`), `eligible_companies` (join `CompanySource` `source_type="careers"` + `verification_status="careers_confirmed"` sem nenhum `CompanySource` de ATS, e sem tentativa dentro dos últimos 30 dias em `discovery_attempt`).
5. Implementar `discover_one` com `urllib.robotparser` (uma checagem de `robots.txt` por host, cacheada na execução), `User-Agent` identificando o radar, uma requisição por segundo no total (mesmo espírito do `minimum_interval_seconds` de `CollectionNetworkPolicy`, `acquisition/domain.py:146`), timeout curto e `follow_redirects=True` registrando a URL final.
6. Implementar `record_discovery_attempt` (sempre grava) e `record_ats_identified` (só quando `ats_found` não é `None`), este último criando `CompanySource` diretamente (sem passar por `registration.add_source`/`_source_values`, que exigem um ATS já suportado).
7. Criar `scripts/discover_ats.py` no formato de `scripts/discover_sources.py`: abre sessão a partir de `DATABASE_URL`, chama `eligible_companies`, roda `discover_one` para cada uma, imprime o relatório JSON por tipo de ATS.
8. Adicionar o alvo `discover-ats` ao `Makefile`, no formato de `discover-sources`/`enable-sources` (linhas 56-61), desligado por padrão (sem agendamento automático).
9. Escrever o teste de respeito a `robots.txt` com servidor falso (nega e permite) e o teste do intervalo entre tentativas (30 dias).
10. Rodar a execução real sobre o catálogo (fora do CI) e escrever `docs/pesquisas/descoberta-ats-<data>.md` com a contagem por tipo de ATS — é o insumo que ordena F20-28 a F20-32.

## Testes a escrever

- `tests/backend/companies/test_discovery.py::test_detect_ats_matches_each_signature`
- `tests/backend/companies/test_discovery.py::test_detect_ats_returns_none_without_signature`
- `tests/backend/companies/test_discovery.py::test_eligible_companies_excludes_known_ats`
- `tests/backend/companies/test_discovery.py::test_eligible_companies_excludes_recent_attempt`
- `tests/backend/companies/test_discovery.py::test_discover_one_respects_robots_txt`
- `tests/backend/companies/test_discovery.py::test_discover_one_records_final_url_on_redirect`
- `tests/backend/companies/test_discovery.py::test_record_ats_identified_creates_company_source_with_discovery_method`
- `tests/backend/companies/test_discovery.py::test_attempt_not_repeated_before_interval`

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
docker compose -p f20-27 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/companies/test_discovery.py
docker compose -p f20-27 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-27 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
