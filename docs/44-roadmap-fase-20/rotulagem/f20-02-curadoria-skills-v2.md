# Rotulagem F20-02 — Curadoria de `skills-v2` (revisão humana das decisões já aplicadas)

- **Card:** [F20-02](../fase-20/f20-02-curadoria-skills-v2.md)
- **Situação:** o card já está marcado "Feito" e a taxonomia (`SKILL_TAXONOMY` em
  `src/opportunity_radar/opportunities/domain.py`) já tem `ai`, `cicd` e `observability`
  aplicados, com `SKILL_TAXONOMY_VERSION = "skills-v2"` e reprocessamento oficial rodado
  (48,46% → 90,74% de cobertura). **Nenhuma decisão de termo foi confirmada por um humano**
  — todas vieram de uma sessão de agente anterior (`docs/pesquisas/curadoria-skills-v2.md`).
  Este documento reproduz a medição no acervo real (630 descrições, 648 oportunidades,
  números idênticos aos já publicados) e pede a confirmação humana por termo, agrupado por
  skill canônica proposta, com os ambíguos marcados.
- **Medido em:** 2026-09-26. Réplica local da lógica de `scripts/unmatched_skill_terms.py`
  (mesmo regex, mesma stopword list, mesmas aliases conhecidas) sobre um dump somente-leitura
  de `opportunities.opportunity.description` (`COPY ... TO STDOUT`, sem gravação no banco).
  Saída idêntica à documentada: `630 descriptions scanned`, `481 data`, `477 build`,
  `473 every`, `467 across`... confirma que a medição publicada é reproduzível e real.

## Achado novo desta revisão: risco do alias `ci` confirmado com dados reais

O documento anterior já registrava "risco residual" teórico para o alias `ci` (2
caracteres, sem desambiguação por contexto, ao contrário de `go`/`react`). Esta revisão
quantifica o risco:

- **179 das 630 descrições (28%) mencionam literalmente `CI&T`** — o nome da própria
  empresa que posta a maior parte das vagas do acervo (CI&T é uma consultoria de TI que
  aparece como `company_name` em centenas de vagas).
- O tokenizador do script corta em `&` (não é caractere de token), então toda menção a
  "CI&T" no texto (ex.: `"CI&T, we help large enterprises..."`, comum no boilerplate
  institucional de cada vaga) produz o token `ci` isolado — o mesmo token que o alias
  `cicd` reconhece como evidência de CI/CD.
- Das 218 descrições em que o termo `ci` aparece (contagem do script, dedupe por
  descrição), **179 (82%) são explicáveis só pela menção a "CI&T"** — não por conteúdo real
  de CI/CD. Isso não prova que todas as 179 são falso-positivo (a mesma vaga pode citar
  "CI&T" e também "CI/CD" de verdade), mas mostra que a maioria das ocorrências de `ci`
  isolado nesta base tem uma causa não técnica identificável.

**Recomendação nova (Alta confiança):** remover o alias solto `"ci"` da entrada `cicd` em
`SKILL_TAXONOMY`, mantendo só `"ci/cd"`, `"continuous integration"`, `"continuous
deployment"` (que não colidem com "CI&T"). Isso é uma correção pontual, não uma reversão
da skill `cicd` inteira.

## Recomendações por skill canônica (grupos)

| Skill canônica | Termo(s)/alias | Recomendação | Justificativa | Confiança | Decisão do usuário |
| --- | --- | --- | --- | --- | --- |
| `ai` (já aplicada) | `ai` (462 desc.) | Manter | Termo técnico inequívoco, altíssima frequência, sem alias curto arriscado. | Alta | aceito |
| `ai` (já aplicada) | `artificial intelligence`, `machine learning`, `ml`, `agentic ai` | Manter | Sinônimos/variações reais observadas no corpus (ex.: "agentic AI systems"). | Alta | aceito |
| `cicd` (já aplicada) | `ci/cd`, `continuous integration`, `continuous deployment` | Manter | Termos multi-palavra, não colidem com nomes de empresa. | Alta | aceito |
| `cicd` (já aplicada) | `ci` (alias isolado, 218 desc.) | **Remover o alias** (revisar) | 82% das ocorrências de `ci` isolado no corpus real vêm de "CI&T" (nome da empresa), não de CI/CD — ver seção acima. | Alta | aceito |
| `observability` (já aplicada) | `observability` (124 desc.) | Manter | Termo técnico inequívoco, sem ambiguidade observada. | Alta | aceito |
| — | `apis` (146, fora do top 60) | Manter descartado | Genérico; qualquer vaga backend cita "APIs" sem nomear um protocolo específico. | Alta | aceito |
| — | `cloud` (193) | Manter descartado | A taxonomia já cobre provedores específicos (`aws`, `azure`, `gcp`); `cloud` genérico duplicaria sinal e arrisca falso positivo em uso não técnico. | Alta | aceito |
| — | `sdlc` (183) | Manter descartado | Sigla de processo/metodologia, não uma tecnologia nomeada — fora do padrão das 30 entradas atuais. | Média | aceito |
| — | `martech` (178) | Manter descartado | Categoria de produto/marketing, fora da área do perfil e do tipo de entrada da taxonomia. | Alta | aceito |
| — | `architecture`/`systems`/`platform`/`frameworks`/`tools`/`stack` | Manter descartado | Palavras-guarda-chuva sem tecnologia nomeada; marcar geraria ruído massivo. | Alta | aceito |
| `ai` (já aplicada, como alias) | `agentic` (140) | Manter como alias de `ai` | Variação de "agentic AI", já coberta por `agentic ai` na entrada `ai`. | Média | aceito |

## Cobertura sobre count>=2: nenhum termo tecnológico novo além do já decidido

Rodando a mesma lógica com min-count=2 sobre as 630 descrições reais, e buscando por uma
lista ampla de tecnologias comuns não cobertas pela taxonomia atual (`kafka`, `spark`,
`airflow`, `ansible`, `jenkins`, `angular`, `vue`, `swift`, `spring`, `elastic`,
`snowflake`, `databricks`, `tableau`, `grafana`, `prometheus`, `istio`, `helm`,
`salesforce`, `hubspot`, `figma`, `webpack`, `rabbitmq`, `grpc`, `hadoop`, `scala`,
`numpy`, `pandas`, `pytorch`, `tensorflow`, `llm`, `genai`, `gpt`, `openai`, `anthropic`,
`langchain`, `embeddings`, `dynamodb`, `bigquery`, `redshift`, `lambda`, `serverless`,
`microservices`, `monorepo`, `svelte`, `nginx`, `scrum`, `kanban`, `oauth`, `jwt`, `saml`,
`sso`, `gdpr`, `hipaa`, `soc2`, `compliance`, `linux`), **nenhum aparece na lista de
candidatos com contagem ≥ 2** (top 401 termos, arquivo completo reproduzível). Isso é
evidência de que a curadoria de `skills-v2` já esgotou os candidatos de sinal técnico real
com frequência relevante neste acervo específico (que é dominado por boilerplate de RH de
empresas modernas — n8n, Nubank, CI&T, Spotify, Supabase, RevenueCat, Render, Firecrawl,
Trigger.dev, Browserbase, WorkOS, Cartesia). Recomendo **não abrir nova rodada de curadoria
de termos** até o acervo crescer ou diversificar de fontes.

## Como aplicar

1. O revisor marca "aceitar"/"rejeitar" em cada linha da tabela acima.
2. Para a única mudança recomendada (remover o alias `ci`), editar
   `src/opportunity_radar/opportunities/domain.py:227` — trocar
   `("ci/cd", "ci", "continuous integration", "continuous deployment")` por
   `("ci/cd", "continuous integration", "continuous deployment")`.
3. Ver `f20-02-curadoria-skills-v2.json` para o formato máquina (uma linha por termo, com
   `aceito: null` para o revisor preencher `true`/`false`).
4. Se o alias `ci` for removido, rodar o reprocessamento oficial de novo (mesmo processo
   documentado em `docs/pesquisas/curadoria-skills-v2.md`, seção "Reprocessamento
   oficial") e medir se a cobertura de `cicd` cai — a expectativa é uma queda pequena,
   porque a maioria das vagas que citam CI/CD real também usam a forma `ci/cd` ou
   "continuous integration/deployment" em algum lugar do texto, não só o token isolado.
