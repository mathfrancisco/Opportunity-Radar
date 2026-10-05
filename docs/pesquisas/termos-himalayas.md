# Revisão de termos — Himalayas Remote Jobs API (F48-19)

**Data:** 2026-09-30
**Card:** [F48-19](../48-roadmap-mais-vagas/f48-19-termos-novos-ats.md)
**Veredito:** **viável** (com atribuição visível; termos gerais do site não lidos)

## Páginas consultadas (acesso 2026-09-30)

| URL | Resultado |
| --- | --- |
| https://himalayas.app/docs/remote-jobs-api | lida |
| Termos de uso gerais de himalayas.app | **não lidos** |

## Endpoint público

- Listagem: `GET https://himalayas.app/jobs/api` (feed completo) e
  `GET https://himalayas.app/jobs/api/search` (filtros: palavra-chave, país, senioridade, tipo
  de emprego, empresa, fuso).
- Autenticação: "No API key or authentication is required."
- Máximo 20 vagas por requisição; paginação por cursor recomendada, `offset` descontinuado;
  dados atualizados a cada 24 horas por cache.
- Detalhe separado: não descrito.

## Taxa

"The API is rate limited. If you exceed the rate limit, you will receive a `429 Too Many
Requests` response." Valor numérico não informado; limites maiores por contato com
`hi@himalayas.app`. Como o dado renova a cada 24h, uma coleta diária basta.

## Atribuição

"If you display Himalayas job data on your own website or application, include a visible link
back to himalayas.app and mention that the data is sourced from Himalayas."

## Veredito e motivo

**Viável**, com crédito visível a Himalayas e link para himalayas.app onde as vagas aparecerem,
respeito a `429` (backoff) e coleta no máximo diária. Ressalva: termos de uso gerais do site
não foram lidos; a doc da API é a única fonte citada.

## Não revisado

Arbeitnow (`https://www.arbeitnow.com/blog/job-board-api`, lido): API gratuita, sem chave, mas o
texto lido não traz termos, limite nem atribuição, e o conteúdo é reagregado de outros ATS
(Greenhouse, SmartRecruiters, Recruitee etc., segundo resultado de busca). Ficou fora dos três
candidatos por falta de termos; seria **a confirmar**.
