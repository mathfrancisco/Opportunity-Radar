# Revisão de termos — Jobicy API (F48-19)

**Data:** 2026-09-30
**Card:** [F48-19](../48-roadmap-mais-vagas/f48-19-termos-novos-ats.md)
**Veredito:** **viável** (com atribuição e no máximo 1 consulta por hora)

## Páginas consultadas (acesso 2026-09-30)

| URL | Resultado |
| --- | --- |
| https://jobicy.com/jobs-rss-feed | lida (descrição da API, atribuição e frequência) |
| https://jobi.cy/apidocs | HTTP 403 |
| https://jobicy.com/api/v2/remote-jobs?count=1 | 1 fetch, lido só o cabeçalho (`documentationUrl`, `friendlyNotice`); nenhum item de vaga aproveitado |

Observação de método: o aviso `friendlyNotice` só existe na resposta do endpoint; o fetch de 1
item foi feito para ler esse aviso, não como probe de coletor.

## Endpoint público

`GET https://jobicy.com/api/v2/remote-jobs` — "public REST endpoint" com JSON, "No API key
required" para o acesso básico, até 200 vagas por requisição, filtros `geo`, categoria, `count`
e `tag`. Também há RSS. O resumo da página não indica endpoint de detalhe separado.

## Taxa

"A few checks per day are usually enough. Automated checks must not run more frequently than
once per hour." (resumo do fetch da página `jobs-rss-feed`).

## Atribuição

- Página: "Keep Jobicy as the original source and preserve the canonical Jobicy job URL when
  displaying listings."; não apresentar as vagas como postagens originais nem remover a
  atribuição.
- Aviso da resposta: "Thanks for using Jobicy API! Please ensure Jobicy is clearly credited
  with a direct link to the source, and all application buttons redirect to the original job
  URL provided in this feed."

## Veredito e motivo

**Viável.** Endpoint público documentado, sem chave, com regras claras: crédito e link direto a
Jobicy, botões de candidatura levando à URL original do feed, e no máximo uma consulta por hora
(uma por dia é suficiente para a fonte). Ressalva: a página de docs dedicada (`jobi.cy/apidocs`)
deu 403, então os termos completos não foram lidos.
