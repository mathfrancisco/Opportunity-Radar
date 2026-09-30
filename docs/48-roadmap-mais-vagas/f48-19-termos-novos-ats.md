# F48-19 — Revisão de termos de novos ATS e agregadores (V20.4)

Parte de documentação do card F48-19 (a lista `FORBIDDEN_PLATFORMS` já foi entregue). Revisão
feita em 2026-09-30, só por leitura de páginas oficiais; nenhum coletor foi escrito e nenhum
endpoint de vagas foi sondado para coleta. Cláusulas só são citadas onde a página foi lida; onde
a página falhou (403/404) o documento diz isso e o veredito é "a confirmar".

## Resultado

| Candidato | Documento | Endpoint público documentado | Veredito |
| --- | --- | --- | --- |
| SmartRecruiters | [termos-smartrecruiters.md](../pesquisas/termos-smartrecruiters.md) | Sim (`/v1/companies/{id}/postings`; segurança "sem autenticação" listada) | a confirmar (termos da API não lidos) |
| BambooHR | [termos-bamboohr.md](../pesquisas/termos-bamboohr.md) | Não (só API autenticada) | não viável (cláusula contra robôs/scraping) |
| Recruitee | [termos-recruitee.md](../pesquisas/termos-recruitee.md) | Sim (`{empresa}.recruitee.com/api/offers/`, sem auth) | a confirmar (termos 404) |
| inhire | [termos-inhire.md](../pesquisas/termos-inhire.md) | Não confirmado (docs deram 403) | a confirmar |
| Workday, detalhe da vaga | [termos-workday-detalhe.md](../pesquisas/termos-workday-detalhe.md) | Não (endpoint interno do SPA) | a confirmar |
| Remote OK | [termos-remoteok.md](../pesquisas/termos-remoteok.md) | Sim (`/api`, sem doc dedicada) | viável, com atribuição (link com follow) |
| Jobicy | [termos-jobicy.md](../pesquisas/termos-jobicy.md) | Sim (`/api/v2/remote-jobs`, sem chave) | viável (crédito; máx. 1 consulta/hora) |
| Himalayas | [termos-himalayas.md](../pesquisas/termos-himalayas.md) | Sim (`/jobs/api`, sem chave) | viável (link visível; 429; dado diário) |

Arbeitnow foi lido (`arbeitnow.com/blog/job-board-api`) mas não virou documento: o texto não traz
termos, taxa nem atribuição e o conteúdo é reagregado de outros ATS; seria "a confirmar".

## Páginas que não puderam ser lidas

- `docs.inhire.com.br/**` (4 páginas): HTTP 403.
- `recruitee.com/legal/terms-of-service`: 404. `remoteok.com/terms`: 404.
- `jobi.cy/apidocs` (Jobicy): 403. `arbeitnow.com/api` mostrou só a listagem de vagas.
- Termos de desenvolvedor da SmartRecruiters: não localizados.
- Termos gerais de himalayas.app: não lidos.

## Consequência para o F48-20

Há três agregadores "viáveis" (Remote OK, Jobicy, Himalayas), todos com atribuição obrigatória.
Nenhum ATS novo está "viável" ainda: Recruitee e SmartRecruiters são os mais próximos e dependem
de ler os termos que faltam. A escolha do primeiro coletor fica com o mantenedor.
