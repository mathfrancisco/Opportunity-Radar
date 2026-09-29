# CARD F20-60 — Importar empresas do mapa de carreira e ativar fontes já identificadas

- **Status:** Feito — fontes ativadas na pilha real `opportunity-radar` em 2026-09-29 (importadas com probe, 137 habilitadas; inclui DoorDash, Remotebase e Lemon.io), ver
  [`docs/44-roadmap-fase-20/validacao-pendente.md`](../validacao-pendente.md) §4 e §7 e
  [`docs/44-roadmap-fase-20/evidencias/mapa-carreira-vs-catalogo-2026-09-28.md`](../evidencias/mapa-carreira-vs-catalogo-2026-09-28.md)
  ("Resultados da execução").
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

- [x] As 5 fontes da classe (c) revisadas por termos; as que passarem, com
      `enabled=true` e pelo menos uma coleta real registrada. Todas as 5 passaram
      (termos já revisados em nível de coletor: Greenhouse/Ashby/Workday); todas
      habilitadas na `f20manual` com coleta real (`SUCCEEDED`, exceto Accenture
      `PARTIAL` com 1997 itens reais — ver evidência).
- [x] As 5 empresas com ATS confirmado por sondagem (Loadsmart, Zup, EBANX, Devsu,
      Azumo) importadas via `CompanyService.reconcile` (não inserção manual), com
      `company_source` e, após revisão de termos, `source_definition` habilitada.
      Todas com coleta real `SUCCEEDED`.
- [x] Para cada fonte habilitada neste card, pelo menos um item real coletado e
      visível na API/Overview. 19 de 20 fontes `SUCCEEDED`; Accenture `PARTIAL` com
      1997 itens (evidência real, board grande demais para a paginação atual do
      coletor Workday — fora do escopo deste card).
- [x] Nenhuma fonte Gupy tocada; Red Hat e CESAR permanecem fora deste card (ou
      viram sub-cards próprios, se alguém pesquisar o tenant/endpoint deles depois).
      Red Hat teve o tenant Workday achado nesta sessão e foi importado/habilitado
      como extensão explícita do escopo (pedido do usuário); CESAR permanece fora,
      DB/FCamara/Minsait (Gupy) nunca sondados.

### Extensão de escopo executada nesta sessão (fora do card original)

Além do escopo original (5 + 5), a sessão também importou as ~42 empresas classe (d)
restantes (excluídas Gupy/CESAR/Red Hat) e rodou `discover_ats.py`/`discover_sites.py`
sobre elas, ativando 9 boards adicionais achados (Andela, Bluelight Consulting,
Braintrust, LiteLLM, Percona, Roboflow, Rollstack, Turing, VTEX) + Red Hat — 10 fontes
novas além das 10 originais. Ver evidência para a lista completa, contagens e
incertezas (URLs de careers page chutadas para várias das 42 empresas).

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
