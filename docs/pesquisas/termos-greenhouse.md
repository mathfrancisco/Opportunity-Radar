# Revisão de termos — Greenhouse

**Data:** 2026-10-05
**Veredito:** **viável com ressalvas.** A documentação oficial diz que os dados do Job
Board são públicos e que os GET não exigem autenticação, e o `robots.txt` do host da API
só bloqueia `/embed/`; a mesma documentação descreve o uso como o de "your company's"
páginas de carreiras e não diz nada sobre terceiros, limites ou redistribuição.
**Escopo:** o tipo de ATS inteiro (qualquer `board_token`); não precisa ser repetida por
board. Motivo: documentação, API e `robots.txt` são comuns a todos os boards, e cada board
é a página pública de vagas que a própria empresa publica. Ver "Escopo" abaixo.

## Histórico

Fontes do tipo `greenhouse` já estavam habilitadas antes deste arquivo existir, com base
na decisão 6 da [SPEC 48](../48-spec-mais-vagas.md) ("dentro dos termos já revisados por
tipo de ATS") e na documentação oficial citada em `PUBLIC_ENDPOINT_REFERENCES["greenhouse"]`
(`probing.py`). Não havia um `termos-greenhouse.md`. Este arquivo registra essa base
depois do fato, em 2026-10-05, quando mais fontes Greenhouse estão sendo habilitadas. O
dono do projeto aceitou a base por tipo de ATS na mesma data; esta revisão documenta a
evidência, não cria uma autorização que não existia.

## O que o coletor chama

Lido em `src/opportunity_radar/acquisition/greenhouse.py` (2026-10-05):

- `GET https://boards-api.greenhouse.io/v1/boards/<board_token>/jobs?content=true`
  (`DEFAULT_BASE_URL`, configurável por `greenhouse_base_url` para testes). Uma requisição
  por execução: a lista traz tudo e `meta.total` é lido como contagem anunciada.
- Nenhuma autenticação, chave nem cookie. O endpoint de candidatura (`POST .../jobs/<id>`,
  que exige Basic Auth) nunca é chamado. Cabeçalhos condicionais
  (`If-None-Match`/`If-Modified-Since`) só quando há `ETag`/`Last-Modified` guardado.
- Sem `User-Agent` próprio: sai o padrão do `httpx` (mesma observação de Ashby e Lever).
- Timeout de 5 s para conectar e 15 s para ler; até 2 retentativas, com `Retry-After`
  respeitado em 429, espera mínima entre tentativas pela política da fonte
  (`_wait_for_minimum_interval`). 401, 403 e 404 não são retentados.
- Ritmo: fontes importadas levam `requests_per_second: 0.2`, `max_retries: 2`,
  `max_retry_delay_seconds: 30` (`scripts/import_research_catalog.py`).
- Campos guardados: `absolute_url` (vira a URL da vaga), `id`, `title`,
  `location.name`, `content` (descrição em HTML), `updated_at`; no `metadata`:
  `internal_job_id`, `requisition_id`, `language`, `departments`, `offices`, `metadata`.
  O `updated_at` é data de última modificação e por decisão do F20-61 não vira
  `published_at`. Nenhum dado de candidato.
- Referência citada pelo código: `PUBLIC_ENDPOINT_REFERENCES["greenhouse"]` =
  `https://docs.greenhouse.io/job-board.html`.

## Documentação da Greenhouse (lida em 2026-10-05)

URL pedida: https://developers.greenhouse.io/job-board.html. Respondeu 301 para
https://docs.greenhouse.io/job-board.html, a URL que o código já cita. Título da página:
"Job Board API | Greenhouse".

Lido:

- "With our Job Board API, you will have easy access to a simple JSON representation of
  your company's offices, departments, and published jobs. Since we give you access to the
  raw data, you can build careers pages with a unique look and feel, construct
  department-level pages, and more!"
- "Job Board data is publicly available, so authentication is not required for any GET
  endpoints. Only the application submission endpoint ( POST
  https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{id} ) requires Basic
  Auth."
- Com `?content=true`, cada vaga inclui `content` com a descrição. A resposta de lista traz
  `jobs[]` (`id`, `internal_job_id`, `title`, `updated_at`, `requisition_id`,
  `location.name`, `absolute_url`, `language`, `metadata`) e `meta.total`.
- A página também documenta JSONP (parâmetro `callback`).

Não aparece na página: limite de taxa, política de cache, restrição de uso ou de
redistribuição, nem menção a agregadores ou a terceiros. A frase "publicly available" é a
declaração mais clara de qualquer um dos três vendors sobre o acesso, mas a finalidade
descrita é a de a empresa montar a própria página.

Medido hoje, uma chamada ao board `netlify`: HTTP 200 sem autenticação; `etag: W/"..."`,
`cache-control: max-age=0, private, must-revalidate`; nenhum cabeçalho de limite de taxa
nem `Retry-After`; resposta servida pela CloudFront.

## robots.txt (verificado em 2026-10-05)

- `https://boards-api.greenhouse.io/robots.txt` (host da API): `User-agent: *` /
  `Disallow: /embed/`. O caminho `/v1/boards/...` que o coletor chama não está bloqueado.
- `https://boards.greenhouse.io/robots.txt`: o mesmo conteúdo.
- `https://job-boards.greenhouse.io/robots.txt` (host das páginas atuais dos boards): sem
  regra ativa (as linhas de bloqueio estão comentadas).
- `https://www.greenhouse.com/robots.txt`: `Disallow: /*_page=`, só o site comercial.

O coletor não consulta `robots.txt`; a descoberta (`robots_allows()`) o faz antes de uma
página virar fonte proposta.

## Termos (lidos em 2026-10-05)

- https://www.greenhouse.com/legal (centro legal): lista Privacy policy, Bias audit
  statement, Cookie notice, CCPA/CPRA for candidates, Master subscription agreement, Data
  processing addendum, Subprocessors in use e Sustainability statement. Não há "termos de
  uso do site" nem "termos da API do Job Board" separados; os links `/legal/terms-of-use`
  e `/legal/website-terms-of-use` responderam 404.
- https://www.greenhouse.com/master-subscription-agreement (contrato do cliente, 48 mil
  caracteres lidos): a busca por "scrap", "crawl", "robot", "automated", "Job Board",
  "career site" e "careers page" não achou nada. A única ocorrência de "public" é a
  exclusão padrão da definição de informação confidencial ("generally known to the
  public"). O contrato obriga o cliente e não trata de terceiros que leem as vagas.
- A página de documentação não faz referência a termos de uso da API do Job Board.

Resultado: nenhum documento lido proíbe nem autoriza a leitura automatizada de boards
públicos por terceiros. Os Termos de Uso do site `greenhouse.com` (se existirem em outro
endereço) não foram localizados: não determinado; o que fecharia seria o texto desses
termos ou uma resposta da Greenhouse.

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
- Na prática: guarda `absolute_url` e mostra o link da vaga original; não chama o endpoint
  de candidatura; uma requisição por board por execução; 0,2 req/s; `Retry-After`
  respeitado; `ETag` reaproveitado.
- Remoção: não há, nos documentos do projeto, regra escrita sobre atender a um pedido de
  remoção. Não determinado. O que fecharia: uma linha no runbook (desabilitar a fonte e
  ocultar as vagas dela a pedido da Greenhouse ou da empresa).

## Escopo

A revisão cobre o tipo `greenhouse` como um todo, porque o que se revisou é comum a todos
os boards. Fica de fora: uma empresa que restrinja a reutilização de suas vagas na própria
página de carreiras, ou que peça remoção; isso é tratado por fonte. Também não cobre o
`board_token` quando ele é só um palpite: um token que devolve 404 ou zero vagas não é
fonte (o caso do Langfuse, em `f50-fontes-2026-10-05.md`, é de Ashby, mas a regra vale
aqui).

## Condições para operar

- Uma requisição por board por execução; 0,2 req/s e 2 retentativas por fonte.
- Só `GET /v1/boards/<token>/jobs`; nunca o POST de candidatura.
- Respeitar `Retry-After` e 429; em 401/403/404 não insistir.
- Mostrar sempre o link para a vaga original; desabilitar a fonte a pedido.
- Recomendado, não feito: `User-Agent` próprio no coletor.

## O que ainda poderia mudar o veredito

- Termos de uso do site público da Greenhouse, se localizados: não determinado.
- Limite de taxa: não documentado; não determinado.

## Referências (todas acessadas em 2026-10-05)

- https://developers.greenhouse.io/job-board.html (301) e https://docs.greenhouse.io/job-board.html
- https://boards-api.greenhouse.io/robots.txt
- https://boards.greenhouse.io/robots.txt
- https://job-boards.greenhouse.io/robots.txt
- https://www.greenhouse.com/robots.txt
- https://www.greenhouse.com/legal
- https://www.greenhouse.com/master-subscription-agreement
- `docs/17-fontes-coletores.md`, `docs/48-spec-mais-vagas.md` (decisão 6).
