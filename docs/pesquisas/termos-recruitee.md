# Revisão de termos — Recruitee (F48-19)

**Data:** 2026-09-30
**Card:** [F48-19](../48-roadmap-mais-vagas/f48-19-termos-novos-ats.md)
**Veredito:** **a confirmar** (endpoint público documentado; termos de uso não lidos)

## Páginas consultadas (acesso 2026-09-30)

| URL | Resultado |
| --- | --- |
| https://docs.recruitee.com/reference/intro-to-careers-site-api | lida |
| https://docs.recruitee.com/reference/offers.md | lida (Careers Site API `/offers/`) |
| https://docs.recruitee.com/llms.txt | lida |
| https://docs.recruitee.com/reference/getting-started | lida (API autenticada de ATS) |
| https://docs.recruitee.com/reference/offers-get | lida (endpoint **admin**, legado, autenticado; não é o alvo) |
| https://recruitee.com/legal/terms-of-service | HTTP 404 |
| Termos de uso da Recruitee (outra URL) | **não localizados nem lidos** |

## Endpoint público

- Listagem: `GET https://{yourcompany}.recruitee.com/api/offers/` (Careers Site API). Doc:
  "Returns a collection of published company jobs. Offers can be filtered by department or
  tag." Segurança declarada vazia (`{}`): sem autenticação. Filtros `department` e `tag`.
- Campos de resposta lidos: `title`, `id`, `department`, `status`, `careers_url`,
  `careers_apply_url`, `description`, `requirements`, `locations`, `salary`,
  `employment_type_code`, entre outros. Não há endpoint de detalhe separado na doc lida
  (a listagem já traz a descrição).
- A introdução da Careers Site API descreve o propósito como "view company jobs and add
  candidates ... from the candidate perspective" e marca a documentação como "still a work in
  progress". O `POST .../candidates` cria candidatura: nunca usar.
- Não confundir com `https://api.recruitee.com/c/{company_id}/offers`, que exige bearer token.

## Taxa

Careers Site API: nenhum limite documentado. A API autenticada de ATS diz "Rate limit is set to
1000 requests per minute per API token" (não se aplica à Careers Site API).

## Termos

Não lidos: a URL tentada retornou 404 e nenhum outro termo foi localizado. Nenhuma cláusula é
afirmada aqui.

## Atribuição

Nenhuma exigência encontrada nas páginas lidas.

## Veredito e motivo

**A confirmar.** É o candidato com melhor documentação pública (endpoint documentado, sem
autenticação), mas falta ler os termos de uso da Recruitee e o `robots.txt` do tenant. Se os
termos não proibirem uso automatizado da Careers Site API, passa a viável.
