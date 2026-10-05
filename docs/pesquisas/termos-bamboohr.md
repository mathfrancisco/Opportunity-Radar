# Revisão de termos — BambooHR (F48-19)

**Data:** 2026-09-30
**Card:** [F48-19](../48-roadmap-mais-vagas/f48-19-termos-novos-ats.md)
**Veredito:** **não viável**

## Páginas consultadas (acesso 2026-09-30)

| URL | Resultado |
| --- | --- |
| https://documentation.bamboohr.com/docs/getting-started | lida |
| https://www.bamboohr.com/legal/terms-of-service | lida (seção 4.2) |
| https://www.bamboohr.com/legal/developer-terms-of-service | lida |
| https://www.bamboohr.com/legal/terms-of-service/ (com barra final) | HTTP 404 |

## Endpoint público

A documentação lida só descreve acesso autenticado (OAuth ou API key com HTTP Basic):
"Each API request sent from a third-party application to the BambooHR website will be
authenticated and permissioned as if a real user were using the software." A página não
documenta nenhum endpoint de vagas sem autenticação. Existir uma página pública de carreiras
`*.bamboohr.com/careers` não a torna endpoint documentado: **não há endpoint público
documentado** de listagem/detalhe.

## Taxa

A página lida não especifica limites. Os termos de desenvolvedor proíbem "exceed or attempt to
circumvent any rate limits or usage caps, or otherwise place an unreasonable or
disproportionate load on the Developer Tools or BambooHR infrastructure".

## Termos

- Termos de Serviço, seção 4.2 (Restrictions): proíbe agir "with any robot, spider, other
  automated device, or manual process to monitor or copy any content from the Service other
  than copying or exporting of the Customer Data as contemplated in the documentation". O
  "Service" é definido na seção 1.1 como um HRIS; a leitura não permitiu concluir se as
  páginas públicas de carreiras estão dentro dele.
- Termos de Desenvolvedor: proíbem "scrape or crawl BambooHR interfaces or content without
  BambooHR's prior written consent".

## Atribuição

Termos de desenvolvedor: proíbem "obscure, misrepresent, or remove attribution to BambooHR as
the source of BambooHR Customer Integration Data" (aplica-se a dados via API autenticada).

## Veredito e motivo

**Não viável.** Sem endpoint público documentado, e com cláusulas explícitas contra robôs e
scraping sem consentimento escrito. O acesso programático legítimo exige OAuth do cliente
(credencial que o projeto não tem por empresa). Lemon.io (`lemonio`) e afins ficam de fora
deste ATS; revisitar só com consentimento escrito da BambooHR ou API pública documentada.
