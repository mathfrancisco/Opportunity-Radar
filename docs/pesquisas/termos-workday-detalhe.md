# Revisão de termos — endpoint de detalhe do Workday (F48-19)

**Data:** 2026-09-30
**Card:** [F48-19](../48-roadmap-mais-vagas/f48-19-termos-novos-ats.md)
**Complementa:** [termos-workday.md](termos-workday.md) (F20-28, que cobre a listagem)
**Veredito:** **a confirmar** (mesma zona intermediária da listagem; sem termo dedicado)

## Páginas consultadas (acesso 2026-09-30)

| URL | Resultado |
| --- | --- |
| https://www.workday.com/en-us/legal/site-terms.html | lida |
| https://nvidia.wd5.myworkdayjobs.com/robots.txt | lida |
| Portal de desenvolvedor/documentação pública do endpoint `wday/cxs` | **não existe** nas fontes consultadas |

## Endpoint

`GET https://<tenant>.<pod>.myworkdayjobs.com/wday/cxs/<tenant>/<site><externalPath>` (detalhe
da vaga; descrição em `jobDescription`). Descrito em `termos-workday.md`; **não documentado
oficialmente** pela Workday. Não foi chamado nesta revisão. É o backend do próprio SPA de carreiras.

## robots.txt (lido em 2026-09-30, tenant `nvidia.wd5`)

```
Sitemap: https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/siteMap.xml

User-agent: *
Allow: /NVIDIAExternalCareerSite/
Disallow: /NVIDIAExternalCareerSiteResearch/
Disallow: /talentcommunity/
Disallow: /refreshFacet/
```

Diferença em relação a `termos-workday.md`: hoje há também `Disallow: /NVIDIAExternalCareerSiteResearch/`
(outro site do mesmo tenant). Nenhum `Disallow` cobre `/wday/cxs/`, mas também não há `Allow`
explícito para ele. O `robots.txt` é por tenant e deve ser conferido por tenant.

## Termos

Fetch dos termos de site da Workday, com trechos:
- Escopo (segundo o resumo do fetch): "www.workday.com, associated web pages, the Community, and
  Workday APIs".
- "Use any data mining, robots or similar data gathering or extraction methods designed to
  scrape or extract data from our Sites"
- "Develop or use any applications that interact with our Sites without our prior written
  consent"
- "Bypass or ignore instructions contained in our robots.txt file"

Ponto em aberto: se os sites `*.myworkdayjobs.com` (conteúdo de cada tenant) entram em "our
Sites" **não é dito no texto lido**. Não foi encontrado termo específico para eles.

## Taxa e atribuição

Sem limite documentado, sem exigência de atribuição encontrada.

## Veredito e motivo

**A confirmar.** Mantém-se o precedente de `termos-workday.md` (listagem aceita pelas guardas do
projeto: robots.txt, ritmo baixo, sem autenticação, sem dado de candidato), mas as cláusulas
acima (robôs, aplicações que interagem sem consentimento escrito) são amplas e o escopo sobre os
sites de tenant não está esclarecido. Recomendação: o detalhe segue o mesmo regime da listagem;
o risco só sobe se o detalhe for chamado em volume (o orçamento do F48-08 continua valendo);
decisão de manter ou revogar fica com o mantenedor.

## Atualização de 2026-10-05

**Veredito mantido: a confirmar. Decisão: o `fetch_detail` do Workday continua desligado.**

Relido hoje: https://www.workday.com/en-us/legal/site-terms.html (o texto traz "Last Updated:
08/13/2026"), por fetch com resumo, não no original em navegador.

- A definição de "Sites" tem quatro partes: (a) `www.workday.com` e páginas associadas; (b)
  "any web pages, websites, corresponding social media pages, materials, or other documents
  (including all content therein) that directly reference these Terms"; (c) a Community; (d)
  as Workday APIs.
- As três proibições citadas acima continuam no texto.
- O texto não nomeia `myworkdayjobs.com` nem sites de carreira de clientes, a não ser um link
  de navegação para as vagas da própria Workday.

O que continua não determinado: se uma página de carreiras de tenant "directly reference
these Terms" (parte b) e se a rota `/wday/cxs/` conta como "Workday APIs" (parte d). O que
fecharia: ler o rodapé e os avisos legais de uma página de tenant num navegador, ou uma
resposta escrita da Workday.

Motivo da decisão: a rota não é documentada, os termos têm proibição expressa de extração e
de aplicações sem consentimento escrito, e ligar o detalhe nas 19 fontes Workday habilitadas
na base de dev significa uma requisição por vaga em cerca de 13 mil vagas. No inHire a
documentação oficial declara a rota pública; aqui não há nada equivalente.
