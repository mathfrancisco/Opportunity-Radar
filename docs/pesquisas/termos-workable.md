# Revisão de termos — Workable (F20-30)

**Data:** 2026-09-26
**Card:** [F20-30 — Coletor Workable](../44-roadmap-fase-20/fase-20/f20-30-coletor-workable.md)
**Decisão:** viável, com as mesmas guardas já aplicadas ao Greenhouse/Lever/Ashby/Workday
(robots.txt, ritmo de requisição, sem autenticação, sem dado de candidato).

## O que existe

Toda empresa que usa Workable para recrutamento tem uma conta pública identificada por um
subdomínio/slug (ex.: `acme` em `apply.workable.com/acme`). A página pública de vagas
dessa conta é alimentada por um widget JSON, sem autenticação, chamado pelo próprio
navegador do candidato:

- Listagem: `GET https://apply.workable.com/api/v1/widget/accounts/<account>?details=true`
  (a mesma resposta também é servida em `https://www.workable.com/api/accounts/<account>?details=true`,
  que redireciona para a primeira). Sem `details=true`, a resposta traz só título e
  metadados básicos; com `details=true`, cada vaga inclui `description`/`full_description`
  (HTML), cidade/estado/país e tipo de emprego.
- Resposta: objeto único com uma lista `jobs`; cada item tem `id` (ou `shortcode`),
  `title`, `url` (link canônico da vaga), `location` (`location_str`, `city`,
  `state_code`, `country_name`, `telecommuting`, `workplace_type`), `description`,
  `full_description`, `published_on`/`created_at`, `experience` e `state`.
- **Sem paginação**: o widget devolve todas as vagas ativas da conta em uma única
  resposta — não há `page`/`offset`/`limit` documentado nem observado. O coletor trata a
  resposta inteira como uma página só (ver `discover` abaixo); "board vazio" só é
  aceito quando a resposta é de fato uma lista vazia, nunca como resultado de erro HTTP
  ou schema alterado.
- Endpoints companheiros, não usados por este coletor: `/api/accounts/<account>/locations`
  e `/api/accounts/<account>/departments` (facetas de filtro da UI, não vagas).

Não há chave de API, autenticação nem cabeçalho especial — é o mesmo request que o
navegador do candidato faz ao abrir a página pública de vagas da conta.

## robots.txt (verificado)

`https://apply.workable.com/robots.txt`:

```
User-agent: *
Content-Signal: search=yes, ai-input=yes, ai-train=no
Disallow:
```

`Disallow` vazio: nenhum caminho é bloqueado, incluindo `/api/v1/widget/accounts/`.
`https://www.workable.com/robots.txt` bloqueia apenas áreas administrativas
(`/userpasswordresets`, `/admin`, `/auth/google`, `/j/`) — não bloqueia
`/api/accounts/`. O `Content-Signal` proíbe uso para treino de modelo de IA
(`ai-train=no`); isso não se aplica aqui, pois o coletor lê dados de vaga para o produto
(matching de oportunidades), não para treinar modelo.

## Termos de uso da Workable (workable.com/terms)

Os termos de `www.workable.com` regem o uso do site pelo cliente Workable (a empresa que
contrata) e não têm uma cláusula específica proibindo scraping, automação ou coleta de
dados do widget público de vagas. A cláusula mais próxima (seção 4.5) proíbe o cliente
"fazer algo que possa prejudicar, interferir ou causar dano à operação dos Serviços" —
uma restrição genérica de abuso de serviço, não uma proibição de leitura do widget
público por terceiros. Os termos, pelo texto, regem `www.workable.com` como site — não
mencionam explicitamente o subdomínio público `apply.workable.com` nem o endpoint do
widget, que é conteúdo do cliente (a conta de vagas), hospedado na infraestrutura da
Workable.

Isso é a mesma zona intermediária já registrada para Lever e Workday: endpoint público,
sem autenticação, sem termo dedicado, cujo contrato de uso aceitável vem do `robots.txt`
(que permite explicitamente, com `Disallow` vazio) e das práticas do projeto (uma
requisição por vez, identificação por `User-Agent`, sem dado de candidato).

## Taxa e boas maneiras

Não há cabeçalho de limite de taxa documentado publicamente. O coletor segue o mesmo
contrato de rede dos demais (`CollectionNetworkPolicy`): retentativa com backoff, respeito
a `Retry-After` quando presente em um 429, e o ritmo imposto pela política de rede do
chamador — nenhuma chamada em paralelo, uma conta por vez.

## Atribuição

Nenhuma atribuição é exigida pelo `robots.txt` nem pelos termos de `workable.com`. O
coletor preserva a URL canônica da vaga (campo `url` do payload) em
`CollectedItem.url`, como os demais coletores.

## Decisão

**Viável.** O coletor:

- só chama `GET /api/v1/widget/accounts/<account>?details=true` em
  `apply.workable.com` — nunca `/locations` nem `/departments`, que são facetas de UI,
  não vagas;
- não autentica, não lê nem envia dado de candidato;
- identifica uma conta por um único valor de texto — decisão desta revisão: reaproveitar
  `company_reference` (o mesmo campo que `IDENTIFIER_KEYS`/`SUPPORTED_ATS` já esperam)
  para o slug da conta (`account_identifier` na tabela do card e no formulário, mesmo
  valor);
- trata a resposta inteira como uma página só, porque o widget não pagina: uma lista
  vazia só conta como "sem vagas" quando a chamada teve sucesso (HTTP 2xx e JSON válido
  com `jobs: []`), nunca como resultado padrão de erro ou schema alterado (mesma regra
  dos demais coletores — falha nunca parece board vazio).

## Referências

- https://apply.workable.com/robots.txt (verificado, `Disallow` vazio)
- https://www.workable.com/robots.txt (verificado, bloqueia só áreas administrativas)
- https://www.workable.com/terms (verificado, sem cláusula de scraping específica)
- https://help.workable.com/hc/en-us/articles/115012771647-Using-the-Workable-API-to-create-a-careers-page
  (a própria Workable documenta o widget público como mecanismo para páginas de carreira
  de terceiros)
- Precedente interno: `docs/pesquisas/termos-workday.md` e `probing.py` (referência ao
  Lever `postings-api`, endpoint público sem termo dedicado).
