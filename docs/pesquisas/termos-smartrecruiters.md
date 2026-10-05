# Revisão de termos — SmartRecruiters (F48-19)

**Data:** 2026-09-30
**Card:** [F48-19](../48-roadmap-mais-vagas/f48-19-termos-novos-ats.md)
**Veredito:** **a confirmar** (endpoint público documentado; termos de uso da API não lidos)

## Páginas consultadas (acesso 2026-09-30)

| URL | Resultado |
| --- | --- |
| https://developers.smartrecruiters.com/docs/posting-api | lida |
| https://developers.smartrecruiters.com/docs/endpoints | lida |
| https://developers.smartrecruiters.com/reference/v1listpostings | lida |
| https://www.smartrecruiters.com/legal/terms-of-use/ | lida (é o termo do **Candidate Portal**) |
| Termos de desenvolvedor/API da SmartRecruiters | **não localizados nem lidos** |

## Endpoint público

- Listagem: `GET https://api.smartrecruiters.com/v1/companies/{companyIdentifier}/postings`
  (descrita em `/docs/endpoints` como "Lists active postings published by given company.").
  Parâmetros vistos no `reference/v1listpostings`: `q`, `limit` (máximo 100), `offset`,
  `destination`.
- Detalhe: `.../postings/{postingId}` ("Content of a job posting with given id.").
- Autenticação: a página `v1listpostings` lista três esquemas de segurança: nenhuma
  autenticação, API key (`x-smarttoken`) ou OAuth 2.0 com escopo `internal_postings_read`, e
  afirma: "The internal_postings_read OAuth scope is only required when the destination query
  parameter is INTERNAL or INTERNAL_OR_PUBLIC." Ou seja, o padrão (vagas públicas) não exige
  credencial.
- Ressalva: a página `/docs/posting-api` diz "The Public Posting API supports both API Key and
  OAuth 2.0 Client Credentials authentication." Não houve leitura que reconcilie as duas
  frases; a leitura mais provável é que a chave seja opcional para vagas públicas, mas isso
  deve ser confirmado no probe (fora do escopo deste card).

## Taxa

Nenhuma das páginas lidas menciona limite de taxa para esses endpoints. Não documentado.

## Termos

O único termo lido (`legal/terms-of-use`) rege o Candidate Portal (`my.smartrecruiters.com`) e a
plataforma. Cláusulas lidas: "Use automatic means to access content or data from other users";
"Harvest, collect, gather or assemble information or data regarding other users without their
consent". Elas falam de dados de **outros usuários** e não citam API, robots.txt nem scraping
de vagas publicadas. Não foi lido nenhum termo específico da Posting API nem exigência de
atribuição.

## Atribuição

Nenhuma exigência encontrada nas páginas lidas (não é o mesmo que ausência confirmada).

## Veredito e motivo

**A confirmar.** Há endpoint público documentado e sem credencial para vagas públicas, mas
o termo que rege o uso da API não foi encontrado, e a documentação é ambígua sobre chave. Antes
de qualquer coletor: localizar e ler os termos de desenvolvedor, e confirmar a autenticação
com probe de 1 item (rito F48-20).
