# Revisão de termos — inhire (F48-19)

**Data:** 2026-09-30
**Card:** [F48-19](../48-roadmap-mais-vagas/f48-19-termos-novos-ats.md)
**Veredito:** **a confirmar** (documentação da API inacessível a esta revisão; atualização de
2026-10-05 abaixo, veredito mantido)

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

## Atualização de 2026-10-05

**Veredito mantido: a confirmar.** Nada lido hoje autoriza nem proíbe a leitura de vagas
públicas por terceiros. **Decisão do dono em 2026-10-05: nenhum coletor inHire será
construído até esta revisão ser fechada.** Cada item abaixo diz se foi verificado hoje por
quem escreve este arquivo (carregando a URL) ou se é relato da medição do coordenador,
sem nova verificação.

### Verificado hoje (carregando a URL, 2026-10-05)

- `https://lyncas.inhire.app/vagas` e `https://tenant-que-nao-existe-xyz.inhire.app/vagas`:
  HTTP 200, 12.254 bytes cada, arquivos **idênticos** (`cmp`). É uma casca de página
  (título "InHire", sem nenhuma vaga no HTML estático e sem `ld+json`/JSON-LD). Um tenant
  desconhecido devolve a mesma casca, então a página pública não prova que o tenant existe.
- `https://embed.inhire.app/v1/jobs.js`: HTTP 200, 12 KB; o texto contém
  `api.inhire.app/job-posts` e o cabeçalho `X-Tenant`; não contém `Authorization`.
- `GET https://api.inhire.app/job-posts/public/pages` com `X-Tenant: lyncas`: HTTP 200 sem
  autenticação; JSON com `tenantName`, `about`, `logo`, `bannerTitle`, `background` e
  `jobsPage` (28 itens numa única resposta, sem paginação neste tenant). Cada item traz
  `careerPageId`, `careerPageIds`, `displayName` (título), `jobId`, `status`,
  `workplaceType` e `location`. Nenhum cabeçalho `RateLimit-*` nem `Retry-After` na
  resposta. Um tenant só: a ausência de paginação foi observada em um board, não provada.
- Mesma rota com `X-Tenant: tenant-que-nao-existe-xyz`: HTTP 404, corpo
  `{"message":"Tenant not found"}`. Com `X-Tenant: nuvemshop`: também 404; o tenant do
  Nuvemshop não usa esse nome (ou não está nessa rota), e esta revisão não descobriu qual é.
- `https://inhire.app/robots.txt`: `User-agent: *` / `Disallow: /indique-uma-pessoa/`
  (só isso).
- `https://www.inhire.com.br/robots.txt`: `User-agent: *` / `Allow: /` e `Sitemap`.
- `https://api.inhire.app/robots.txt`: HTTP 403, corpo `{"message":"Forbidden"}`. Sem
  `robots.txt` legível no host da API; não determinado o que o host declara.
- `https://docs.inhire.com.br/`: HTTP 403 (página de erro do CloudFront, "Request
  blocked") para um cliente que não é navegador.
- `https://www.inhire.com.br/termo-e-condicoes-de-uso`: HTTP 200, relido. Não há menção a
  leitura automatizada de páginas públicas de vagas. A cláusula de engenharia reversa
  está entre os deveres do Cliente: "Direta ou indiretamente, não realizar engenharia
  reversa, copiar ou tentar copiar, decompor, decifrar ou de qualquer forma reproduzir
  elementos da Plataforma InHire." A única frase sobre coleta é sobre o produto deles:
  "O INHIRE COMPANION NÃO REALIZA QUALQUER TIPO DE COLETA AUTOMÁTICA, CAPTURA MASSIVA,
  EXTRAÇÃO OU SCRAPING DE DADOS."

### Relatado pelo coordenador, não reverificado aqui

- A página de carreiras e o script de embed chamam essa mesma rota (a metade do script
  foi confirmada acima; a de a própria página chamá-la depende de rodar JavaScript, que
  não foi feito).
- A lista não traz descrição, tipo de contrato nem data de publicação; cada vaga exige uma
  chamada de detalhe. Eu vi só a lista (campos acima); a rota de detalhe não foi chamada.
- A contagem de vagas por empresa e o ganho potencial abaixo.

### O que falta para fechar a revisão

1. Ler a documentação da API (`docs.inhire.com.br`) em um navegador: o fetch por script
   recebe 403.
2. Confirmar se a rota `job-posts/public/pages` é documentada como pública, e se o
   cabeçalho `X-Tenant` é o uso previsto para quem não é o cliente.
3. Limites de taxa, hoje não documentados nem observados em cabeçalho.
4. Se os dados guardados podem ser reexibidos (título, local, descrição) e com que
   atribuição.
5. Se ainda for preciso, uma resposta escrita da InHire (a documentação foi a fonte que
   faltou em 2026-09-30 e continua faltando).

### Ganho potencial medido pelo coordenador em 2026-10-05 (nota, não vinculante)

Não decide nada: o veredito e a decisão do dono não mudam por causa dele. Uma empresa do
catálogo tem vagas lá: Conta Azul (14 vagas). Cerca de 15 empresas brasileiras de
tecnologia fora do catálogo têm vagas de tecnologia listadas: Lyncas, Premiersoft,
NSTECH, Objective, Programmers, Atlas, Magazine Luiza, Dock, Olist, Alelo, B3, Sicredi,
Bemobi, Matera e Neoway. Valor da medição do coordenador; só o `lyncas` (28 itens na
lista de hoje) foi visto por mim.
