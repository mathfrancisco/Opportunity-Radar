# Revisão de termos — inhire (F48-19)

**Data:** 2026-09-30
**Card:** [F48-19](../48-roadmap-mais-vagas/f48-19-termos-novos-ats.md)
**Veredito:** **a confirmar** (documentação da API inacessível a esta revisão)

ATS brasileiro (INT Desenvolvimento de Sistema de RH Ltda.), usado pela Nuvemshop.

## Páginas consultadas (acesso 2026-09-30)

| URL | Resultado |
| --- | --- |
| https://www.inhire.com.br/termo-e-condicoes-de-uso | lida |
| https://docs.inhire.com.br/ | HTTP 403 |
| https://docs.inhire.com.br/api/obter-pagina-de-carreira/ | HTTP 403 |
| https://docs.inhire.com.br/api/obter-vagas/ | HTTP 403 |
| https://docs.inhire.com.br/guides/guias/vaga/listar/ | HTTP 403 |

## Endpoint público

As páginas de docs deram 403 ao fetch, então **nada foi lido da documentação**. Só há
indício vindo de resultados de busca (títulos e trechos, não lidos na fonte): o domínio da API é
`https://api.inhire.app` (autenticação em `https://auth.inhire.app`), existe uma página de
referência "Obter Página de Carreira" e o trecho de busca cita `https://api.inhire.app/job-posts/public/pages`
como rota da página de carreira com vagas publicadas. Se esse endpoint exige ou não
autenticação, cabeçalhos de tenant e limites: **não confirmado**.

## Taxa

Não confirmada.

## Termos

Lidos em https://www.inhire.com.br/termo-e-condicoes-de-uso (fetch resumiu o texto):
- Sobre o INHIRE Companion (extensão de prospecção): "O INHIRE COMPANION NÃO REALIZA QUALQUER
  TIPO DE COLETA AUTOMÁTICA, CAPTURA MASSIVA, EXTRAÇÃO OU SCRAPING DE DADOS." Isso descreve o
  produto deles, não é regra para terceiros.
- Cláusula de engenharia reversa: "direta ou indiretamente, não realizar engenharia reversa,
  copiar ou tentar copiar, decompor, decifrar" (aplicada à plataforma).
- Sobre a API: "A InHire não será responsabilizada pelas integrações realizadas pelo Cliente
  com a Plataforma InHire através da API disponibilizada." (API destinada ao Cliente, isto é, à
  empresa contratante).
- O termo, como resumido, não trata de leitura automatizada de páginas públicas de vagas.

## Atribuição

Nenhuma encontrada.

## Veredito e motivo

**A confirmar.** Os termos lidos não proíbem nem autorizam expressamente a leitura de vagas
públicas por terceiros, e a API documentada parece destinada ao Cliente (autenticada). Falta
ler a documentação (403 ao fetch; tentar navegador manual) e o `robots.txt` da página de
carreira. Nuvemshop segue sem fonte de ATS até lá (ver F20-60).
