# Revisão de termos — Workday (F20-28)

**Data:** 2026-09-26
**Card:** [F20-28 — Coletor Workday](../44-roadmap-fase-20/fase-20/f20-28-coletor-workday.md)
**Decisão:** viável, com as mesmas guardas já aplicadas ao Greenhouse/Lever/Ashby
(robots.txt, ritmo de requisição, sem autenticação, sem dado de candidato).

## O que existe

Toda vaga pública de uma empresa que usa Workday para recrutamento fica em um site de
carreiras hospedado sob o domínio `<tenant>.<pod>.myworkdayjobs.com/<site>` (ex.:
`nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite`). Esse site é uma SPA que busca
os dados de um endpoint JSON **não documentado publicamente pela Workday**, mas comum a
todo tenant, porque é o mesmo bundle de frontend que a Workday distribui para todos os
clientes:

- Listagem paginada: `POST https://<tenant>.<pod>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs`
  — corpo JSON com `limit`, `offset` e `searchText` opcional; resposta com `total` e uma
  lista `jobPostings` (título, localização, data, `externalPath`).
- Detalhe por vaga: `GET https://<tenant>.<pod>.myworkdayjobs.com/wday/cxs/<tenant>/<site><externalPath>`
  — retorna a descrição completa (`jobDescription`, geralmente HTML), `jobReqId`, e por
  vezes `bulletFields`.

Não há chave de API, autenticação ou cabeçalho especial: é o mesmo request que o
navegador do candidato faz ao carregar a página. Não existe portal de desenvolvedor nem
documento de termos específico para esse endpoint — ele é implícito ao site público, como
o Lever "postings API" (`docs/pesquisas/README-pesquisa.md` já usa esse endpoint sem
documentação oficial como precedente aceito no projeto).

## robots.txt (verificado)

Cada tenant publica seu próprio `robots.txt` em
`https://<tenant>.<pod>.myworkdayjobs.com/robots.txt`. Exemplo real conferido
(`nvidia.wd5.myworkdayjobs.com/robots.txt`):

```
Sitemap: https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/siteMap.xml
User-agent: *
Allow: /NVIDIAExternalCareerSite/
Disallow: /talentcommunity/
Disallow: /refreshFacet/
```

O padrão observado em múltiplos tenants: `Allow` cobre o próprio site de carreiras
(onde o candidato humano navega, e de onde o SPA chama `/wday/cxs/...`), e `Disallow`
cobre apenas `/talentcommunity/` (comunidade de talentos, fora de escopo) e
`/refreshFacet/` (endpoint de filtro de UI, não usado pelo coletor). O endpoint
`/wday/cxs/<tenant>/<site>/jobs` que o coletor chama não aparece em nenhum `Disallow`
observado — é o próprio backend do caminho permitido, não um caminho paralelo a ele.

Assim como `LeverCollector`/`GreenhouseCollector`/`AshbyCollector`, o coletor não repete
uma checagem de `robots.txt` a cada chamada: essa verificação é papel da descoberta
(`discovery.py`, F20-27), que já roda `robots_allows()` antes de a página virar
`CompanySource`, e do cadastro de empresa (F20-25), que homologa a fonte antes de
habilitar. Um tenant cujo `robots.txt` proibisse o site de carreiras nunca teria chegado
a virar fonte proposta. Se um tenant específico vier a restringir `/wday/cxs/` no futuro,
isso é uma regressão a pegar na homologação daquele tenant (probe falha com
`SOURCE_FORBIDDEN`), não um caso a resolver no coletor.

## Termos de uso da Workday (workday.com)

Os [termos de site da Workday](https://www.workday.com/en-us/legal/site-terms.html)
proíbem ignorar `robots.txt`, mineração de dados/scraping, e uso de aplicações que
interajam com "our Sites" sem consentimento prévio por escrito. Esses termos, pelo texto,
se aplicam a `www.workday.com` e páginas associadas — não mencionam explicitamente os
sites de carreiras `*.myworkdayjobs.com`, que são propriedade/conteúdo de cada empresa
cliente (tenant), hospedados na infraestrutura da Workday. Não há um termo de uso
publicado, específico e único, para o conjunto de sites de carreiras.

Isso deixa o mesmo tipo de zona intermediária que já existe para o Lever (`postings-api`
sem termo dedicado, referenciado por `probing.py:27` como
`https://github.com/lever/postings-api`): endpoint público, sem autenticação, cujo
contrato de uso aceitável vem do `robots.txt` do site (o instrumento que o próprio host
usa para declarar o que pode ser lido por automação) e das práticas do projeto (uma
requisição por vez, identificação por `User-Agent`, sem dado de candidato).

## Taxa e boas maneiras

Não há cabeçalho de limite de taxa documentado. O coletor segue o mesmo contrato de rede
dos demais (`CollectionNetworkPolicy`): retentativa com backoff, respeito a
`Retry-After` quando presente em um 429, e o ritmo imposto pela política de rede do
chamador — nenhuma chamada em paralelo, um tenant/site por vez.

## Atribuição

Nenhuma atribuição é exigida pelo `robots.txt` nem pelos termos de `workday.com`. O
coletor preserva a URL original da vaga (`externalPath` resolvido) em `CollectedItem.url`,
como os demais coletores.

## Decisão

**Viável.** O coletor:

- só chama `/wday/cxs/<tenant>/<site>/jobs` e o detalhe por vaga — nunca
  `/talentcommunity/` nem `/refreshFacet/`;
- não autentica, não lê nem envia dado de candidato;
- identifica um board por dois valores, `tenant` e `site` — decisão desta revisão:
  codificar como `"<tenant>/<site>"` em `company_reference` (um único campo de
  identificador, no formato que `IDENTIFIER_KEYS`/`SUPPORTED_ATS` já esperam — um valor
  de texto por fonte), em vez de introduzir um segundo campo de configuração. O pod
  (`wd5`, `wd1`, …) é um terceiro valor, que a Workday não expõe de forma previsível a
  partir do tenant; ele entra como `api_region` (reaproveitando o campo que o Lever já
  usa para uma finalidade parecida — identificar qual host chamar), com o pod real
  confirmado por empresa no cadastro. Nome de campo final:
  `tenant_identifier` = `"<tenant>/<site>"` (conforme a tabela do card).

## Referências

- https://www.workday.com/en-us/legal/site-terms.html
- `https://<tenant>.<pod>.myworkdayjobs.com/robots.txt` (verificado com `nvidia.wd5`)
- Precedente interno: `probing.py` já referencia o Lever `postings-api` (endpoint público
  sem termo dedicado) como `PUBLIC_ENDPOINT_REFERENCES["lever"]`.
