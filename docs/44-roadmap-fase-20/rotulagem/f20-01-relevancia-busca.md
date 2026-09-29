# Rotulagem F20-01 — Relevância da busca no acervo real

- **Card:** [F20-01](../fase-20/f20-01-baselines-e-relatorios-da-busca.md)
- **Objetivo:** dar ao card F17-03 (`recall@10 fulltext > recall@10 like`) o gabarito humano
  que falta. O relatório `docs/pesquisas/eval-search-f17-03.md` já documenta que o
  `data/search-reference/queries.json` usado até agora foi construído por correspondência
  automática de substring (mesmo critério do modo `like`), o que favorece o `like` por
  construção — não é o julgamento humano que a SPEC 37 §10 pede. `queries.json` fica fora
  do git (local à máquina) e não existe nesta sessão; este documento propõe um novo
  conjunto lendo o título de cada vaga real (sem abrir a descrição completa para não
  reproduzir texto de terceiros além do necessário).
- **Medido em:** 2026-09-26, `docker compose -p opportunity-radar exec postgres psql`
  (somente `SELECT`, banco real com 648 oportunidades, container iniciado só para leitura,
  sem `down -v`, sem escrita).
- **Metodologia:** para cada consulta abaixo, os candidatos são os até 8 itens mais
  recentes cujo título ou nome da empresa contém o termo (mesma consulta `LIKE` que
  `scripts/eval_search.py --mode like` usa para o modo antigo), com PII removida (nenhum
  nome de pessoa/e-mail/telefone está nos campos usados — título, empresa, senioridade,
  área, modo de trabalho). **Toda linha abaixo é uma recomendação do agente, não uma
  decisão humana** — a coluna "decisão do usuário" fica vazia para o revisor preencher com
  `aceitar`, `rejeitar` ou um valor corrigido.
- **Duas vagas com zero candidato por título:** `kubernetes` e `frontend` — nenhuma vaga do
  acervo tem esses termos no título ou no nome da empresa (`frontend`/`front-end`/`front
  end` também não aparecem). `kubernetes` aparece em pelo menos 12 descrições (verificado
  por `LIKE` na coluna `description`), então o modo `like` (que só olha título/empresa)
  teria recall 0 nessas duas consultas por construção, enquanto o `fulltext` (peso C na
  descrição) poderia recuperá-las — evidência real a favor do full-text que o gabarito
  antigo, construído por substring de título, nunca teria capturado. Recomendo incluir as
  duas no `queries.json` novo com `relevant_urls` vazio preenchido manualmente pelo
  revisor após ler as descrições completas (fora do escopo de leitura deste agente).

## Tabela de recomendações

| Caso (consulta → vaga) | Recomendação | Justificativa | Confiança | Decisão do usuário |
| --- | --- | --- | --- | --- |
| python → `[Job-31720] Data developer (Python, FICO DMPS...)` (CI&T) | Relevante | Título cita Python explicitamente; vaga de dados com Python. | Alta | aceito |
| python → `[Job-31569] AWS I Python Application Architect` (CI&T) | Relevante | Título cita Python. | Alta | aceito |
| python → `[Job-31306] Senior IA Developer Java / Python` (CI&T) | Relevante | Python é uma das duas linguagens do título. | Alta | aceito |
| python → `[Job - 31570] AWS Python Cloud Application Architecture` (CI&T) | Relevante | Título cita Python. | Alta | aceito |
| python → `[Job-31932] Senior Java /Python Developer Back End` (CI&T) | Relevante | Python é uma das duas linguagens do título. | Alta | aceito |
| python → `[Job - 29835] Mid Level Python Developer` (CI&T) | Relevante | Título cita só Python. | Alta | aceito |
| python → `[Job-30600] Sr. Software Engineer (Python \| AWS Lambda \| React)` (CI&T) | Relevante | Python é uma das stacks citadas no título. | Alta | aceito |
| backend → `Backend Engineer (Security)` (Trigger.dev) | Relevante | Título é literalmente "Backend Engineer". | Alta | aceito |
| backend → `Senior Backend Engineer (Europe)` (Trigger.dev) | Relevante | Idem. | Alta | aceito |
| backend → `Senior Backend Engineer` (RevenueCat) | Relevante | Idem. | Alta | aceito |
| backend → `Backend Infrastructure Engineer` (Firecrawl) | Relevante | "Backend" está no título; papel de infra backend. | Alta | aceito |
| backend → `[Job 31840] Developer Backend Java Pleno` (CI&T) | Relevante | Título cita "Backend". | Alta | aceito |
| backend → `Senior Backend Engineer - Subscriptions` (Spotify) | Relevante | Idem. | Alta | aceito |
| backend → `[Job - 31296] Master Backend Developer / Tech Lead` (CI&T) | Relevante | Idem. | Alta | aceito |
| backend → `Senior Backend Data Engineer – Content Intelligence` (Spotify) | Ambíguo | Título tem "Backend", mas a vaga é de engenharia de dados (`role_family=DATA`), não backend de aplicação — um operador pode considerar fora da intenção de quem busca "backend" puro. | Média | aceito |
| devops → todos os 6 candidatos (Firecrawl, CI&T ×5) | Relevante | Todos os títulos citam "DevOps" explicitamente. | Alta | aceito |
| java → `[Job 31746] Software Architect (Java)` (CI&T) | Relevante | Título cita Java. | Alta | aceito |
| java → `[Job 31629] Mid Level Fullstack (Java / Angular)` (CI&T) | Relevante | Java é uma das stacks do título. | Alta | aceito |
| java → `[Job-31106] Senior Kotlin/Java Developer` (CI&T) | Relevante | Java é uma das stacks do título. | Alta | aceito |
| java → `[Job 31627] AI Engineer/Software Architect (Java + Angular)` (CI&T) | Relevante | Java é uma das stacks do título. | Alta | aceito |
| java → `[Job 31822] Software Architect (Tech Lead Java & IA Generativa)` (CI&T) | Relevante | Java é uma das stacks do título. | Alta | aceito |
| java → `[job-31803] Developer Senior Fullstack Angular/Java` (CI&T) | Relevante | Java é uma das stacks do título. | Alta | aceito |
| java → `[Job-30394] Senior Fullstack Developer (Java / React)` (CI&T) | Relevante | Java é uma das stacks do título. | Alta | aceito |
| java → `[Job 31840] Developer Backend Java Pleno` (CI&T) | Relevante | Java é uma das stacks do título. | Alta | aceito |
| react → todos os 8 candidatos (CI&T) | Relevante | Todos os títulos citam React ou "React/TypeScript" explicitamente. | Alta | aceito |
| sales → `Sales Enablement Manager` (n8n) | Relevante | Papel de vendas explícito no título. | Alta | aceito |
| sales → `Enterprise Sales Development Representative` (n8n) | Relevante | Idem. | Alta | aceito |
| sales → `Sales Development Representative - DACH` (n8n) | Relevante | Idem. | Alta | aceito |
| sales → `Sales Data Analyst` (n8n) | Ambíguo | Título tem "Sales", mas o papel é de análise de dados dentro da área comercial (`role_family=OPERATIONS`), não um vendedor — quem busca "sales" pode querer só papéis de linha de frente. | Média | aceito |
| sales → `Enterprise Sales Leader DACH` (n8n) | Relevante | Papel de liderança de vendas. | Alta | aceito |
| sales → `Sales Engineer` (Browserbase) | Ambíguo | "Sales Engineer" é um papel técnico pré-venda, híbrido entre engenharia e vendas; depende da intenção de quem busca. | Média | aceito |
| sales → `Head of Sales` (RevenueCat) | Relevante | Papel de liderança de vendas. | Alta | aceito |
| sales → `Pre-Sales Solutions Architect` (Supabase) | Ambíguo | Papel técnico de pré-venda, mesmo caso do "Sales Engineer". | Média | aceito |
| marketing → `AWS Partner Marketing Manager` (Supabase) | Relevante | Papel de marketing explícito, mesmo com `role_family=SALES` no dado (parceria comercial). | Média | aceito |
| marketing → `Marketing Lead` (Trigger.dev) | Relevante | Papel de marketing puro. | Alta | aceito |
| marketing → `Senior FP&A Manager - Marketing` (n8n) | Ambíguo | Papel de finanças (`FINANCE`) que atende a área de marketing, não um papel de marketing em si. | Média | aceito |
| marketing → `Senior Data Analyst - Marketing` (Supabase) | Ambíguo | Papel de dados (`DATA`) para a área de marketing, mesmo caso acima. | Média | aceito |
| marketing → `Startup Marketing` (Render) | Relevante | Papel de marketing puro. | Alta | aceito |
| marketing → `Senior Product Marketing Manager` (RevenueCat) | Relevante | Papel de marketing puro. | Alta | aceito |
| marketing → `Staff Software Engineer (Marketing Platforms)` (Nubank) | **Não relevante** | É uma vaga de engenharia de software (`SOFTWARE_ENGINEERING`) que constrói plataformas *para* marketing — quem busca "vagas de marketing" não está procurando um cargo de engenharia. Caso clássico de falso positivo por substring de título. | Alta | aceito |
| marketing → `Head of Growth Marketing` (Firecrawl) | Relevante | Papel de marketing puro. | Alta | aceito |
| node → todos os 5 candidatos (n8n ×2, CI&T ×3) | Relevante | Todos os títulos citam Node.js/NodeJS explicitamente. | Alta | aceito |
| aws → `AWS Partner Marketing Manager` (Supabase) | Ambíguo | "AWS" aqui é o nome do parceiro comercial (GTM), não a tecnologia; quem busca "vagas AWS" (técnicas) provavelmente não quer isto. | Média | aceito |
| aws → `AWS Gaming GTM Segment Lead` (Supabase) | **Não relevante** | Papel comercial/GTM sobre a parceria com AWS, não uma vaga técnica de AWS. | Alta | aceito |
| aws → `AWS Enterprise Segment Lead` (Supabase) | **Não relevante** | Mesmo caso acima. | Alta | aceito |
| aws → `[job-31310] Sênior DevOps (AWS)` (CI&T) | Relevante | Vaga técnica com AWS como tecnologia central. | Alta | aceito |
| aws → `[Job - 31247] AWS Data Specialist` (CI&T) | Relevante | Vaga técnica com AWS como tecnologia central. | Alta | aceito |
| aws → `[Job-31569] AWS I Python Application Architect` (CI&T) | Relevante | Vaga técnica com AWS como tecnologia central. | Alta | aceito |
| aws → `[Job - 31308] Specialist AWS Data Developer` (CI&T) | Relevante | Vaga técnica com AWS como tecnologia central. | Alta | aceito |
| aws → `[Job - 31570] AWS Python Cloud Application Architecture` (CI&T) | Relevante | Vaga técnica com AWS como tecnologia central. | Alta | aceito |
| fullstack → todos os 8 candidatos (n8n, Spotify ×2, CI&T ×5) | Relevante | Todos os títulos citam "Fullstack"/"Full Stack" explicitamente. | Alta | aceito |
| machine learning → todos os 8 candidatos (Nubank ×4, Firecrawl, Spotify ×3) | Relevante | Todos os títulos citam "Machine Learning" explicitamente. | Alta | aceito |
| product manager → `Senior Product Manager, Analytics Features` (RevenueCat) | Relevante | Título é "Product Manager". | Alta | aceito |
| product manager → `Senior Product Manager, Ad Monetization` (RevenueCat) | Relevante | Idem. | Alta | aceito |
| product manager → `Senior Product Manager (Enterprise)` (n8n) | Relevante | Idem. | Alta | aceito |
| product manager → `Senior Product Manager, Funnels` (RevenueCat) | Relevante | Idem. | Alta | aceito |
| product manager → `Product Manager - Strategic Partner Integrations` (Supabase) | Relevante | Idem. | Alta | aceito |
| product manager → `Staff Product Manager, CI/CD & Developer Productivity` (Render) | Relevante | Idem (título é "Product Manager", mesmo com `role_family=DESIGN` no dado, que parece um erro de classificação de área — não desta consulta). | Média | aceito |
| product manager → `Senior Product Manager - Core Platform` (n8n) | Relevante | Idem. | Alta | aceito |
| product manager → `Product Manager - Marketplace` (Supabase) | Relevante | Idem. | Alta | aceito |
| accounting → `Controllership Senior Specialist - Global Product Accounting` (Nubank) | Relevante | "Accounting" no título, papel de contabilidade. | Alta | aceito |
| accounting → `Controllership Specialist - Global Product Accounting` (Nubank) | Relevante | Idem. | Alta | aceito |
| qa → todos os 6 candidatos (CI&T) | Relevante | Todos os títulos citam "QA" explicitamente. | Alta | aceito |
| kubernetes → *(nenhum candidato por título)* | — | Ver nota acima: recall do `like` é 0 por construção; revisor decide os relevantes lendo descrição. | — | |
| frontend → *(nenhum candidato por título)* | — | Mesmo caso; nenhuma vaga do acervo usa "frontend"/variantes no título. | — | |

## Como aplicar

1. O revisor preenche "decisão do usuário" linha a linha (`aceitar`, `rejeitar` ou um texto
   livre corrigindo a recomendação).
2. Para cada linha aceita como Relevante (ou Ambíguo confirmado como relevante), rodar,
   dentro do container `api` do projeto `opportunity-radar`:
   `python scripts/search_reference.py add --query "<consulta>" --opportunity-id <id>`
   — os pares `query`/`opportunity_id` de cada linha aceita estão em
   `f20-01-relevancia-busca.json` (campo `recomendacao == "relevante"`), já prontos para
   iterar num loop; o `id` de cada candidato é o `opportunity_id` daquele arquivo, não o da
   URL. Alternativa mais direta: copiar `f20-01-relevancia-busca.json` para
   `data/search-reference/queries.json` mantendo só as entradas aceitas (o schema já é o
   que `scripts/search_reference.py`/`scripts/eval_search.py` esperam: `{"queries":
   [{"query": str, "relevant_urls": [str, ...]}]}`).
3. Isso recria `data/search-reference/queries.json` com um gabarito humano de fato, sem o
   viés documentado em `docs/pesquisas/eval-search-f17-03.md`.
4. Rerodar `docker compose exec api python scripts/eval_search.py --mode both` e comparar
   com os números antigos (recall@10 like=0,6357, fulltext=0,6279) — a expectativa, se a
   hipótese do relatório estiver certa, é o full-text virar maior que o like.
5. As duas consultas sem candidato por título (`kubernetes`, `frontend`) exigem que o
   revisor leia a descrição completa das vagas candidatas (não incluída aqui para não
   reproduzir texto de terceiros sem necessidade) e adicione manualmente com
   `scripts/search_reference.py add`.

## Addendum — decisão do usuário aplicada e medição real (2026-09-27)

O revisor aceitou todas as recomendações como estão (inclusive os 9 casos `ambíguo`,
mantidos como ambíguos — não promovidos a `relevante`). `data/search-reference/queries.json`
foi reconstruído localmente (fora do git, como o schema já previa) a partir das 86 linhas
`relevante` deste documento — 14 consultas, sem `kubernetes`/`frontend` (que continuam sem
gabarito, como a nota acima já previa). `docker compose -p opportunity-radar` (só leitura)
+ `python scripts/eval_search.py --mode both` deu:

```
mode=like     average recall@10 = 1.0000   average nDCG@10 = 0.9416
mode=fulltext average recall@10 = 0.8170   average nDCG@10 = 0.6831
```

**Isto não resolve o F17-03/F20-01 — reconfirma o viés já documentado, não o remove.** Os
candidatos de cada consulta continuam vindo de correspondência por substring de
título/empresa (mesmo critério do `like`); o revisor só confirmou humanamente quais desses
candidatos *já encontrados pelo `like`* são relevantes — não havia candidatos gerados por
full-text/descrição para o revisor julgar. Por construção, quase todo item confirmado como
relevante É um match de título, então `like` recall@10 ≈ 1 não é surpresa nem evidência a
favor do `like` sobre o full-text; é a mesma limitação do relatório original
(`docs/pesquisas/eval-search-f17-03.md`), agora com números atualizados. As duas únicas
consultas que teriam dado ao full-text uma chance real (`kubernetes`, `frontend`, sem
candidato por título) continuam sem gabarito porque exigem leitura de descrição completa,
fora do escopo desta sessão. **F17-03/F20-01 permanece "Em revisão"**, não `Done` — falta um
gabarito com candidatos vindos de full-text (não só de título) para medir a comparação que
o card realmente pede.
