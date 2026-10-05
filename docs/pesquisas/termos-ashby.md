# Revisão de termos — Ashby

**Data:** 2026-10-05
**Veredito:** **viável com ressalvas.** A API é documentada pela Ashby para quem hospeda a
própria página de carreiras, responde sem autenticação e não declara limite nem restrição;
a documentação não diz que terceiros possam agregar, e esta revisão não encontrou
autorização nem proibição explícita para isso.
**Escopo:** o tipo de ATS inteiro (qualquer board `jobs.ashbyhq.com/<slug>`); não precisa
ser repetida por board. Motivo: a API, o `robots.txt` e os termos lidos são os mesmos para
todos os boards, e o dado de cada board é publicado pelo próprio cliente da Ashby na
página pública dele. Ver "Escopo" abaixo para o que isso não cobre.

## Histórico

Fontes do tipo `ashby` já estavam habilitadas antes deste arquivo existir, com base na
decisão 6 da [SPEC 48](../48-spec-mais-vagas.md) ("dentro dos termos já revisados por tipo
de ATS") e na documentação oficial citada em `PUBLIC_ENDPOINT_REFERENCES["ashby"]`
(`probing.py`). Não havia um `termos-ashby.md`. Este arquivo registra essa base depois do
fato, em 2026-10-05, quando mais fontes Ashby estão sendo habilitadas. O dono do projeto
aceitou a base por tipo de ATS na mesma data; esta revisão documenta a evidência, não cria
uma autorização que não existia.

## O que o coletor chama

Lido em `src/opportunity_radar/acquisition/ashby.py` (2026-10-05):

- `GET https://api.ashbyhq.com/posting-api/job-board/<slug>?includeCompensation=true`.
  Uma requisição por execução (o endpoint não pagina); sem corpo.
- Nenhuma autenticação, chave nem cookie é enviado. O único cabeçalho opcional é o
  condicional (`If-None-Match`/`If-Modified-Since`, quando há `ETag`/`Last-Modified`
  guardado da execução anterior).
- O cliente HTTP (`httpx.AsyncClient`) não define `User-Agent` próprio: sai o padrão do
  `httpx`. Os coletores de Ashby, Greenhouse e Lever, ao contrário do Hacker News e da
  descoberta (`OpportunityRadarDiscoveryBot/1.0`), não se identificam. Ver "Condições".
- Timeout de 5 s para conectar e 15 s para ler. Retentativa: até 2, com espera vinda da
  política da fonte (padrão 1 s, teto 30 s), respeitando `Retry-After` em 429.
  401, 403 e 404 não são retentados.
- Ritmo: o ritmo por fonte vem de `rate_limit_policy`. As fontes importadas
  (`scripts/import_research_catalog.py`) levam `requests_per_second: 0.2` (uma requisição
  a cada 5 s), `max_retries: 2` e `max_retry_delay_seconds: 30`. Como o coletor faz uma
  chamada por execução, a política limita sobretudo a cadência entre execuções e entre
  fontes do mesmo host.
- Campos guardados: `jobUrl` (vira a URL da vaga), `title`, `location`, `descriptionPlain`,
  `publishedAt`; no `metadata`: `applyUrl`, `secondaryLocations`, `department`, `team`,
  `isRemote`, `workplaceType`, `employmentType`, `compensation`. A resposta bruta da vaga
  fica em `raw_payload`. Não há dado de candidato.
- Referência citada pelo código: `PUBLIC_ENDPOINT_REFERENCES["ashby"]` =
  `https://developers.ashbyhq.com/docs/public-job-posting-api`.

## Documentação da Ashby (lida em 2026-10-05)

URL: https://developers.ashbyhq.com/docs/public-job-posting-api, título "Ashby Job
Postings API", carregada por HTTP (a página também existe em Markdown, sufixo `.md`).

Lido:

- "This API allows you to get data for all currently published Job Postings for your
  organization. If you host your own careers page, you can use this data to populate it."
- Pedido de exemplo: `curl https://api.ashbyhq.com/posting-api/job-board/{JOB_BOARD_NAME}?includeCompensation=true`,
  sem credencial. A página não pede chave de API.
- "Your request must include your organization's Ashby jobs page name in the URL path."
- Campo `isListed`: "Should this job be listed in the list of postings on your job
  board. If false, this listing should only be available via direct link."
- Campo `publishedAt`: "ISO DateTime when the job was last published".
- Fecha com: "If there is additional data you'd like to have included in this response
  but currently is not, please reach out to us and let us know."

Não aparece na página: afirmação expressa de que a API é "pública" ou "não autenticada"
(só o exemplo sem credencial); limite de requisições; política de cache; restrição de uso
ou de redistribuição. A ausência não é permissão: a página fala em "your organization",
isto é, no cliente que publica as próprias vagas, e não trata de terceiros.

Segunda página lida, "Dedicated Partner Job Feeds"
(https://developers.ashbyhq.com/docs/dedicated-partner-job-feeds.md): "Ashby can
provision a dedicated job posting feed for a partner interested in ingesting job
postings. Once the integration is live, Ashby customers can opt-in to sharing their jobs
with the partner's service by enabling the partner's integration in the Admin section of
the Ashby app." Esse é o caminho formal que a Ashby oferece a quem quer ingerir vagas de
vários clientes, com adesão do cliente. Este projeto não usa esse caminho: lê a API
pública por board. Isso é a principal ressalva do veredito.

Medido hoje, uma chamada ao board `notion`: HTTP 200 sem autenticação; cabeçalhos
`cache-control: public, max-age=60, stale-while-revalidate=60` e `etag: W/"job-board:..."`;
nenhum cabeçalho de limite de taxa (`RateLimit-*`, `X-RateLimit-*`) nem `Retry-After`.

## robots.txt (verificado em 2026-10-05)

- `https://api.ashbyhq.com/robots.txt`: HTTP 401, corpo `Unauthorized`. O host da API não
  publica `robots.txt`. Pelo RFC 9309, um 4xx significa "sem restrições declaradas"; a
  função `robots_allows()` do projeto, mais conservadora, trata 401/403 como bloqueio. Isso
  só importa para a descoberta, não para o coletor, que não consulta `robots.txt`.
- `https://jobs.ashbyhq.com/robots.txt` (host público dos boards):
  `User-Agent: *` com `Disallow: /meeting/`, `Disallow: /b/`, `Disallow: /api/`. O
  coletor não lê páginas desse host; só devolve o link `jobUrl` ao usuário.
- `https://www.ashbyhq.com/robots.txt`: `User-agent: *` / `Allow: /`.

## Termos (lidos em 2026-10-05)

URL: https://www.ashbyhq.com/resources/terms ("Ashby Customer Terms of Service", última
atualização 2025-09-29, 32 mil caracteres lidos). É o contrato com o cliente que compra
a plataforma. A busca no texto não achou menção a leitura automatizada, "scraping",
"crawl", "robot" nem à API pública de vagas. As cláusulas de uso aceitável (5.1) obrigam o
cliente, por exemplo "(f) attempt to circumvent or disable any security or other
technological features of the Service" e "(g) use the Service in any manner that could
interfere with, disrupt, negatively affect ... or overburden ... the Service". Elas
descrevem deveres do cliente e não tratam de terceiros que leem o board público; não
foram tratadas como proibição nem como autorização. Não localizei termos de uso do site
público `jobs.ashbyhq.com` voltados a visitantes (a página `Terms and Policies` lista o
contrato do cliente, a política de privacidade e termos de recursos de IA e de parceiros de
design; não li esses dois últimos). Resultado: sem cláusula sobre automação de leitura de
boards públicos por terceiros em nenhum documento lido.

## O que o projeto faz para ficar dentro disso

Regras do próprio projeto, citadas:

- `docs/17-fontes-coletores.md` §2 e §4: o coletor não cria `Opportunity`, não calcula
  score, não decide elegibilidade, "não" inicia candidatura nem envia mensagem; fontes que
  exigem "contornar autenticação", "imitar sessão privada", "quebrar captcha", "ignorar
  bloqueios" ou "ocultar identidade do cliente" "não fazem parte da estratégia". §48: a
  nova fonte só entra com "termos e forma de acesso ... compatíveis com o uso" e "rate
  limit configurável".
- `README.md` e `docs/47-arquitetura-atual.md`: uso pessoal, local, sem multiusuário e sem
  autenticação; a porta publicada escuta só em `127.0.0.1`. Nada é republicado.
- SPEC 48, decisão 6: ativação com probe e `TERMS_REVIEWED=1` por fonte
  (`terms_reviewed` em `scripts/enable_sources.py`).
- Na prática: cada vaga guarda a URL original (`jobUrl`) e o `applyUrl`; o projeto não
  submete candidatura; uma requisição por execução e por board; `Retry-After` respeitado;
  `ETag`/`Last-Modified` reaproveitados para evitar baixar o board inteiro quando nada
  mudou.
- Remoção: não encontrei nos documentos do projeto uma regra escrita sobre atender a um
  pedido de remoção de dados por parte de um board ou da Ashby. Não determinado. O que
  fecharia: uma linha no runbook dizendo que, a pedido da Ashby ou da empresa, a fonte é
  desabilitada (`enabled=false`) e as vagas dela deixam de ser exibidas.

## Escopo

A revisão cobre o tipo `ashby` como um todo, e não precisa ser repetida por board, porque o
que se revisou (endpoint, `robots.txt`, termos) é comum a todos. Fica de fora: uma empresa
específica que declare, na própria página de carreiras, restrição à reutilização de suas
vagas, ou que peça remoção. Isso é tratado por fonte, no momento em que ocorrer. A
revisão também não cobre o caminho "Dedicated Partner Job Feeds", que não é usado.

## Condições para operar

- Manter uma requisição por board por execução, ritmo da fonte em 0,2 req/s e 2 retentativas.
- Respeitar `Retry-After` e 429; em 401/403/404 não insistir.
- Sem autenticação, sem candidatura automática, sem leitura de `jobs.ashbyhq.com`.
- Mostrar sempre o link para a vaga original.
- Desabilitar a fonte se a Ashby ou a empresa pedir.
- Recomendado, não feito: identificar o coletor com `User-Agent` próprio, como já fazem a
  descoberta e o Hacker News. Hoje sai o `User-Agent` padrão do `httpx`.

## O que ainda poderia mudar o veredito

- Resposta da Ashby (`integrations@ashbyhq.com`, contato indicado na página de feeds) sobre
  se a leitura da API pública por um agregador pessoal é aceita: não determinado; só uma
  resposta escrita fecharia.
- Limite de taxa: não documentado; não determinado.

## Referências (todas acessadas em 2026-10-05)

- https://developers.ashbyhq.com/docs/public-job-posting-api
- https://developers.ashbyhq.com/docs/dedicated-partner-job-feeds.md
- https://developers.ashbyhq.com/llms.txt (índice da documentação)
- https://api.ashbyhq.com/robots.txt (HTTP 401)
- https://jobs.ashbyhq.com/robots.txt
- https://www.ashbyhq.com/robots.txt
- https://www.ashbyhq.com/resources/terms
- `docs/17-fontes-coletores.md`, `docs/48-spec-mais-vagas.md` (decisão 6),
  `docs/pesquisas/termos-workable.md` (precedente interno).
