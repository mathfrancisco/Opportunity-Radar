# SPEC — Descoberta de startups sem Wellfound/YC (busca em domínios de ATS + HN)

- **Status:** Planejada; nenhuma capacidade abaixo é declarada entregue
- **Data:** 2026-09-28
- **Escopo:** achar mais startups (idealmente YC, seed/Series A, remoto/LATAM/Brasil)
  usando fontes com contrato já aceito pelo radar — busca Tavily restrita aos domínios de
  ATS já suportados, validada pela sonda direta existente — e, condicionado a revisão de
  termos própria, o thread mensal "Who is hiring?" da Hacker News via API oficial. Marcar
  a empresa resultante como "startup" com evidência, e expor filtro na UI.
- **Cards de execução:** [Fase 20, Bloco C](44-roadmap-fase-20/README.md) — F20-53 a F20-55
- **Pesquisa que fundamenta esta SPEC:**
  [`docs/pesquisas/descoberta-startups-ats.md`](pesquisas/descoberta-startups-ats.md)
- **Não fundamenta esta SPEC:** Wellfound e YC/Work at a Startup diretos — fechados não
  viáveis em [`docs/pesquisas/wellfound-yc-jobs.md`](pesquisas/wellfound-yc-jobs.md)
  (F20-51, F20-52). Nada nesta SPEC toca `wellfound.com`, `ycombinator.com/jobs` ou
  `workatastartup.com`.
- **Documentos relacionados:** [SPEC Tavily (41)](41-spec-tavily.md),
  [SPEC de varredura produtiva (39)](39-spec-varredura-produtiva.md),
  [SPEC LLM cloud e consolidação (43)](43-spec-llm-cloud-e-consolidacao.md)

---

## 1. Objetivo e limite da promessa

O usuário tem interesse específico em vagas de startups no board. Wellfound e YC/WaaS
proíbem automação nos próprios Termos de Uso (F20-51/F20-52) — esta SPEC não tenta
contornar isso. Em vez disso, usa dois caminhos que **não têm** essa restrição:

1. Buscar (Tavily) por sinal de startup (`"Y Combinator"`, `"YC "+batch`, `"seed
   stage"`, `"Series A"`) **restrito aos domínios de ATS que o radar já coleta**
   (Ashby, Greenhouse, Lever, Workable, Teamtailor). O resultado aponta direto para o
   board do ATS da própria empresa — nunca para Wellfound/YC.
2. Ler o thread mensal "Ask HN: Who is hiring?" pela API oficial da Hacker News
   (`hacker-news.firebaseio.com`, mantida pela própria YC/HN para acesso programático).

Não é promessa de cobertura total do universo de startups — é mais uma fonte de
descoberta de empresa, no mesmo funil que a busca web (F20-44) e a descoberta limitada de
sites (F20-36) já alimentam. Nenhuma vaga entra no acervo sem passar por normalização,
identidade e matching como qualquer outro `CollectedItem` — mesma invariante do §1 da
SPEC 41.

## 2. Decisões

- **Não é coletor novo.** A busca em domínios de ATS reaproveita 100%
  `TavilySearchCollector` (F20-44) — só muda a query (termo de startup) e o
  `include_domains` (restrito aos domínios de ATS, não geral). Nenhum `source_type` novo,
  nenhuma entrada nova em `SUPPORTED_ATS`/`PROBE_TYPES`.
- **`probe_direct_ats`/`limited_discovery` (F20-27/F20-36) não muda.** Continuam
  validando um board a partir de nome de empresa + URL semente, exatamente como hoje.
  A busca desta SPEC alimenta o funil de proposta com **mais candidatos a empresa**, não
  muda como um candidato é validado.
- **Marca de "startup" é evidência anexada, não uma nova fonte de verdade.** O campo
  novo em `company_radar.company` (ou tabela satélite, a decidir no card F20-54) guarda
  `is_startup_evidence` — o texto/URL de onde veio o sinal ("Y Combinator (S24)" numa
  vaga do Greenhouse, por exemplo) — igual ao padrão de evidência do F20-46. Nunca é um
  booleano sem origem: sinal fraco (`"seed stage"` sem marca) e sinal forte (menção
  nomeada a "Y Combinator"/YC + batch) ficam distintos no dado guardado, seguindo a
  recomendação medida no piloto (query sem marca teve mais falso positivo).
- **Hacker News entra por API oficial, não por scraping de `news.ycombinator.com`.**
  Antes de qualquer código, revisão de termos formal no card F20-55 (mesmo padrão do
  F20-32/F20-51/F20-52): robots.txt de `news.ycombinator.com`, texto de
  `ycombinator.com/legal` aplicado especificamente ao uso da Firebase API (não ao site),
  e confirmação de que a API (`github.com/HackerNews/API`) não tem cláusula própria
  restritiva. Endpoint/cláusula que proíbe automação encerra o card, como sempre.
- **Orçamento de créditos compartilhado.** As queries de busca de startup entram na
  mesma fila e no mesmo `TavilyBudgetGuard` do F20-43 — não é orçamento novo. Cadência e
  número de queries por ciclo são decisão do card F20-53, medida contra o teto real
  configurado (o piloto desta SPEC estimou ~15 créditos por ciclo com 5 domínios × 3
  termos; a confirmar).

## 3. Fatos do piloto (evidência resumida — ver pesquisa completa)

- 4 buscas Tavily (`site:<domínio-ATS> <termo-startup>`, profundidade `basic`, 1 crédito
  cada) devolveram 40 resultados / ~20 empresas distintas.
- **~95% dos candidatos eram novos** frente às 223 empresas já no catálogo
  (`company_radar.company`, consulta somente leitura).
- Sinal de marca nomeada (YC/"Y Combinator") teve mais precisão (57% dos resultados úteis
  citavam o sinal explicitamente) do que sinal de estágio sem marca (`"seed stage"`/
  `"Series A"` sozinhos: 25%, com um falso positivo grosseiro — empresa grande capturada
  por termo genérico).
- Mesma empresa apareceu em dois domínios de ATS diferentes (Weekday em Lever e
  Workable) — dedupe de proposta precisa comparar por empresa/nome normalizado, não só
  por URL de board.

## 4. Fluxo

```text
perfil/termos de startup (config)
  → TavilySearchCollector com include_domains = domínios de ATS já suportados
  → resultado aponta board de ATS da própria empresa (nunca Wellfound/YC)
  → known_ats_boards (F20-44) filtra o que já tem CompanySource habilitada
  → candidato novo entra na fila de homologação (F20-25) com evidência de origem
    (F20-46) + evidência de sinal de startup (marca forte/fraca, F20-54)
  → homologação humana decide habilitar
  → coleta segue pelo coletor de ATS já existente (Ashby/Greenhouse/Lever/Workable/
    Teamtailor) — nenhum coletor novo
```

Caminho HN (F20-55), separado:

```text
Algolia HN Search (localizar item do mês "Who is hiring?")
  → Firebase API oficial (ler comentários de nível 1)
  → parsing heurístico de texto livre (empresa, remoto, stack) — sem schema.org
  → mesmo funil de proposta/homologação acima
```

## 5. Marcação "startup" (F20-54)

- Campo/tabela satélite em `company_radar` guardando: sinal (`yc_batch`, `seed_stage`,
  `series_a`, outro), força (`forte`/`fraco`, conforme §2), texto/URL de evidência, data.
- Filtro na UI (Inbox/Overview, `apps/web`) por "é startup" e, quando disponível, por
  batch YC — não altera elegibilidade, score nem veredito do matching (mesma invariante
  do §Invariantes da Fase 20).
- Evidência pode vir de qualquer fonte já homologada (não só da busca do F20-53) — um
  board já coletado pode ganhar a marca depois, se uma vaga futura citar o sinal.

## 6. Fora de escopo

- Qualquer chamada a `wellfound.com`, `ycombinator.com/jobs` ou `workatastartup.com`.
- Coletor novo de ATS ou `source_type` novo.
- Dataset de funding (Crunchbase ou similar) — sem fonte aberta e atualizada encontrada
  nesta rodada (ver pesquisa, seção "Opções descartadas").
- Listas GitHub "awesome-*" de startups — qualidade de dado inferior à busca direta;
  registrado como opção de reserva, sem card agora.
- Parsing estruturado de vaga da HN além de empresa/remoto/stack — texto livre não tem
  schema, não vale prometer os mesmos campos do JobPosting (F20-37).

## 7. Verificação

Cada card de execução (F20-53 a F20-55) traz seus próprios critérios de aceite com
teste, conforme o padrão da Fase 20 (`docs/44-roadmap-fase-20/README.md`, "Como um card é
executado"). Nenhuma chamada real à Tavily ou à API da HN roda no CI — fixtures/
`httpx.MockTransport`, mesmo padrão do F20-44.
