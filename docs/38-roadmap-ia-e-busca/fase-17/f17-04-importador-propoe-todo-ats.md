# CARD F17-04 — Importador propõe todo ATS identificado, com chave extraída do link

- **Status:** Backlog
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** Nenhum (habilitação em massa espera F17-02 e F17-07)
- **Bloqueia:** F17-05, F17-09
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §4

## Resultado

Toda empresa do catálogo com Ashby, Greenhouse ou Lever identificado vira uma proposta de
fonte — inerte, à espera da sonda e da homologação —, e as que não têm chave resolvível
viram pendência de pesquisa com o motivo.

## Contexto

O catálogo tem 55 empresas com ATS identificado (Ashby 29, Greenhouse 9, Lever 5, e 12 em
ATS sem coletor), mas o importador só materializa fonte para "API JSON confirmada" de
qualquer ATS ou "ATS identificado" de Greenhouse com chave
(`scripts/import_research_catalog.py:65-86`). Resultado: 6 fontes + Remotive. As 25
empresas Ashby com ATS identificado ficam sem fonte; 8 delas têm até o link do board na
pesquisa.

## Escopo

- O filtro de `register_researched_collectors` passa a aceitar todo `CompanySource` de tipo
  `ashby`, `greenhouse` ou `lever` com status `ats_identified` ou `api_json_confirmed` e
  chave presente.
- **Extração da chave** quando a pesquisa tem o link do board e não a chave, por padrão
  explícito por ATS:
  - Ashby: `https://jobs.ashbyhq.com/<chave>` (e `/<chave>/…`);
  - Greenhouse: `https://boards.greenhouse.io/<chave>`, `https://job-boards.greenhouse.io/<chave>`;
  - Lever: `https://jobs.lever.co/<chave>`, `https://jobs.eu.lever.co/<chave>` (com
    `api_region = eu`).
  A chave extraída passa pelo validador do próprio coletor antes de ser gravada, com
  `verification_method = "research_link"` e o link como evidência.
- Link fora do padrão, ou ATS identificado sem link: `CompanyImportIssue` com código
  `ats_key_unresolved` e o motivo, visível no relatório do import.
- As propostas nascem como hoje: desabilitadas, `evidence_status = ats_identified`, com
  a evidência da pesquisa.
- **E2E:** as contagens fixas do passo "Import and expose the researched company catalog"
  (`sources total == 7`) e dos passos seguintes (`sources_total == 8`,
  `len(day['sources']) == 8`, `len(idle) == 7`) são recalculadas a partir do novo
  resultado do import e documentadas no PR.

## Fora de escopo

- Sondar ou habilitar as propostas (F17-05, com a sonda do F14-06).
- Coletores para Workday, Teamtailor, Workable, Factorial e Gupy (F17-10).

## Notas de implementação

- O import continua idempotente: rodar de novo não duplica proposta (a chave
  `company_source_id + source_type` já protege) nem pendência.
- A F14-05 proíbe inferir chave de URL colada **na tela** pelo operador; aqui a origem é a
  pesquisa versionada no repositório, e a chave extraída ainda passa pela sonda antes de
  qualquer coleta.
- Contar, no próprio PR, quantas propostas o import gera com a pesquisa atual — esse é o
  número que atualiza o E2E e a meta da SPEC §3.

## Critérios de aceite

- [ ] Toda empresa Ashby, Greenhouse ou Lever com chave resolvível tem proposta inerte.
- [ ] Chave extraída de link é validada pelo coletor e guarda o link como evidência.
- [ ] Empresas sem chave resolvível aparecem como pendência com motivo.
- [ ] O import continua idempotente.
- [ ] O E2E passa com as contagens novas, justificadas no PR.

## Verificação

- **CI:** testes do extrator de chave com links reais de cada ATS e links inválidos; teste
  do filtro do import com um catálogo de exemplo; E2E com as contagens atualizadas.

## Arquivos prováveis

- `scripts/import_research_catalog.py`
- `src/opportunity_radar/acquisition/proposals.py` (padrões por ATS junto de
  `IDENTIFIER_KEYS`)
- `tests/backend/test_research_catalog_import.py`
- `.github/workflows/pipeline.yml`
