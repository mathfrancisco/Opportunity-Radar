# Revisão de termos — Lever

**Data:** 2026-10-05
**Veredito:** **viável**, com as condições abaixo. É o tipo com a evidência mais direta dos
três (Ashby, Greenhouse, Lever): a documentação oficial diz que as vagas publicadas são
"publicly viewable" e que "may be scraped by third parties", e o `robots.txt` do host da
API permite tudo com `Crawl-delay: 1`. Continua sem haver autorização contratual
expressa; é um aviso na documentação, não uma licença.
**Escopo:** o tipo de ATS inteiro, nas duas instâncias (global `api.lever.co` e EU
`api.eu.lever.co`); não precisa ser repetida por board. Motivo: documentação e
`robots.txt` valem para toda a API de postings. Ver "Escopo" abaixo.

## Histórico

Fontes do tipo `lever` já estavam habilitadas antes deste arquivo existir, com base na
decisão 6 da [SPEC 48](../48-spec-mais-vagas.md) ("dentro dos termos já revisados por tipo
de ATS") e na documentação citada em `PUBLIC_ENDPOINT_REFERENCES["lever"]` (`probing.py`).
Outras revisões do projeto (`termos-workday.md`, `termos-workable.md`) já tratavam o Lever
como precedente ("postings API sem termo dedicado"), mas nunca houve um `termos-lever.md`.
Este arquivo registra essa base depois do fato, em 2026-10-05, quando mais fontes Lever
estão sendo habilitadas. O dono do projeto aceitou a base por tipo de ATS na mesma data;
esta revisão documenta a evidência, não cria uma autorização que não existia.

## O que o coletor chama

Lido em `src/opportunity_radar/acquisition/lever.py` (2026-10-05):

- `GET https://api.lever.co/v0/postings/<site>?mode=json&skip=<n>&limit=<n>`, ou o mesmo
  em `api.eu.lever.co` quando a fonte está marcada como instância EU (`api_region`).
  Pagina por `skip`/`limit` com páginas de 100 e para ao receber uma página mais curta
  que o limite (sinal de fim), ou ao atingir o teto de itens; uma página repetida é erro.
  Um board de 250 vagas custa 3 requisições por execução.
- Nenhuma autenticação, chave nem cookie. O `POST` de candidatura da API nunca é chamado.
  Cabeçalhos condicionais só na primeira página, quando há `ETag`/`Last-Modified` guardado.
- Sem `User-Agent` próprio: sai o padrão do `httpx` (mesma observação de Ashby e
  Greenhouse).
- Timeout de 5 s para conectar e 15 s para ler; até 2 retentativas, `Retry-After`
  respeitado em 429; espera mínima entre requisições pela política da fonte. 401, 403 e
  404 não são retentados.
- Ritmo: fontes importadas levam `requests_per_second: 0.2` (uma requisição a cada 5 s),
  `max_retries: 2`, `max_retry_delay_seconds: 30`. Isso é mais lento que o
  `Crawl-delay: 1` do `robots.txt` da Lever.
- Campos guardados: `id` (identificador externo), `hostedUrl` (URL da vaga), `text`
  (título), `categories.location`, `descriptionPlain`, `createdAt` (data de criação, em
  milissegundos, usada como `published_at`); no `metadata`: `categories`, `country`,
  `applyUrl`, `workplaceType`, `salaryRange`. Resposta bruta em `raw_payload`. Nenhum
  dado de candidato.
- Referência citada pelo código: `PUBLIC_ENDPOINT_REFERENCES["lever"]` =
  `https://github.com/lever/postings-api`.

## Documentação da Lever (lida em 2026-10-05)

URL: https://github.com/lever/postings-api (README lido em
https://raw.githubusercontent.com/lever/postings-api/master/README.md). Título "Lever
Postings API". Consultada também por um resumo automático da página; as citações abaixo
são do texto bruto do README.

Lido:

- "This API is designed to help you create a job site."
- "Note that all job postings in the `published` state are publicly viewable. These jobs
  may be scraped by third parties. All other jobs are completely hidden from the jobs API."
- "You do not need to use this API to get started with Lever job postings. All published
  job postings are also automatically viewable via your Lever-hosted job site (e.g.
  `https://jobs.lever.co/leverdemo`)."
- "GET /v0/postings/SITE?skip=X&limit=Y"; parâmetros `mode` (JSON, iframe ou HTML), `skip`
  ("skip N from the start") e `limit` ("only return at most N results").
- "All API methods are exposed under our postings base url (global / EU). The API is not
  available via unencrypted HTTP."
- Limite documentado só para candidaturas: "Lever will return a `429` status code (`TOO
  MANY REQUESTS`) if your custom job site issues more than 2 application POST requests per
  second. This rate limit may also be changed without warning". A leitura de vagas (GET)
  não tem limite documentado.
- Lista do que a API não faz: entre outros, "Support cross-origin HTTP requests from sites
  outside of your company's domains/subdomains" (restrição de CORS para navegadores; o
  coletor não é um navegador e não usa CORS).

A frase "may be scraped by third parties" é um aviso da Lever sobre o conteúdo; não é uma
licença nem uma regra de uso, e não fala de redistribuição nem de cache. Não aparece:
política de cache nem restrição de redistribuição.

Medido hoje, uma chamada ao board `spotify` (`limit=5`): HTTP 200 sem autenticação;
`ETag: W/"..."`; nenhum cabeçalho de limite de taxa nem `Retry-After`.

## robots.txt (verificado em 2026-10-05)

- `https://api.lever.co/robots.txt`: `User-agent: *` / `Allow: /` / `Crawl-delay: 1`.
- `https://api.eu.lever.co/robots.txt`: o mesmo.
- `https://jobs.lever.co/robots.txt` (páginas públicas dos boards): o mesmo.
- `https://www.lever.co/robots.txt`: `Allow: /` com `Disallow: /studio/`, `/api/`, `/404`,
  `/500`; é o site comercial.

`Crawl-delay: 1` pede, no máximo, uma requisição por segundo. O coletor, a 0,2 req/s, cumpre
com folga.

## Termos (lidos em 2026-10-05)

- https://www.lever.co/legal/terms-of-service ("Terms of Service", última atualização
  2023-08-25, Lever, Inc., hoje parte da Employ Inc.; o rodapé o chama de "Terms of
  Use"): contrato de assinatura do cliente. A busca no texto não achou "scrap", "crawl",
  "robot" nem "automated". A cláusula 1.2 obriga o cliente: não "reverse engineer,
  decompile, disassemble or otherwise attempt to discover the source code ... of the
  Services, Documentation or data related to the Services" nem "make available the
  Services or Documentation to any third party". É dever do cliente, não de quem lê o
  board público, e não foi tratada como proibição nem como autorização.
- https://www.lever.co/legal (Legal Center): lista Terms of Service, Professional
  Services Agreement, DMCA e Contest Rules; a Employ Inc. publica o resto em
  https://www.employinc.com/legal/ (página curta, sem termos de uso do site público de
  vagas). Não localizei termos específicos para `jobs.lever.co` voltados a visitantes.

Resultado: nenhum termo lido trata de leitura automatizada de boards públicos por
terceiros; a única declaração que trata disso é o aviso da documentação ("may be scraped
by third parties").

## O que o projeto faz para ficar dentro disso

Regras do próprio projeto, citadas:

- `docs/17-fontes-coletores.md` §2 e §4: o coletor não cria `Opportunity`, não decide
  elegibilidade, não inicia candidatura nem envia mensagem; fontes que exigem contornar
  autenticação, quebrar captcha, ignorar bloqueios ou ocultar identidade "não fazem parte
  da estratégia". §48: "termos e forma de acesso são compatíveis com o uso" e "rate limit
  configurável" são itens obrigatórios.
- `README.md` e `docs/47-arquitetura-atual.md`: uso pessoal, local, sem multiusuário;
  porta só em `127.0.0.1`; nada é republicado.
- SPEC 48, decisão 6: ativação com probe e `TERMS_REVIEWED=1` por fonte.
- Na prática: guarda `hostedUrl` e mostra o link da vaga original; não usa o POST de
  candidatura; 0,2 req/s (abaixo do `Crawl-delay` de 1 s); `Retry-After` respeitado;
  `ETag` reaproveitado.
- Remoção: não há, nos documentos do projeto, regra escrita sobre atender a um pedido de
  remoção. Não determinado. O que fecharia: uma linha no runbook (desabilitar a fonte e
  ocultar as vagas dela a pedido da Lever ou da empresa).

## Escopo

A revisão cobre o tipo `lever` (global e EU) como um todo, porque o que se revisou é comum
a todos os boards. Fica de fora: uma empresa que restrinja a reutilização de suas vagas na
própria página de carreiras ou peça remoção; isso é tratado por fonte. Também fica de fora
um board de grupo compartilhado entre várias marcas (por exemplo, um board Lever de um
grupo que publica vagas de empresas diferentes): a fonte vira a empresa dona do board, e a
atribuição à marca certa é decisão de cadastro, não de termos.

## Condições para operar

- Ritmo da fonte em 0,2 req/s ou mais lento; nunca abaixo do `Crawl-delay` de 1 s.
- Respeitar `Retry-After` e 429; em 401/403/404 não insistir.
- Só `GET /v0/postings/<site>`; nunca o POST de candidatura.
- Mostrar sempre o link para a vaga original; desabilitar a fonte a pedido.
- Recomendado, não feito: `User-Agent` próprio no coletor.

## O que ainda poderia mudar o veredito

- Termos de uso do site público `jobs.lever.co`, se localizados: não determinado.
- Limite de taxa para a leitura (GET): não documentado; não determinado.

## Referências (todas acessadas em 2026-10-05)

- https://github.com/lever/postings-api (README)
- https://raw.githubusercontent.com/lever/postings-api/master/README.md
- https://api.lever.co/robots.txt, https://api.eu.lever.co/robots.txt,
  https://jobs.lever.co/robots.txt, https://www.lever.co/robots.txt
- https://www.lever.co/legal/terms-of-service
- https://www.lever.co/legal
- https://www.employinc.com/legal/
- `docs/17-fontes-coletores.md`, `docs/48-spec-mais-vagas.md` (decisão 6),
  `docs/pesquisas/termos-workday.md` e `termos-workable.md` (precedente interno).
