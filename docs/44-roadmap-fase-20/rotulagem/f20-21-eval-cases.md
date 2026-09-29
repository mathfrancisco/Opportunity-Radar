# Rotulagem F20-21 — Conjunto de avaliação (revisão dos 41 casos reais)

- **Card:** [F20-21](../fase-20/f20-21-conjunto-de-avaliacao-no-groq.md)
- **Achado crítico (bloqueia o critério "50 casos rotulados versionados"):**
  `.git/info/exclude` tem a linha `opportunity_analysis/` (comentada "personal, never
  commit"). Esse padrão local (não é o `.gitignore` do repositório) casa com
  `prompts/opportunity_analysis/` inteiro — inclusive `eval/cases/`, que é onde os casos
  **revisados** deveriam ir para virar parte do harness versionado. `.gitignore`
  (compartilhado) já ignora só `prompts/opportunity_analysis/eval/drafts/`, de propósito
  (rascunhos não revisados). A regra local em `.git/info/exclude` é mais ampla e também
  esconde `eval/cases/` — `git ls-files prompts/opportunity_analysis/eval/cases` retorna 0
  arquivos, apesar de existirem 50 arquivos no disco (41 reais + 9 sintéticos). **Nenhum
  caso de avaliação jamais foi commitado nesta máquina**, mesmo com o trabalho de rotulagem
  já feito. Isso não foi corrigido aqui (é configuração git local, fora do escopo dos
  arquivos deste card); fica registrado para decisão humana — provavelmente remover ou
  restringir essa linha antes de comitar `eval/cases/`.
- **Situação dos casos:** 41 casos reais + 9 sintéticos = 50 arquivos em
  `prompts/opportunity_analysis/eval/cases/`, todos com `expected.verdict`,
  `must_mention_risks` e `must_not_claim` já preenchidos por uma sessão de agente anterior
  — **nenhum confirmado por humano**. Nenhum novo caso real foi criado nesta sessão (não
  há orçamento de Groq nem chamada real, conforme "Não fazer" do card); o trabalho aqui é
  revisar o que já existe.
- **Nota de metodologia (não é bug):** em todos os 41 casos, `expected.verdict` é
  idêntico a `payload.verdict`. Isso é esperado, não um erro de cópia: `verdict` e
  `eligibility` vêm do motor de regras determinístico (`matching/evaluation.py`), não são
  o que o LLM decide. O harness mede se o texto do LLM é fiel a esse veredito já calculado
  (menciona os riscos certos, não afirma o que não deveria), não se o LLM "acertou" um
  veredito — o próprio docstring de `eval_analysis.py` diz isso ("no model judges
  another").

## Lacuna frente ao plano do card (10 Java, 10 fullstack, 10 IA, 10 fora de área, 10 inelegíveis = 50)

| Categoria pedida pelo card | Casos reais existentes | Rótulo usado no arquivo | Faltam |
| --- | --- | --- | --- |
| Java | 0 | (nenhum bucket "java"; ver "backend" abaixo) | 10 |
| Fullstack | 3 (09, 10, 11) | `fullstack` | 7 |
| IA | 1 (12) | `ai` | 9 |
| Fora de área | 19 (13–31) | `fora_de_area` | 0 (excedeu) |
| Inelegíveis | 10 (32–41) | `ineligible` | 0 (completo) |
| (bucket não pedido) | 8 (01–08) | `backend` | — |

O bucket `backend` (8 casos) não corresponde ao pedido do card ("10 Java"); ver a tabela de
casos abaixo — a maioria desses 8 nem é papel de engenharia. Hipótese mais provável: o
`export_eval_cases.py` exporta por **verdito** (`REVIEW_REQUIRED`, etc.), não por
área/tecnologia, então quem moveu os drafts para `cases/` rotulou pelo que sobrou no pool
de rascunhos exportado, não porque encontrou vagas Java de verdade. **Recomendação:**
rodar `make export-eval-cases` de novo com filtro manual por título (`grep -il java`) para
achar candidatos Java/fullstack/IA reais antes de fechar os 50 casos — ou aceitar o desvio
e registrar no card por que a composição não seguiu o plano original.

## Revisão caso a caso (41 casos reais)

| Caso | Título da vaga | Bucket do arquivo | Recomendação | Justificativa | Confiança | Decisão do usuário |
| --- | --- | --- | --- | --- | --- | --- |
| 01-backend-03 | Forward Deployed Engineer - US East Coast | backend | **Reclassificar** | Papel de deployment/customer-facing, não engenharia backend; não tem o risco "fora da área" que casos equivalentes (13–31) têm. | Alta | aceito |
| 02-backend-04 | Senior Product Manager - Core Platform | backend | **Reclassificar** | É Product Manager — mesmo tipo de papel do caso 26 (`fora_de_area`), mas aqui sem o risco de área. Inconsistência clara entre dois casos quase idênticos. | Alta | aceito |
| 03-backend-08 | Senior Support Engineer \| Remote \| North America | backend | **Reclassificar** | Suporte técnico, não engenharia backend. | Alta | aceito |
| 04-backend-24 | Forward Deployed Engineer - EMEA | backend | **Reclassificar** | Mesmo caso do 01, duplica o tipo de papel. | Alta | aceito |
| 05-backend-28 | Staff Core Platform Engineer | backend | Aceitar | "Core Platform Engineer" é plausivelmente uma vaga de engenharia (infra/plataforma); mais defensável que os outros do bucket. | Média | aceito |
| 06-backend-31 | Technical Account Manager (US) | backend | **Reclassificar** | Papel comercial/pós-venda técnico, não engenharia backend — mesmo padrão do caso 21 (`fora_de_area`, Account Executive). | Alta | aceito |
| 07-backend-38 | Backend Engineer (Security) | backend | Aceitar | Título é literalmente "Backend Engineer"; único caso do bucket sem ambiguidade. | Alta | aceito |
| 08-backend-40 | Technical Recruiter (3 month FTC) | backend | **Reclassificar** | Recrutamento, não engenharia backend. | Alta | aceito |
| 09-fullstack-07 | Senior Product Engineer (TS/NodeJS/Vue) | fullstack | Aceitar | Vaga técnica fullstack real. | Alta | aceito |
| 10-fullstack-18 | Sr Growth Engineer (Fullstack TS/Vue/NodeJS) | fullstack | Aceitar | Idem. | Alta | aceito |
| 11-fullstack-37 | Design Engineer | fullstack | Revisar | "Design Engineer" é ambíguo (pode ser UX/produto, não fullstack de verdade); recomendo abrir a descrição completa antes de aceitar o bucket. | Média | aceito |
| 12-ai-11 | Agentic Engineering Platform Engineer | ai | Aceitar | Papel de plataforma de IA/agentes, coerente com o bucket. | Alta | aceito |
| 13 a 31 (19 casos) | Sales/Marketing/CS/PM/People/Design etc. (ver lista completa no JSON) | fora_de_area | Aceitar (lote) | Risco "não é desenvolvimento de software" aplicado de forma consistente nos 19; nenhuma inconsistência interna encontrada. Excede a meta (10), o que é aceitável — sobra não é problema. | Alta | aceito |
| 32 a 41 (10 casos) | Treasury/Lead SWE Hybrid/Data Analytics/Reliability/Controllership/AML/Infra/Data Center/Compliance/Communications | ineligible | Aceitar (lote) | Todos `ONSITE`/`HYBRID`, risco "incompatível com trabalho remoto" consistente, veredito `INELIGIBLE` coerente com a regra de elegibilidade do perfil (só aceita remoto). | Alta | aceito |

*(A lista completa dos 19 casos `fora_de_area` e dos 10 `ineligible`, com título e arquivo,
está em `f20-21-eval-cases.json`, campo `casos`, para não repetir aqui uma tabela de 31
linhas idênticas em estrutura.)*

## Como aplicar

1. O revisor decide, para os 6 casos `backend` marcados **Reclassificar**: mover o rótulo
   do arquivo (renomear `NN-backend-*.json` para `NN-fora_de_area-*.json` ou um novo bucket
   `outras_areas`) e, se aceitar a reclassificação, adicionar a mesma frase de risco de área
   que os casos 13–31 usam (`"Vaga não é de desenvolvimento de software; foge da área de
   atuação do perfil (Python)."`) ao `must_mention_risks` desses 6 arquivos.
2. Resolver o achado crítico do `.git/info/exclude` antes de comitar `eval/cases/` — sem
   isso, nenhum caso entra no `git add`, mesmo que pareça ter sido adicionado.
3. Decidir se vale gerar mais casos Java/fullstack/IA reais (rodando
   `make export-eval-cases` e filtrando manualmente por tecnologia) para fechar a lacuna
   de composição, ou aceitar o desvio e documentar no card.
4. Rodar `make eval-analysis` só depois dos 50 casos estarem versionados e as
   reclassificações aplicadas — não antes, para não gastar cota do Groq medindo um
   conjunto que ainda vai mudar.

## Recomendação para os 26 drafts de lacuna (`gap-{java,fullstack,ai}-NN`)

Os 26 drafts exportados pela sessão anterior (10 Java, 7 fullstack, 9 IA, todos `role_family=SOFTWARE_ENGINEERING`, `work_mode=REMOTE`) tinham `must_mention_risks` e `must_not_claim` vazios — recomendações de rotulagem abaixo, seguindo exatamente a convenção dos 50 casos já revisados (risco de remuneração ausente quando `compensation` é `null`, risco de países ausentes quando `allowed_countries` é vazio, risco de habilidade ausente por skill de `required_skills` que não está no perfil Python, ou o risco genérico de habilidades não extraídas quando `required_skills` é vazio). Nenhuma dessas vagas tem risco de área — são papéis de engenharia de verdade. **Decisão do usuário: aceito (pré-autorizado)** para as 26 linhas, incluindo a promoção para `eval/cases/` (ver seção de rebalanceamento abaixo). PII: encontrado 1 caso (`gap-java-01`) com o primeiro nome da recrutadora na descrição ("eu sou a Bia, recruiter..."); escrito para "Recrutadora" antes da promoção. Nenhum outro hit em e-mail, telefone, LinkedIn ou nome próprio nos 26 drafts.

| Draft | Título | Verdict | must_mention_risks | must_not_claim | Promovido como | Decisão do usuário |
| --- | --- | --- | --- | --- | --- | --- |
| gap-java-01-review_required.json | [Job-30904] Mid level Java Developer, Brazil | REVIEW_REQUIRED | A vaga exige Java, que não está no perfil.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 42-java-01-review_required.json | aceito (pré-autorizado) |
| gap-java-02-review_required.json | [Job-31106]  Senior Kotlin/Java Developer, Brazil | REVIEW_REQUIRED | A vaga exige AWS, que não está no perfil.; A vaga exige Java, que não está no perfil.; A vaga exige Kotlin, que não está no perfil.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 43-java-02-review_required.json | aceito (pré-autorizado) |
| gap-java-03-review_required.json | [Job-31311] Master JAVA/AWS  Developer, Brazil | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 44-java-03-review_required.json | aceito (pré-autorizado) |
| gap-java-04-review_required.json | [Job 31746] Software Architect (Java) | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 45-java-04-review_required.json | aceito (pré-autorizado) |
| gap-java-05-review_required.json | [Job-31932] Senior Java /Python Developer Back End, Brazil | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 46-java-05-review_required.json | aceito (pré-autorizado) |
| gap-java-06-review_required.json | [Job - 31296] Master Backend Developer / Tech Lead — Java, Go & AWS, Brazil | REVIEW_REQUIRED | A vaga exige MongoDB, que não está no perfil.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 47-java-06-review_required.json | aceito (pré-autorizado) |
| gap-java-07-review_required.json | [Job-31697] Mid-Level Java Developer – AI \| Java + React, Brazil | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 48-java-07-review_required.json | aceito (pré-autorizado) |
| gap-java-08-review_required.json | [Job-31698] Senior Java Developer – AI \| Java + React. Brazil | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 49-java-08-review_required.json | aceito (pré-autorizado) |
| gap-java-09-review_required.json | [Job 31822] Software Architect (Tech Lead Java & IA Generativa) | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 50-java-09-review_required.json | aceito (pré-autorizado) |
| gap-java-10-review_required.json | [Job-31846] Mid Level / Senior Java/IA Developer, Brazil | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 51-java-10-review_required.json | aceito (pré-autorizado) |
| gap-fullstack-01-review_required.json | Senior Fullstack Engineer | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 52-fullstack-01-review_required.json | aceito (pré-autorizado) |
| gap-fullstack-02-review_required.json | [Job - 31638] Mid Level  FullStack Developer (.NET/React) | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil | 53-fullstack-02-review_required.json | aceito (pré-autorizado) |
| gap-fullstack-03-review_required.json | [Job-31524] Senior Software Developer Fullstack - Kotlin/Next.js (React/TypeScript), Brazil | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 54-fullstack-03-review_required.json | aceito (pré-autorizado) |
| gap-fullstack-04-review_required.json | [Job-31651] Tech Lead FullStack (.Net/React), Brazil | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 55-fullstack-04-review_required.json | aceito (pré-autorizado) |
| gap-fullstack-05-review_required.json | [Job-31927]  SR FullStack Developer - [C# / NodeJS + React] | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 56-fullstack-05-review_required.json | aceito (pré-autorizado) |
| gap-fullstack-06-review_required.json | [31868]  AI Fullstack Java/Angular Desenvolvedor | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 57-fullstack-06-review_required.json | aceito (pré-autorizado) |
| gap-fullstack-07-review_required.json | [Job- 31800] Mid-Level Fullstack Developer ( Java + Angular ) , Brazil | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 58-fullstack-07-review_required.json | aceito (pré-autorizado) |
| gap-ai-01-review_required.json | Applied AI Engineer | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil | 59-ai-01-review_required.json | aceito (pré-autorizado) |
| gap-ai-02-review_required.json | Senior Machine Learning Engineer, Personalization, Muse | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 60-ai-02-review_required.json | aceito (pré-autorizado) |
| gap-ai-03-review_required.json | Senior Staff Machine Learning Engineer - Content Platform | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 61-ai-03-review_required.json | aceito (pré-autorizado) |
| gap-ai-04-review_required.json | Staff Machine Learning Engineer, Home Surfaces | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 62-ai-04-review_required.json | aceito (pré-autorizado) |
| gap-ai-05-review_required.json | Staff Machine Learning Engineer, Personalization | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 63-ai-05-review_required.json | aceito (pré-autorizado) |
| gap-ai-06-review_required.json | [30118] - Senior AI Engineer | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 64-ai-06-review_required.json | aceito (pré-autorizado) |
| gap-ai-07-review_required.json | [Job- 31650] Master Generative AI Developer, Brazil | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 65-ai-07-review_required.json | aceito (pré-autorizado) |
| gap-ai-08-review_required.json | [Job-31614]  Senior Machine Learning Engineer, Brazil | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 66-ai-08-review_required.json | aceito (pré-autorizado) |
| gap-ai-09-review_required.json | [Job-31455] AI Engineer & Software Architect, Brasil | REVIEW_REQUIRED | A vaga não relaciona habilidades técnicas exigidas extraídas; o perfil não pode ser conferido contra requisitos explícitos.; A remuneração não é informada na vaga.; Os países permitidos para contratação não são informados na vaga. | todos os requisitos técnicos da vaga são atendidos pelo perfil; remuneração competitiva | 67-ai-09-review_required.json | aceito (pré-autorizado) |

## Rebalanceamento para caber em 50 (10/10/10/10/10, conforme o card)

O card pede exatamente 10 Java + 10 fullstack + 10 IA + 10 fora de área + 10 inelegíveis = 50 — não há categoria `backend` nem `synthetic` no plano. Promover os 26 drafts (10 Java, 7 fullstack, 9 IA) fecha Java/fullstack/IA em 10/10/10 exatamente, mas sem mexer em mais nada o total passaria de 76. Para caber em 50 sem inventar regra nova:

- **fora_de_area**: tinha 25 (19 originais `13–31` + 6 reclassificados de `backend` `01,02,03,04,06,08`). Ficam em `eval/cases/` os 6 reclassificados (documentam a decisão de rotulagem mais discutível do lote) + os 4 primeiros do lote batch-aceito (`13,14,15,16`) = 10. Os 15 restantes (`17`–`31`) vão para `prompts/opportunity_analysis/eval/cases-secondary/` como reserva, não descartados.
- **backend** (`05`, `07`, os 2 casos que a rotulagem anterior manteve como `Aceitar` em vez de reclassificar): não corresponde a nenhum dos 5 buckets do card. Movidos para `cases-secondary/`.
- **synthetic** (9 arquivos, casos sintéticos de regressão: negação, contradição, prompt injection etc.): também fora dos 5 buckets do card. Movidos para `cases-secondary/` — continuam versionados, só não fazem parte dos 50 que `load_cases()` lê de `eval/cases/`.
- Resultado: `eval/cases/` tem exatamente 50 arquivos, 10 por bucket (java/fullstack/ai/fora_de_area/ineligible). `eval/cases-secondary/` tem os 26 excedentes (2 backend + 15 fora_de_area + 9 synthetic), preservados para uso futuro se o card mudar de plano.
- `tests/backend/matching/test_eval_scoring.py::test_every_case_in_the_set_loads_with_a_complete_answer_key` passou com os 50 novos arquivos (`22 passed`), confirmando que o schema/loader aceitam a composição.
