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
