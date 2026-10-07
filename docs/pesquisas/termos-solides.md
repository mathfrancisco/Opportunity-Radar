# Revisão de termos — Sólides (F52-06)

**Data:** 2026-10-07
**Card:** F52-06 da [SPEC 52](../52-spec-aderencia-ao-nivel.md)
**Veredito:** **não viável hoje.** Não foi encontrada API nem feed público documentado, e os
termos gerais vedam obter material por meio que a Sólides não disponibiliza. Nenhum coletor é
construído.

As páginas foram lidas por ferramenta de busca e extração, não em navegador. As citações são
as que a ferramenta devolveu; antes de reabrir a revisão, conferir o original.

## Páginas consultadas (acesso 2026-10-07)

| URL | Resultado |
| --- | --- |
| https://solides.com.br/termos-de-uso/ | lida. Título: "Termos de Uso e Responsabilidade \| Sólides Ponto e DP"; sem data de atualização visível |
| https://vagas.solides.com.br/termos-de-uso | HTTP 404 |
| https://vagas.solides.com.br/robots.txt | lida |
| Termos próprios do Portal de Vagas | **não localizados** |
| Documentação de API ou feed público de vagas | **não localizada** |

## Endpoint público

Nenhum documentado. O Portal de Vagas (`vagas.solides.com.br`) é um site; a página de uma
vaga fica em `/empresa/<slug>/vaga/...`. Nenhuma chamada foi feita além do `robots.txt`.

`robots.txt`: para `User-agent: *`, `Allow: /`. Para `Googlebot`, permite
`/empresa/*/vaga` e bloqueia `/empresa/*$`. Declara
`Sitemap: https://www.vagas.solides.com.br/sitemap.xml`. O `robots.txt` diz o que um robô
pode buscar; não é licença para guardar e reexibir o conteúdo.

## Taxa

Nada documentado.

## Termos

Do documento lido, que pelo título cobre os produtos de Ponto e DP e não cita o Portal de
Vagas em cláusula própria:

- Cláusula 3.7(d): é vedado "obter ou tentar obter qualquer material ou informação, por
  qualquer meio não disponibilizado ou não fornecido, intencionalmente, através da SÓLIDES."
- Cláusula 3.3: "É extremamente vedada a modificação, cópia parcial ou total de qualquer
  texto, logomarca ou gráfico, distribuição, transmissão, exibição, execução, reprodução,
  publicação...", estendida a "informações e pesquisas nele geradas".

Se esses termos valem para o Portal de Vagas: **não confirmado**.

## Atribuição

Nenhuma exigência encontrada.

## Veredito e motivo

**Não viável hoje.** A decisão do dono exige API ou feed público documentado, e não há
nenhum. Coletar exigiria ler o HTML ou o sitemap do portal, e a cláusula 3.7(d), se
aplicável, veda justamente o meio não fornecido. O que reabriria a revisão: a Sólides
publicar um feed ou API de vagas, ou termos do Portal de Vagas que permitam o uso.
