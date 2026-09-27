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
| 01-backend-03 | Forward Deployed Engineer - US East Coast | backend | **Reclassificar** | Papel de deployment/customer-facing, não engenharia backend; não tem o risco "fora da área" que casos equivalentes (13–31) têm. | Alta | |
| 02-backend-04 | Senior Product Manager - Core Platform | backend | **Reclassificar** | É Product Manager — mesmo tipo de papel do caso 26 (`fora_de_area`), mas aqui sem o risco de área. Inconsistência clara entre dois casos quase idênticos. | Alta | |
| 03-backend-08 | Senior Support Engineer \| Remote \| North America | backend | **Reclassificar** | Suporte técnico, não engenharia backend. | Alta | |
| 04-backend-24 | Forward Deployed Engineer - EMEA | backend | **Reclassificar** | Mesmo caso do 01, duplica o tipo de papel. | Alta | |
| 05-backend-28 | Staff Core Platform Engineer | backend | Aceitar | "Core Platform Engineer" é plausivelmente uma vaga de engenharia (infra/plataforma); mais defensável que os outros do bucket. | Média | |
| 06-backend-31 | Technical Account Manager (US) | backend | **Reclassificar** | Papel comercial/pós-venda técnico, não engenharia backend — mesmo padrão do caso 21 (`fora_de_area`, Account Executive). | Alta | |
| 07-backend-38 | Backend Engineer (Security) | backend | Aceitar | Título é literalmente "Backend Engineer"; único caso do bucket sem ambiguidade. | Alta | |
| 08-backend-40 | Technical Recruiter (3 month FTC) | backend | **Reclassificar** | Recrutamento, não engenharia backend. | Alta | |
| 09-fullstack-07 | Senior Product Engineer (TS/NodeJS/Vue) | fullstack | Aceitar | Vaga técnica fullstack real. | Alta | |
| 10-fullstack-18 | Sr Growth Engineer (Fullstack TS/Vue/NodeJS) | fullstack | Aceitar | Idem. | Alta | |
| 11-fullstack-37 | Design Engineer | fullstack | Revisar | "Design Engineer" é ambíguo (pode ser UX/produto, não fullstack de verdade); recomendo abrir a descrição completa antes de aceitar o bucket. | Média | |
| 12-ai-11 | Agentic Engineering Platform Engineer | ai | Aceitar | Papel de plataforma de IA/agentes, coerente com o bucket. | Alta | |
| 13 a 31 (19 casos) | Sales/Marketing/CS/PM/People/Design etc. (ver lista completa no JSON) | fora_de_area | Aceitar (lote) | Risco "não é desenvolvimento de software" aplicado de forma consistente nos 19; nenhuma inconsistência interna encontrada. Excede a meta (10), o que é aceitável — sobra não é problema. | Alta | |
| 32 a 41 (10 casos) | Treasury/Lead SWE Hybrid/Data Analytics/Reliability/Controllership/AML/Infra/Data Center/Compliance/Communications | ineligible | Aceitar (lote) | Todos `ONSITE`/`HYBRID`, risco "incompatível com trabalho remoto" consistente, veredito `INELIGIBLE` coerente com a regra de elegibilidade do perfil (só aceita remoto). | Alta | |

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
