# Revisão de termos — Quickin (F52-06)

**Data:** 2026-10-07
**Card:** F52-06 da [SPEC 52](../52-spec-aderencia-ao-nivel.md)
**Veredito:** **a confirmar.** Há endpoint público documentado; os termos de uso não foram
localizados. Nenhum coletor é construído.

As páginas foram lidas por ferramenta de busca e extração, não em navegador. As citações são
as que a ferramenta devolveu; antes de qualquer coletor, conferir o original.

## Páginas consultadas (acesso 2026-10-07)

| URL | Resultado |
| --- | --- |
| https://intercom.help/quickin/pt-BR/articles/5546094-endpoint-pagina-de-carreiras | lida (artigo de ajuda, atualizado em 23 de fevereiro de 2022) |
| https://quickin.io/ | lida; o rodapé só traz "Política de Privacidade" |
| https://quickin.io/termos-de-uso | HTTP 404 |
| https://www.quickin.io/politica-de-privacidade | localizada, não lida |
| Termos de uso da Quickin (outra URL) | **não localizados** |

## Endpoint público

- Lista: `GET https://api.quickin.io/public/{account_id}/jobs?sort=-created_at`.
- Detalhe: `GET https://api.quickin.io/public/{account_id}/jobs/{job_id}`.
- O artigo diz: "Não é necessário usar o token de autenticação para endpoints da página de
  carreiras."
- Campos listados: `_id`, `update_status_date`, `publicate`, `code`, `title`, `description`,
  `requirements`, `benefits`, `remuneration_period`, `currency`, `remuneration`, `country`,
  `region`, `city`, `company_id` (`_id`, `name`), `contract_id` (`_id`, `name`), `career_url`,
  `created_at`.
- O artigo descreve o uso pela empresa cliente na própria página de carreiras: "a candidatura
  deverá ser realizada na página de carreiras do Quickin."
- Como obter o `account_id` de uma empresa: **não documentado** no artigo. Paginação: não
  mencionada.

Nenhuma chamada foi feita a `api.quickin.io`.

## Taxa

Nenhum limite documentado no artigo.

## Termos

Não lidos: a URL tentada devolveu 404 e a página inicial não tem link de termos. Nenhuma
cláusula é afirmada aqui.

## Atribuição

Nenhuma exigência encontrada nas páginas lidas.

## Veredito e motivo

**A confirmar.** A decisão do dono pede API ou feed público documentado **e** termos que não
proíbam coleta automatizada. A primeira condição está atendida pelo artigo de ajuda; a
segunda não pôde ser verificada. Falta: localizar e ler os termos de uso; descobrir como o
`account_id` é publicado (um identificador que só se obtém por tentativa não serve); e ter
uma lista curada de empresas brasileiras de tecnologia que usam Quickin, para medir se a fonte
rende vagas do nível do dono.
