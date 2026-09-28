# CARD F20-60 — Importar empresas do mapa de carreira e ativar fontes já identificadas

- **Status:** Backlog.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-03, F20-27
- **Origem:** auditoria do mapa de carreira internacional do Notion contra o catálogo,
  registrada em
  [`docs/44-roadmap-fase-20/evidencias/mapa-carreira-vs-catalogo-2026-09-28.md`](../evidencias/mapa-carreira-vs-catalogo-2026-09-28.md)
  (2026-09-28). Nenhuma empresa foi inserida e nenhuma fonte foi habilitada durante a
  auditoria; este card materializa o que ela encontrou.

## Contexto

O usuário mantém um mapa pessoal de 100 empresas-alvo no Notion (produto estrangeiro,
consultorias/redes e origem brasileira). Comparado com `company_radar.company` +
`acquisition.source_definition` do banco do projeto (223 empresas), 51 dessas 100 não
estão no catálogo e 5 estão no catálogo com ATS identificado mas a fonte desabilitada.
A auditoria fez sondagens reais (uma requisição por candidato, endpoint público do
próprio ATS, nunca o site institucional) para 5 das 51 ausentes e confirmou boards
ativos e populados.

## Escopo

1. **Ativar as 5 fontes já identificadas e desabilitadas** (classe c da auditoria),
   após revisão de termos de cada uma: Grafana Labs (Greenhouse), TestGorilla (Ashby),
   Customer.io (Greenhouse), NTT DATA (Workday), Accenture (Workday).
2. **Importar as 5 empresas ausentes com ATS confirmado por sondagem real** nesta
   auditoria, usando o fluxo de `scripts/import_research_catalog.py` /
   `CompanyService.reconcile` (nunca inserção manual direta):
   - Loadsmart — Lever (`api.lever.co/v0/postings/loadsmart`)
   - Zup — Greenhouse (`boards-api.greenhouse.io/v1/boards/zupinnovation`)
   - EBANX — Greenhouse (`boards-api.greenhouse.io/v1/boards/ebanx`)
   - Devsu — Workable (`apply.workable.com/api/v1/widget/accounts/devsu`)
   - Azumo — Workable (`apply.workable.com/api/v1/widget/accounts/azumo`)
3. **Revisão de termos** de cada uma das 10 fontes acima antes de qualquer `enabled=true`
   — mesma régua do F20-32/F20-51/F20-52: um Termos de Uso que proíba coleta automatizada
   fecha aquela fonte individualmente, sem bloquear as demais.
4. Registrar evidência real de coleta (pelo menos uma vaga por fonte habilitada) após
   a ativação, como já feito nos cards de coletor do Bloco C.

## Fora de escopo

- As ~45 empresas da classe (d) sem ATS identificável a partir do texto do Notion —
  precisam de uma rodada de pesquisa (Tavily ou manual) antes de qualquer sondagem;
  não é o mesmo trabalho barato deste card.
- Red Hat (Workday, tenant não pesquisado) e CESAR (Breezy HR, sem coletor no
  projeto) — ver "Não fazer".
- Minsait, DB (antiga DBServer) e FCamara — ATS real é Gupy, fechado pelo F20-32.
- Qualquer mudança em `probe_direct_ats`, coletores existentes ou no schema do
  catálogo; este card só importa/ativa dentro do que já existe.

## Critérios de aceite

- [ ] As 5 fontes da classe (c) revisadas por termos; as que passarem, com
      `enabled=true` e pelo menos uma coleta real registrada.
- [ ] As 5 empresas com ATS confirmado por sondagem (Loadsmart, Zup, EBANX, Devsu,
      Azumo) importadas via `CompanyService.reconcile` (não inserção manual), com
      `company_source` e, após revisão de termos, `source_definition` habilitada.
- [ ] Para cada fonte habilitada neste card, pelo menos um item real coletado e
      visível na API/Overview.
- [ ] Nenhuma fonte Gupy tocada; Red Hat e CESAR permanecem fora deste card (ou
      viram sub-cards próprios, se alguém pesquisar o tenant/endpoint deles depois).

## Não fazer

- Não sondar, coletar ou ativar nenhuma fonte Gupy (Minsait, DB, FCamara) — decisão
  já tomada no F20-32.
- Não adivinhar tenant/pod/site do Workday da Red Hat sem pesquisa prévia registrada.
- Não inserir empresa ou habilitar fonte fora do fluxo de reconciliação existente
  (`CompanyService`/`import_research_catalog.py`).
- Não copiar dado pessoal do mapa de carreira do Notion (notas de candidatura,
  mensagens, currículo) para o repositório — só nome, URL e categoria da empresa.

## Verificação

- **CI:** suíte de testes de `companies/` e `acquisition/` relevante à importação e
  aos coletores tocados (Lever, Greenhouse, Workable).
- **Máquina de referência:** pelo menos uma coleta real por fonte habilitada,
  registrada em `docs/44-roadmap-fase-20/evidencias/`.

## Pronto quando

As 5 fontes desabilitadas e as 5 empresas com ATS confirmado por sondagem estiverem
avaliadas por termos, e as aprovadas estiverem habilitadas e coletando de verdade —
ou, para qualquer uma que falhar a revisão de termos, fechadas individualmente com a
mesma evidência exigida pelo F20-32/F20-51/F20-52.
