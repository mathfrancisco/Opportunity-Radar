# Auditoria das 186 empresas do Notion

Data: 11/09/2026. Todas as 186 linhas do banco mestre estão representadas abaixo. Resultado: 2 APIs JSON, 40 ATS identificados, 108 páginas de carreiras, 4 páginas dinâmicas, 1 redirecionamento a revisar e 31 acessos pendentes.

## Como interpretar

- **API JSON confirmada:** o endpoint retornou JSON de vagas durante a pesquisa. Ainda falta homologar o coletor no ambiente local.
- **ATS identificado:** há evidência de uma plataforma de recrutamento vinculada à empresa. Isso não certifica uma API funcionando.
- **Página de carreiras:** conteúdo da página foi consultável; extração completa, paginação e tecnologia ainda precisam ser verificadas.
- **Página dinâmica:** resposta insuficiente para validar as vagas; exige inspeção adicional.
- **Acesso pendente:** a ferramenta de pesquisa não conseguiu consultar o endereço. Não prova que o site está fora do ar ou que a automação é impossível.
- **Redirecionamento:** o destino exige revisão de identidade ou deixou de ser uma página de carreiras.

“Direto” inclui o portal oficial e o board de recrutamento contratado pela própria empresa. Não implica que a vaga aceite residência no Brasil, contratação PJ ou trabalho remoto internacional. Essas condições devem ser verificadas em cada anúncio. Nenhum coletor local foi homologado e os termos de cada fonte ainda não foram revisados.

## Resultado por empresa

| Empresa | Situação | ATS | Fonte consultada | Evidência / observação |
| --- | --- | --- | --- | --- |
| Accenture | ATS identificado | Workday | [Carreiras](https://www.accenture.com/us-en/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Adevinta Spain | Acesso pendente | — | [Carreiras](https://www.adevinta.com/careers/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Adyen | Página de carreiras | — | [Carreiras](https://careers.adyen.com/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Agentero | ATS identificado | Factorial | [Carreiras](https://agentero.factorialhr.com/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Airbyte | Página de carreiras | — | [Carreiras](https://airbyte.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Airtable | Página dinâmica; revisar | — | [Carreiras](https://www.airtable.com/careers) | Página retornou conteúdo insuficiente/iframe/JavaScript. Listagem não validada. |
| Aiven | Página de carreiras | — | [Carreiras](https://aiven.io/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Akamai | Página de carreiras | — | [Carreiras](https://www.akamai.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Algolia | Página de carreiras | — | [Carreiras](https://www.algolia.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Amadeus | ATS identificado | Workday | [Carreiras](https://jobs.amadeus.com/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Amenitiz | Acesso pendente | — | [Carreiras](https://careers.amenitiz.com/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Anthropic | Página de carreiras | — | [Carreiras](https://www.anthropic.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Anysphere (Cursor) | Página de carreiras | — | [Carreiras](https://cursor.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Apollo GraphQL | Página de carreiras | — | [Carreiras](https://www.apollographql.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| AssemblyAI | ATS identificado | Greenhouse | [Carreiras](https://www.assemblyai.com/careers) | [Board](https://job-boards.greenhouse.io/assemblyai). Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Automattic | Página de carreiras | — | [Carreiras](https://automattic.com/work-with-us/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Babel | Acesso pendente | — | [Carreiras](https://babelgroup.com/talento/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| BairesDev | Acesso pendente | — | [Carreiras](https://jobs.bairesdev.com/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| BBVA | Acesso pendente | — | [Carreiras](https://careers.bbva.com/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Bird | Página de carreiras | — | [Carreiras](https://bird.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Brex | Página de carreiras | — | [Carreiras](https://www.brex.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Buffer | Página de carreiras | — | [Carreiras](https://buffer.com/journey) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Buildkite | ATS identificado | Greenhouse | [Carreiras](https://buildkite.com/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Cabify | Acesso pendente | — | [Carreiras](https://cabify.com/en/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Camunda | Página de carreiras | — | [Carreiras](https://camunda.com/career/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Canonical | Página de carreiras | — | [Carreiras](https://canonical.com/careers/all) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Capgemini | Página de carreiras | — | [Carreiras](https://www.capgemini.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Cartesia | ATS identificado | Ashby | [Carreiras](https://cartesia.ai/careers) | [Board](https://jobs.ashbyhq.com/cartesia). Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Carto | Página de carreiras | — | [Carreiras](https://carto.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Celonis | Página de carreiras | — | [Carreiras](https://www.celonis.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Chainguard | Página de carreiras | — | [Carreiras](https://www.chainguard.dev/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Checkout.com | Página de carreiras | — | [Carreiras](https://www.checkout.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Clarity AI | Página de carreiras | — | [Carreiras](https://clarity.ai/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| ClickHouse | Página de carreiras | — | [Carreiras](https://clickhouse.com/company/careers) | Página consultável; link Ashby encontrado refere-se à Langfuse, não confirma ATS de todas as vagas ClickHouse. |
| Cloudflare | Página de carreiras | — | [Carreiras](https://www.cloudflare.com/careers/jobs/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Cockroach Labs | Página de carreiras | — | [Carreiras](https://www.cockroachlabs.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Cognigy | Página de carreiras | — | [Carreiras](https://www.cognigy.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Cognition | ATS identificado | Ashby | [Carreiras](https://cognition.ai/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Contentful | Página de carreiras | — | [Carreiras](https://www.contentful.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Customer.io | ATS identificado | Greenhouse | [Carreiras](https://customer.io/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Databricks | Página de carreiras | — | [Carreiras](https://www.databricks.com/company/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Datadog | Página de carreiras | — | [Carreiras](https://careers.datadoghq.com/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Dataiku | ATS identificado | Greenhouse | [Carreiras](https://www.dataiku.com/careers/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| dbt Labs | Página de carreiras | — | [Carreiras](https://www.getdbt.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Deel | Página de carreiras | — | [Carreiras](https://www.deel.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Deepgram | ATS identificado | Ashby | [Carreiras](https://deepgram.com/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| DeepL | ATS identificado | Ashby | [Carreiras](https://www.deepl.com/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| DigitalOcean | Página de carreiras | — | [Carreiras](https://www.digitalocean.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Docker | Página de carreiras | — | [Carreiras](https://www.docker.com/career-openings/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Doist | Página de carreiras | — | [Carreiras](https://doist.com/careers) | Página redirecionou para Todoist; manter alias. |
| DuckDuckGo | Página de carreiras | — | [Carreiras](https://duckduckgo.com/hiring) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| eDreams ODIGEO | Página de carreiras | — | [Carreiras](https://www.edreamsodigeocareers.com/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Elastic | Página de carreiras | — | [Carreiras](https://www.elastic.co/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| ElevenLabs | Página de carreiras | — | [Carreiras](https://elevenlabs.io/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Endava | Acesso pendente | — | [Carreiras](https://careers.endava.com/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| EPAM Systems | Página de carreiras | — | [Carreiras](https://www.epam.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Factorial | ATS identificado | Factorial | [Carreiras](https://careers.factorialhr.com/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Fastly | Página de carreiras | — | [Carreiras](https://www.fastly.com/about/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Fever | Página de carreiras | — | [Carreiras](https://careers.feverup.com/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Figma | ATS identificado | Greenhouse | [Carreiras](https://www.figma.com/careers/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Freepik | Acesso pendente | — | [Carreiras](https://www.freepik.com/company/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| GFT | Página de carreiras | — | [Carreiras](https://jobs.gft.com/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| GitBook | ATS identificado | Ashby | [Carreiras](https://www.gitbook.com/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| GitGuardian | Página de carreiras | — | [Carreiras](https://www.gitguardian.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| GitLab | Página de carreiras | — | [Carreiras](https://about.gitlab.com/jobs/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Glean | Página de carreiras | — | [Carreiras](https://www.glean.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Globant | Página de carreiras | — | [Carreiras](https://career.globant.com/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Glovo | Página de carreiras | — | [Carreiras](https://jobs.glovoapp.com/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| GMV | Acesso pendente | — | [Carreiras](https://www.gmv.com/en/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| GoCardless | ATS identificado | Greenhouse | [Carreiras](https://gocardless.com/about/careers/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Grafana Labs | ATS identificado | Greenhouse | [Carreiras](https://grafana.com/careers/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Harvey | Página de carreiras | — | [Carreiras](https://www.harvey.ai/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Hebbia | ATS identificado | Ashby | [Carreiras](https://www.hebbia.com/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Help Scout | ATS identificado | Ashby | [Carreiras](https://www.helpscout.com/company/careers/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Holded | Acesso pendente | — | [Carreiras](https://www.holded.com/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Honeycomb | Página de carreiras | — | [Carreiras](https://www.honeycomb.io/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Hotjar | Acesso pendente | — | [Carreiras](https://careers.hotjar.com/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| HubSpot | Página de carreiras | — | [Carreiras](https://www.hubspot.com/careers/jobs) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Hugging Face | ATS identificado | Workable | [Carreiras](https://huggingface.co/careers) | [Board](https://apply.workable.com/huggingface). Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| idealista | Acesso pendente | — | [Carreiras](https://www.idealista.com/empleo/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Infobip | ATS identificado | Workday | [Carreiras](https://www.infobip.com/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Izertis | Página de carreiras | — | [Carreiras](https://www.izertis.com/en/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| JetBrains | Página dinâmica; revisar | — | [Carreiras](https://www.jetbrains.com/careers/jobs/) | Página retornou conteúdo insuficiente/iframe/JavaScript. Listagem não validada. |
| Jobandtalent | Página de carreiras | — | [Carreiras](https://www.jobandtalent.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Klarna | Página de carreiras | — | [Carreiras](https://www.klarna.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Klaviyo | Acesso pendente | — | [Carreiras](https://careers.klaviyo.com/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| LangChain | Página de carreiras | — | [Carreiras](https://www.langchain.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Langfuse | ATS identificado | Ashby | [Carreiras](https://langfuse.com/careers) | Página de carreira própria com Ashby; revisar relação com ClickHouse para deduplicação. |
| LaunchDarkly | ATS identificado | Greenhouse | [Carreiras](https://launchdarkly.com/careers/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Linear | Página de carreiras | — | [Carreiras](https://linear.app/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Lingokids | ATS identificado | Teamtailor | [Carreiras](https://jobs.lingokids.com/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| LiveKit | ATS identificado | Ashby | [Carreiras](https://livekit.io/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| LlamaIndex | Página de carreiras | — | [Carreiras](https://www.llamaindex.ai/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Lodgify | Página de carreiras | — | [Carreiras](https://www.lodgify.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Lokalise | Página de carreiras | — | [Carreiras](https://lokalise.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Lumenalta | Acesso pendente | — | [Carreiras](https://lumenalta.com/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Mambu | Página de carreiras | — | [Carreiras](https://mambu.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Mews | Página de carreiras | — | [Carreiras](https://www.mews.com/en/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Minsait | Página de carreiras | — | [Carreiras](https://www.minsait.com/en/talent) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Mistral AI | ATS identificado | Ashby | [Carreiras](https://mistral.ai/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Modal | Página dinâmica; revisar | — | [Carreiras](https://modal.com/careers) | Página retornou conteúdo insuficiente/iframe/JavaScript. Listagem não validada. |
| Mollie | Página de carreiras | — | [Carreiras](https://jobs.mollie.com/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| MongoDB | Página de carreiras | — | [Carreiras](https://www.mongodb.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| N26 | Página de carreiras | — | [Carreiras](https://n26.com/en-eu/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| n8n | ATS identificado | Ashby | [Carreiras](https://n8n.io/careers/) | [Board](https://jobs.ashbyhq.com/n8n). Página descreve Europa, Reino Unido e às vezes EUA; não assumir elegibilidade Brasil. |
| Nearsure | Página de carreiras | — | [Carreiras](https://www.nearsure.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Notion | ATS identificado | Ashby | [Carreiras](https://www.notion.com/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| NTT DATA | ATS identificado | Workday | [Carreiras](https://careers.nttdata.com/) | URL consultada levou ao portal de Global Data Centers; não cobre necessariamente NTT DATA Brasil/Consulting. |
| NVIDIA | Página de carreiras | — | [Carreiras](https://www.nvidia.com/en-us/about-nvidia/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| OpenAI | Página de carreiras | — | [Carreiras](https://openai.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Ophelos | Acesso pendente | — | [Carreiras](https://www.ophelos.com/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| OVHcloud | Página de carreiras | — | [Carreiras](https://careers.ovhcloud.com/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Oyster | Página de carreiras | — | [Carreiras](https://www.oysterhr.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Paradigma Digital | Página de carreiras | — | [Carreiras](https://www.paradigmadigital.com/empleo/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Parloa | Página de carreiras | — | [Carreiras](https://www.parloa.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Perplexity | Acesso pendente | — | [Carreiras](https://www.perplexity.ai/hub/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Pinecone | ATS identificado | Ashby | [Carreiras](https://www.pinecone.io/careers/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Plaid | Página de carreiras | — | [Carreiras](https://plaid.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Plain Concepts | ATS identificado | Workable | [Carreiras](https://www.plainconcepts.com/careers/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Pleo | ATS identificado | Ashby | [Carreiras](https://www.pleo.io/en/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| PolyAI | Página de carreiras | — | [Carreiras](https://poly.ai/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| PostHog | Página de carreiras | — | [Carreiras](https://posthog.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Proxify | Página de carreiras | — | [Carreiras](https://career.proxify.io/) | Separar vagas internas de cadastro/alocação de desenvolvedores. |
| Pulumi | Página de carreiras | — | [Carreiras](https://www.pulumi.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Qdrant | Acesso pendente | — | [Carreiras](https://qdrant.tech/careers/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Qonto | ATS identificado | Lever | [Carreiras](https://qonto.com/en/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Ramp | Página de carreiras | — | [Carreiras](https://ramp.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Rapid7 | Página de carreiras | — | [Carreiras](https://careers.rapid7.com/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| receeve | Redirecionamento; revisar | — | [Carreiras](https://www.receeve.com/careers) | Redirecionou à página de produto Receive da InDebted; não confirmou listagem de vagas. |
| Red Points | Acesso pendente | — | [Carreiras](https://www.redpoints.com/careers/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Remote | Página de carreiras | — | [Carreiras](https://remote.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Replicate | Página de carreiras | — | [Carreiras](https://replicate.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Replit | ATS identificado | Ashby | [Carreiras](https://replit.com/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Retell AI | Página de carreiras | — | [Carreiras](https://www.retellai.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Retool | Página de carreiras | — | [Carreiras](https://retool.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Revelo | Acesso pendente | — | [Carreiras](https://www.revelo.com/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| RevenueCat | API JSON confirmada | Ashby | [Carreiras](https://www.revenuecat.com/careers/) | [JSON](https://api.ashbyhq.com/posting-api/job-board/revenuecat). Endpoint público retornou JSON de vagas nesta consulta; coletor local ainda não homologado. |
| Revolut | Página de carreiras | — | [Carreiras](https://www.revolut.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Rippling | Acesso pendente | — | [Carreiras](https://www.rippling.com/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Sanity | Página de carreiras | — | [Carreiras](https://www.sanity.io/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Santander | Página de carreiras | — | [Carreiras](https://www.santander.com/en/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Scaleway | ATS identificado | Lever | [Carreiras](https://www.scaleway.com/en/careers/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Seedtag | ATS identificado | Teamtailor | [Carreiras](https://jobs.seedtag.com/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Sentry | Página de carreiras | — | [Carreiras](https://sentry.io/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Sequra | Acesso pendente | — | [Carreiras](https://careers.sequra.com/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Sierra | ATS identificado | Ashby | [Carreiras](https://sierra.ai/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Signaturit | Acesso pendente | — | [Carreiras](https://careers.signaturit.com/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Sinch | Página de carreiras | — | [Carreiras](https://sinch.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Sngular | Acesso pendente | — | [Carreiras](https://www.sngular.com/careers/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Snyk | Página de carreiras | — | [Carreiras](https://snyk.io/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Sonar | ATS identificado | Lever | [Carreiras](https://www.sonarsource.com/company/careers/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Sourcegraph | Acesso pendente | — | [Carreiras](https://sourcegraph.com/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Speechmatics | Página de carreiras | — | [Carreiras](https://www.speechmatics.com/company/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Spendesk | ATS identificado | Teamtailor | [Carreiras](https://www.spendesk.com/careers/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Storyblok | Página de carreiras | — | [Carreiras](https://www.storyblok.com/jobs) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Stripe | Página de carreiras | — | [Carreiras](https://stripe.com/jobs) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| SumUp | Página de carreiras | — | [Carreiras](https://www.sumup.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Supabase | API JSON confirmada | Ashby | [Carreiras](https://supabase.com/careers) | [JSON](https://api.ashbyhq.com/posting-api/job-board/supabase). Endpoint público retornou JSON de vagas nesta consulta; coletor local ainda não homologado. |
| SUSE | Página de carreiras | — | [Carreiras](https://jobs.suse.com/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Synthflow | Acesso pendente | — | [Carreiras](https://synthflow.ai/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Tailscale | Página de carreiras | — | [Carreiras](https://tailscale.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Telefónica | Página de carreiras | — | [Carreiras](https://jobs.telefonica.com/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Telnyx | Acesso pendente | — | [Carreiras](https://telnyx.com/company/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Temporal | Página de carreiras | — | [Carreiras](https://temporal.io/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| TestGorilla | ATS identificado | Ashby | [Carreiras](https://www.testgorilla.com/careers/) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| Thoughtworks | Página de carreiras | — | [Carreiras](https://www.thoughtworks.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Timescale | Página de carreiras | — | [Carreiras](https://www.timescale.com/careers) | Página retornou marca Tiger Data; manter alias e revisar identidade. |
| Toast | Página de carreiras | — | [Carreiras](https://careers.toasttab.com/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Toggl | Página de carreiras | — | [Carreiras](https://toggl.com/jobs/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Toptal | Página de carreiras | — | [Carreiras](https://www.toptal.com/careers) | Carreiras corporativas e oportunidades para freelancers são funis distintos. |
| Trade Republic | Acesso pendente | — | [Carreiras](https://traderepublic.com/en-de/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| TravelPerk | Página de carreiras | — | [Carreiras](https://www.travelperk.com/careers/) | Página retornou marca Perk; manter alias. |
| TrueLayer | Página de carreiras | — | [Carreiras](https://truelayer.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Twilio | Página dinâmica; revisar | — | [Carreiras](https://www.twilio.com/en-us/company/jobs) | Página retornou conteúdo insuficiente/iframe/JavaScript. Listagem não validada. |
| Typeform | Página de carreiras | — | [Carreiras](https://www.typeform.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Vapi | ATS identificado | Ashby | [Carreiras](https://vapi.ai/careers) | Página/redirect contém evidência de ATS; endpoint, permissão e parser precisam de homologação. |
| VASS | Acesso pendente | — | [Carreiras](https://vasscompany.com/en/careers/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Vercel | Página de carreiras | — | [Carreiras](https://vercel.com/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Voiceflow | Acesso pendente | — | [Carreiras](https://www.voiceflow.com/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Vonage | Página de carreiras | — | [Carreiras](https://www.vonage.com/careers/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Wallbox | Acesso pendente | — | [Carreiras](https://wallbox.com/en_us/careers) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Weaviate | Página de carreiras | — | [Carreiras](https://weaviate.io/company/careers) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Wikimedia Foundation | Página de carreiras | — | [Carreiras](https://wikimediafoundation.org/about/jobs/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Wise | Página de carreiras | — | [Carreiras](https://wise.jobs/) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |
| Writer | Acesso pendente | — | [Carreiras](https://writer.com/careers/) | Consulta não retornou conteúdo verificável. Não significa ausência de vagas ou impossibilidade de integração. |
| Zapier | Página de carreiras | — | [Carreiras](https://zapier.com/jobs) | Página de carreira com conteúdo consultável. API/ATS e completude da lista não confirmados. |

Prioridades e fontes originais estão preservadas em [catalogo-fontes.json](catalogo-fontes.json).
