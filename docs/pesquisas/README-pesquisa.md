# Pesquisa de fontes diretas — Opportunity Radar

Consulta: 11 de setembro de 2026. Escopo: banco mestre de 186 empresas do Notion e 36 candidatas adicionais. Esta é uma triagem documentada de fontes, não a certificação de 222 integrações.

## Resultado

| Evidência | Base Notion | Adicionais |
| --- | ---: | ---: |
| API JSON confirmada | 2 | 3 |
| ATS identificado | 40 | 10 |
| Página de carreiras consultável | 108 | 7 |
| Página dinâmica para revisar | 4 | 0 |
| Redirecionamento para revisar | 1 | 2 |
| Acesso pendente | 31 | 14 |
| Total | 186 | 36 |

Das 186 empresas, **150 têm evidência de página de carreiras, ATS ou API**. Outras quatro retornaram páginas dinâmicas e uma redirecionou para um produto: por isso o total de 155 respostas não deve ser apresentado como 155 fontes prontas. As 31 restantes precisam de nova investigação. Entre as adicionais, 20 têm evidência de fonte direta consultável.

## Documentos

- [Auditoria das 186 empresas](auditoria-186-empresas.md): resultado individual e links.
- [Empresas adicionais](empresas-adicionais.md): 36 candidatas, separando as 20 com evidências das pendências.
- [Plano de integração local](plano-integracao-local.md): conectores, etapas e critérios de aceite.
- Os quatro documentos preservam os 222 registros levantados; a exportação estruturada para importação será gerada somente depois da revisão de identidades e aliases.

## Fonte oficial do catálogo do MVP

O fluxo normal usa `scripts/import_research_catalog.py` para ler diretamente as
tabelas da auditoria e das empresas adicionais. A prioridade operacional é:

```text
API JSON confirmada > ATS identificado > página de carreiras
```

Páginas dinâmicas, redirecionamentos e acessos pendentes são importados no
backlog, sem ativar coleta. O export do Notion deixou de ser uma entrada
necessária para o MVP. As 222 linhas resultam em 220 identidades porque
Neon/Databricks e receeve/InDebted são reconciliadas como aliases.

## Origem e método

A [página compartilhada](https://app.notion.com/p/Tier-List-de-Empresas-Remoto-Europa-e-Espanha-3a64da369be6813b9a99d8e722e17cd9?source=copy_link) referencia o [banco mestre](https://app.notion.com/p/cc358c8b93a44004bdc6e08c1644c5e3). Foram extraídas exatamente 186 linhas, preservando empresa, prioridade e Fonte. O campo Fonte estava vazio em 156 registros; 20 apontavam para fontes secundárias e 10 para fontes oficiais. Portanto, Fonte não poderia ser usado diretamente como cadastro de conectores.

Foram propostos e consultados endereços de carreiras por empresa, inspecionados redirecionamentos e vínculos com plataformas de recrutamento. As fontes adicionais foram comparadas com os nomes do banco mestre. “Adicional” significa ausente desse banco; algumas podem constar nas listas textuais antigas do Notion. Marcas adquiridas também podem compartilhar vagas, exigindo deduplicação.

Foram sondados 16 endpoints: cinco retornaram JSON consultável. Não houve teste de paginação completa, execução recorrente, comparação exaustiva entre API e portal nem homologação dos coletores em Docker. Falhas da ferramenta de consulta permanecem inconclusivas. Os endereços e resultados são uma fotografia da data informada.

## Como interpretar

- **API JSON confirmada:** o endpoint retornou JSON de vagas durante a pesquisa. Ainda falta homologar o coletor no ambiente local.
- **ATS identificado:** há evidência de uma plataforma de recrutamento vinculada à empresa. Isso não certifica uma API funcionando.
- **Página de carreiras:** conteúdo da página foi consultável; extração completa, paginação e tecnologia ainda precisam ser verificadas.
- **Página dinâmica:** resposta insuficiente para validar as vagas; exige inspeção adicional.
- **Acesso pendente:** a ferramenta de pesquisa não conseguiu consultar o endereço. Não prova que o site está fora do ar ou que a automação é impossível.
- **Redirecionamento:** o destino exige revisão de identidade ou deixou de ser uma página de carreiras.

“Direto” inclui o portal oficial e o board de recrutamento contratado pela própria empresa. Não implica que a vaga aceite residência no Brasil, contratação PJ ou trabalho remoto internacional. Essas condições devem ser verificadas em cada anúncio. Os adaptadores Ashby, Lever e Greenhouse já possuem parser e testes com fixture; a homologação contra os boards reais e a revisão dos termos continuam pendentes antes da ativação.

## Cinco endpoints confirmados

- **RevenueCat (Ashby):** [página oficial](https://www.revenuecat.com/careers/) e [endpoint que retornou JSON](https://api.ashbyhq.com/posting-api/job-board/revenuecat).
- **Supabase (Ashby):** [página oficial](https://supabase.com/careers) e [endpoint que retornou JSON](https://api.ashbyhq.com/posting-api/job-board/supabase).
- **Spotify (Lever):** [página oficial](https://www.lifeatspotify.com/jobs) e [endpoint que retornou JSON](https://api.lever.co/v0/postings/spotify?mode=json).
- **Render (Ashby):** [página oficial](https://render.com/careers) e [endpoint que retornou JSON](https://api.ashbyhq.com/posting-api/job-board/render).
- **WorkOS (Ashby):** [página oficial](https://workos.com/careers) e [endpoint que retornou JSON](https://api.ashbyhq.com/posting-api/job-board/workos).

## Correções relevantes

- receeve redirecionou para uma página de produto da InDebted; não deve virar coletor de vagas sem resolver a identidade empregadora.
- Neon redirecionou para Databricks, que já está no banco mestre. Evitar fontes duplicadas.
- Timescale passou a Tiger Data; TravelPerk a Perk; Doist redireciona para Todoist. Manter aliases e revisar vínculo antes de importar.
- A presença de um link Ashby de Langfuse na página ClickHouse não foi tratada como confirmação do ATS da ClickHouse.
- A página encontrada de NTT DATA tem escopo de data centers; não representa necessariamente todas as empresas do grupo.
- Render apresentou vagas com restrições a EUA/Canadá, e Firecrawl apresentou várias posições em San Francisco. São fontes tecnicamente interessantes, mas a compatibilidade geográfica exige filtros.

## Decisão para o projeto

A pesquisa sustenta começar por um conjunto pequeno de fontes oficiais e expandir por plataforma compartilhada. O próximo marco é coletar e reconciliar vagas dos cinco endpoints confirmados, somando o board Lever da CI&T para avaliar oportunidades no Brasil. Não é necessário manter Notion após importar e revisar empresas e aliases na dashboard. O sistema pode executar localmente; a coleta continuará dependendo de acesso à internet aos sites externos.

Na importação operacional, os quatro endpoints Ashby confirmados, o endpoint
Lever do Spotify e o board Greenhouse identificado da AssemblyAI viram
definições desabilitadas. A definição da AssemblyAI conserva o estado
`ats_identified`; CI&T e empresas Greenhouse sem token explícito permanecem no
catálogo até a homologação do endpoint. Páginas dinâmicas, redirecionamentos e
acessos pendentes continuam apenas como backlog; o importador não cria
coletores executáveis para esses casos.

O importador também cria uma definição Remotive independente do catálogo de
empresas para cumprir o caso de feed/query do MVP. Ela permanece desabilitada e
`unverified`; sua existência não altera a contagem dos cinco endpoints JSON
confirmados por esta pesquisa.
