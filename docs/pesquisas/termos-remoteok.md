# Revisão de termos — Remote OK API (F48-19)

**Data:** 2026-09-30
**Card:** [F48-19](../48-roadmap-mais-vagas/f48-19-termos-novos-ats.md)
**Veredito:** **viável, condicionado à atribuição** (limites de taxa não documentados)

## Páginas consultadas (acesso 2026-09-30)

| URL | Resultado |
| --- | --- |
| https://remoteok.com/api | lida (fetch único; o texto legal está na própria resposta da API) |
| https://remoteok.com/terms | HTTP 404 |
| Página de documentação dedicada da API | **não localizada** |

Observação de método: a única fonte legal localizada é o campo/aviso legal que a própria API
publica na resposta de `https://remoteok.com/api`; foi lido com um único fetch, e nenhum item de
vaga foi coletado.

## Endpoint público

`GET https://remoteok.com/api` — JSON, sem chave, segundo o aviso legal (que fala em "API access").
Não há documentação de parâmetros, paginação ou detalhe por vaga nas fontes lidas.

## Taxa

Não documentada nas fontes lidas.

## Termos e atribuição (trecho literal)

"Please link back (with follow, and without nofollow!) to the URL on Remote OK and mention Remote
OK as a source, so we get traffic back from your site. If you do not we'll have to suspend API
access. Please don't use the Remote OK logo without written permission as it's a registered
trademark, please DO use our name Remote OK though."

Consequências para o projeto: guardar a URL original da vaga, exibir "Remote OK" como fonte,
link de retorno sem `nofollow` onde as vagas forem exibidas, não usar o logotipo.

## Veredito e motivo

**Viável**, com atribuição obrigatória e link para a URL da vaga no Remote OK. Ressalvas: não há
termos de uso completos lidos (o `/terms` deu 404), limite de taxa desconhecido (usar ritmo
baixo, no máximo poucas chamadas por dia, como para o Remotive). Se o produto não puder exibir o
link de retorno com `follow`, o veredito passa a **não viável**.
