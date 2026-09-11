# Empresas adicionais ao banco mestre

Data: 11/09/2026. Foram investigadas 36 candidatas ausentes do banco mestre de 186 linhas. Isso não garante ausência nas listas textuais antigas do Notion. A seleção amplia fontes de tecnologia e serviços, sem presumir elegibilidade para Brasil ou Europa em todas as vagas.

## Como interpretar

- **API JSON confirmada:** o endpoint retornou JSON de vagas durante a pesquisa. Ainda falta homologar o coletor no ambiente local.
- **ATS identificado:** há evidência de uma plataforma de recrutamento vinculada à empresa. Isso não certifica uma API funcionando.
- **Página de carreiras:** conteúdo da página foi consultável; extração completa, paginação e tecnologia ainda precisam ser verificadas.
- **Página dinâmica:** resposta insuficiente para validar as vagas; exige inspeção adicional.
- **Acesso pendente:** a ferramenta de pesquisa não conseguiu consultar o endereço. Não prova que o site está fora do ar ou que a automação é impossível.
- **Redirecionamento:** o destino exige revisão de identidade ou deixou de ser uma página de carreiras.

“Direto” inclui o portal oficial e o board de recrutamento contratado pela própria empresa. Não implica que a vaga aceite residência no Brasil, contratação PJ ou trabalho remoto internacional. Essas condições devem ser verificadas em cada anúncio. Nenhum coletor local foi homologado e os termos de cada fonte ainda não foram revisados.

## 20 empresas com evidências de fonte direta

| Empresa | Situação | ATS | Fonte consultada | Evidência / observação |
| --- | --- | --- | --- | --- |
| CI&T | ATS identificado | Lever | [Carreiras](https://ciandt.com/us/en-us/careers) | [Board](https://jobs.lever.co/ciandt). Board público da CI&T retornou listagem de vagas com Brasil, homeoffice e outras localidades. Portal institucional havia falhado. |
| X-Team | Página de carreiras | — | [Carreiras](https://x-team.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Ubiminds | Página de carreiras | — | [Carreiras](https://ubiminds.com/en-us/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Asaas | ATS identificado | Gupy | [Carreiras](https://asaas.gupy.io/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Nubank | ATS identificado | Ashby | [Carreiras](https://international.nubank.com.br/careers/) | [Board](https://jobs.ashbyhq.com/nubank). Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Spotify | API JSON confirmada | Lever | [Carreiras](https://www.lifeatspotify.com/jobs) | [JSON](https://api.lever.co/v0/postings/spotify?mode=json). Endpoint público retornou JSON de vagas nesta consulta; coletor local ainda não homologado. |
| Netlify | ATS identificado | Greenhouse | [Carreiras](https://www.netlify.com/careers/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Render | API JSON confirmada | Ashby | [Carreiras](https://render.com/careers) | [JSON](https://api.ashbyhq.com/posting-api/job-board/render). Várias vagas observadas indicam EUA/Canadá; facilidade de coleta não garante Brasil. |
| Railway | Página de carreiras | — | [Carreiras](https://railway.com/careers) | Página própria consultável; integração de listagem ainda precisa de inspeção. |
| Resend | Página de carreiras | — | [Carreiras](https://resend.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| WorkOS | API JSON confirmada | Ashby | [Carreiras](https://workos.com/careers) | [JSON](https://api.ashbyhq.com/posting-api/job-board/workos). Endpoint público retornou JSON de vagas nesta consulta; coletor local ainda não homologado. |
| Clerk | ATS identificado | Ashby | [Carreiras](https://clerk.com/careers) | [Board](https://jobs.ashbyhq.com/Clerk). Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Firecrawl | ATS identificado | Ashby | [Carreiras](https://www.firecrawl.dev/careers) | [Board](https://jobs.ashbyhq.com/firecrawl). Várias vagas de engenharia indicam San Francisco; algumas funções mencionam Americas. |
| Browserbase | ATS identificado | Ashby | [Carreiras](https://www.browserbase.com/careers) | [Board](https://jobs.ashbyhq.com/browserbase). Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Inngest | ATS identificado | Ashby | [Carreiras](https://www.inngest.com/careers) | [Board](https://jobs.ashbyhq.com/inngest). Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Trigger.dev | ATS identificado | Ashby | [Carreiras](https://trigger.dev/careers) | [Board](https://jobs.ashbyhq.com/triggerdev). Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Windmill | Página de carreiras | — | [Carreiras](https://www.windmill.dev/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| CircleCI | Página de carreiras | — | [Carreiras](https://circleci.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Ashby | Página de carreiras | — | [Carreiras](https://www.ashbyhq.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Kit | ATS identificado | Ashby | [Carreiras](https://kit.com/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |

## 16 candidatas ainda pendentes

Estas empresas não entram na contagem de 20 fontes consultáveis. Uma falha de acesso nesta pesquisa não deve ser tratada como impossibilidade permanente.

| Empresa | Situação | ATS | Fonte consultada | Evidência / observação |
| --- | --- | --- | --- | --- |
| Jobsity | Acesso pendente | — | [Carreiras](https://www.jobsity.com/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Blip | Acesso pendente | — | [Carreiras](https://www.blip.ai/carreiras/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Zenvia | Acesso pendente | — | [Carreiras](https://www.zenvia.com/carreiras/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Conta Azul | Acesso pendente | — | [Carreiras](https://contaazul.gupy.io/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| QuintoAndar | Acesso pendente | — | [Carreiras](https://careers.quintoandar.com.br/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Hotmart | Acesso pendente | — | [Carreiras](https://careers.hotmart.com/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Wellhub | Acesso pendente | — | [Carreiras](https://wellhub.com/en-us/careers/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Neon | Redirecionamento; revisar | — | [Carreiras](https://neon.com/careers) | Redirecionou para carreiras Databricks, já presente na base; evitar dupla contagem de vagas. |
| Turso | Acesso pendente | — | [Carreiras](https://turso.tech/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| CrewAI | Acesso pendente | — | [Carreiras](https://www.crewai.com/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Resemble AI | Acesso pendente | — | [Carreiras](https://www.resemble.ai/careers/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Daily | Acesso pendente | — | [Carreiras](https://www.daily.co/careers/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| SafetyWing | Acesso pendente | — | [Carreiras](https://safetywing.com/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| G2i | Acesso pendente | — | [Carreiras](https://www.g2i.co/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| InDebted | Redirecionamento; revisar | — | [Carreiras](https://www.indebted.co/careers/) | Redirecionou a About; necessário localizar board de vagas. |
| Duckbill | Acesso pendente | — | [Carreiras](https://jobs.ashbyhq.com/duckbill) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |

