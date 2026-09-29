# Revisão de termos — Hacker News "Who is hiring?" via API oficial (F20-55)

**Data:** 2026-09-29
**Card:** [F20-55](../44-roadmap-fase-20/fase-20/f20-55-hn-who-is-hiring.md)
**Padrão aplicado:** o mesmo do F20-32 (Gupy) e de F20-51/F20-52
([`wellfound-yc-jobs.md`](wellfound-yc-jobs.md)): termos e robots antes de qualquer código;
proibição nomeada de coleta automatizada **do canal que o coletor usaria** encerra o card.
Esta revisão só fez leituras de `robots.txt`, páginas de termos, README da API e 1 consulta
de leitura ao endpoint público da Algolia para conferir o formato (nenhuma coleta).

## Veredito: **viável, com risco residual registrado**

| Canal | robots.txt | Termos / licença | Limite de taxa | Veredito |
| --- | --- | --- | --- | --- |
| Firebase API `hacker-news.firebaseio.com/v0` | `Allow: /*.json$`, `Allow: /*.json?*$`, `Disallow: /` (só `.json` é permitido — exatamente o que o coletor usa) | README oficial do `HackerNews/API` (MIT, © 2025 Y Combinator Hacker News) publica a API para uso programático; sem cláusula de proibição | "There is currently no rate limit." | Viável |
| Algolia HN Search `hn.algolia.com/api/v1` | `hn.algolia.com/robots.txt` retorna 404 (sem regras) | API pública documentada em `hn.algolia.com/api`, mantida pela Algolia (não é subdomínio da YC); nenhuma chave, login ou cláusula de proibição | Documentada em `hn.algolia.com/api` (página renderizada por JS, não reverificada aqui); o coletor faz 1 chamada por execução | Viável |
| `news.ycombinator.com` (HTML) | `Crawl-delay: 30`; `Disallow` em `/login`, `/vote?`, `/reply?` etc. | Coberto pelos Termos da YC (abaixo) | — | **Fora de escopo** (o card já proíbe raspar HTML; o coletor nunca o acessa) |

## Evidência

### 1. Termos da YC — `https://www.ycombinator.com/legal/`

Definição de "Site":

> "Welcome to the Y Combinator website (including all subdomains, the "**Site**"), which is
> operated by Y Combinator Management, LLC and its affiliates …"

Cláusula de coleta automatizada (mesma citada em `wellfound-yc-jobs.md`):

> "In connection with your use of the Site you will not engage in or use any data mining,
> robots, scraping or similar data gathering or extraction methods."

Pergunta do card: a API é "parte do Site" ou produto próprio? Leitura adotada:

- A cláusula é escopada a "your use of the **Site**", definido como o site da YC **e seus
  subdomínios**. `news.ycombinator.com` é subdomínio; `hacker-news.firebaseio.com`
  (Google Firebase) e `hn.algolia.com` (Algolia) **não são** domínios da YC.
- O texto de termos **não menciona a API** (conferido: nenhuma ocorrência de "API" na
  página `legal`).
- A própria YC publica a Firebase API justamente para acesso por máquina: "In partnership
  with Firebase, we're making the public Hacker News data available in near real time …
  Servers aren't left out." e "There is currently no rate limit."
  (`https://github.com/HackerNews/API`, README). Pedir para robôs não usarem o canal que a
  própria empresa documenta para robôs seria contraditório; o `robots.txt` do host
  Firebase reforça isso permitindo somente `*.json`.
- Diferença para F20-51/F20-52: lá o único canal era o HTML/front-end do Site, coberto
  pela cláusula; aqui existe um canal programático **separadamente documentado e
  convidado**.

### 2. `robots.txt`

`https://news.ycombinator.com/robots.txt` (não usado pelo coletor):

```
User-Agent: *
Crawl-delay: 30
Disallow: /collapse?
Disallow: /context?
Disallow: /fave?
Disallow: /flag?
Disallow: /hide?
Disallow: /login
Disallow: /logout
Disallow: /r?
Disallow: /reply?
Disallow: /submitlink?
Disallow: /vote?
Disallow: /x?
```

`https://hacker-news.firebaseio.com/robots.txt` (usado):

```
User-agent: *
Allow: /*.json$
Allow: /*.json?*$
Disallow: /
```

`https://hn.algolia.com/robots.txt`: HTTP 404 (sem regras).

### 3. README e licença da API — `https://github.com/HackerNews/API`

- Licença MIT (`LICENSE`: "The MIT License (MIT) Copyright (c) 2025 Y Combinator Hacker
  News").
- "There is currently no rate limit." e "Clients should gracefully handle additional
  fields they don't expect, and simply ignore them." (o coletor ignora campos extras).
- Contato para bugs: api@ycombinator.com.

### 4. Algolia HN Search

`GET https://hn.algolia.com/api/v1/search_by_date?query="Ask HN: Who is hiring"&tags=story,author_whoishiring`
respondeu 200 sem credenciais e devolveu os threads mensais (ex.: "Ask HN: Who is hiring?
(September 2026)", `objectID` 49522897, 396 comentários; agosto e julho idem). O autor
`whoishiring` é o bot oficial que abre os threads.

## Condições de operação adotadas (mesmo sem limite documentado)

- Só `hacker-news.firebaseio.com/v0/*.json` e `hn.algolia.com/api/v1/search_by_date`.
  Nunca HTML de `news.ycombinator.com`, nunca login.
- Ritmo conservador mesmo com "no rate limit": intervalo mínimo entre requisições vindo da
  política de rede da fonte; 429/5xx tratados com `Retry-After` e retentativa limitada;
  um thread por execução (~400 comentários), execução mensal/sob demanda.
- Nada de contornar bloqueio; um 403/429 persistente encerra a execução com erro tipado.
- Comentários são conteúdo de usuários; o coletor guarda o texto para triagem própria e
  aponta de volta para `https://news.ycombinator.com/item?id=<id>` (atribuição), sem
  extrair nem usar e-mails/contatos para envio de mensagens (a cláusula da YC contra
  colher contatos "for the purposes of sending unsolicited emails" permanece respeitada:
  o e-mail que aparece no texto não é extraído para campo próprio).

## Risco residual

A cláusula é ampla e a YC pode entender que "Site … all subdomains" inclui o dado do HN
mesmo via API. Mitigações: uso somente do canal documentado, volume mínimo, atribuição,
nenhuma redistribuição. Se a YC publicar restrição ou bloquear o acesso, o coletor deve ser
desabilitado (a fonte é uma `SourceDefinition` que pode ser desligada sem migração).
