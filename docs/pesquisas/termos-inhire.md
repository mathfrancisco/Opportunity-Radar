# Revisão de termos — inhire (F48-19)

**Data:** 2026-09-30
**Card:** [F48-19](../48-roadmap-mais-vagas/f48-19-termos-novos-ats.md)
**Veredito:** **viável com ressalvas** (fechado em 2026-10-05, segunda atualização abaixo,
"Fechamento da revisão"). Base: a documentação oficial da API, lida em navegador, descreve
a rota de página de carreira como pública, sem autenticação, só com `X-Tenant`; nenhum
termo lido proíbe a leitura por terceiros, e nenhum a autoriza. Vale para o tipo de ATS
inteiro, com as condições da última seção. Não houve resposta escrita da InHire. O
veredito de 2026-09-30 era "a confirmar" e está preservado nas seções abaixo.

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

## Fechamento da revisão (2026-10-05, segunda passada)

**Veredito: viável com ressalvas.** Escopo: o tipo de ATS inteiro (qualquer tenant
`<tenant>.inhire.app`), não por tenant, porque a rota, a documentação e os termos são os
mesmos para todos. Nenhum coletor existe; a decisão do dono de só construir um depois de
fechar esta revisão fica cumprida com este registro, e a construção continua sendo decisão
dele.

Ferramenta: navegador Playwright (a extensão do Chrome não respondeu em duas tentativas).
`docs.inhire.com.br` foi **legível no navegador**; o 403 de 2026-09-30 era bloqueio a
clientes que não são navegador. Tudo abaixo foi lido hoje, no original.

### Documentação da API (acesso 2026-10-05)

- https://docs.inhire.com.br/guides/guias/pagina-de-divulgacao/listar/ : "A InHire expõe um
  endpoint público (sem autenticação) que retorna a página de carreira default do tenant
  junto com todas as vagas publicadas: Obter Página de Carreira — GET /job-posts/public/pages."
  E, no exemplo: "Como o endpoint é público, não é necessário obter token de acesso." O
  exemplo envia só `X-Tenant`.
- https://docs.inhire.com.br/api/obter-pagina-de-carreira/ : `GET https://api.inhire.app/job-posts/public/pages`;
  "Obrigatório o campo X-Tenant no header da requisição. Para obter o x-tenant basta copiar o
  inicio do link do app." Query opcional `customFieldIds`. A lista de respostas inclui 401,
  em contradição com o texto "sem autenticação"; a resposta real de hoje foi 200 sem token.
- https://docs.inhire.com.br/api/obter-uma-pagina-de-divulgacao/ : `GET /job-posts/public/pages/:jobId`
  (detalhe). Texto gerado automaticamente ("Auto-generated from handler"), com o schema da
  lista copiado; o formato real foi observado (abaixo).
- https://docs.inhire.com.br/guides/auth/ : "Todos os endpoints dessa API, com exceção dos
  listados na seção anonymous, requerem autenticação." Credenciais são criadas pelo
  "owner da conta" (service account). Ou seja, o acesso autenticado é do Cliente; a rota
  pública é a exceção declarada.
- https://docs.inhire.com.br/guides/rate-limits/ : "O limite é por conta, não por token de
  acesso." Taxa sustentada de 20 requisições/segundo, burst de 400; 429 com `Retry-After`.
  Aplica-se a "usuários de API da sua conta", isto é, ao acesso autenticado. A rota
  pública, na resposta de hoje, não trouxe `X-RateLimit-*` nem `Retry-After`: limite
  aplicável a ela **não documentado**.
- https://docs.inhire.com.br/ (introdução): descreve a API pelos fluxos de recrutamento do
  cliente; a página de limites fala em "alimentar seu site de carreiras" (clientes).
- `https://docs.inhire.com.br/robots.txt`: HTTP 404.

**Não encontrado:** termos de uso da API ou de desenvolvedor; qualquer frase sobre
terceiros, agregadores, armazenamento, redistribuição ou atribuição de dados de vagas;
qualquer limite de taxa específico da rota pública. A documentação tampouco diz que a rota
pública é só para o dono do tenant. Ela diz que é pública e sem token, nada mais.

### Exemplo do dono: https://gx2.inhire.app/vagas (acesso 2026-10-05)

- Página renderizada: "Sobre a empresa" (GX2, consultoria de tecnologia), filtros por nome,
  modelo de atuação e localização, **10 vagas**, várias de tecnologia (por exemplo
  "Data Engineer", "Backend Developer (Python) | Senior", "Fullstack Developer (Java +
  Angular/React) | Mid-level"), além de vagas comerciais. Rodapé: "© InHire 2026".
- Requisições da página para ler a lista: `GET https://api.inhire.app/job-posts/public/pages`
  com `x-tenant: gx2` e `x-inhire-client: web-inhire`, sem `Authorization`, sem CAPTCHA;
  mais `GET /tenants/public/config/gx2`. A página de uma vaga chama
  `GET /job-posts/public/pages/<jobId>` e `GET /forms/public/job-id/<jobId>/subscription`
  (esta última é o formulário de inscrição; fora do escopo). A página também carrega
  Datadog, Sentry, Google Analytics, Mixpanel e Hand Talk (telemetria própria, sem relação
  com o nosso uso).
- JSON-LD: a **lista** (`/vagas`) não tem `ld+json`; a **página de detalhe** tem um bloco
  `JobPosting` schema.org (`title`, `description`, `datePosted`, `directApply`,
  `employmentType`, `hiringOrganization.name`, `identifier`, `jobLocation`,
  `jobLocationType`, `applicantLocationRequirements`).
- Nenhum aviso de acesso automatizado na página. Links do rodapé do detalhe: só a política
  de privacidade (`https://www.inhire.com.br/privacidade/`), voltada ao candidato.

Sem navegador (curl, `User-Agent: OpportunityRadar/0.1 (personal job radar; ...)`, 15 s,
duas chamadas):

- `GET https://api.inhire.app/job-posts/public/pages` com `X-Tenant: gx2`: HTTP 200, 10
  itens, sem paginação. Raiz: `tenantName`, `background`, `logo`, `bannerTitle`, `about`,
  `bannerTitleColor`, `visibility`, `jobsPage`. Cada item: `careerPageId`, `careerPageIds`,
  `displayName`, `jobId`, `location`, `status`, `workplaceType`. Cabeçalhos:
  `access-control-allow-origin: *` e `x-inhire-cache: HIT`; sem `RateLimit-*`.
- `GET https://api.inhire.app/job-posts/public/pages/<jobId>`: HTTP 200. Campos de vaga:
  `jobId`, `displayName`, `description`, `location`, `workplaceType`, `contractType`,
  `status`, `createdAt`, `updatedAt`, `publishedAt`, `lastPublishedAt`, `salaryCurrency`,
  `careerPageId`, `careerPageIds`, `activeJobBoards`, `privacyPolicyUrl`,
  `settings.fields`, `settings.requiredFields`,
  `settings.email.{senderType,subject,body,templateId,active}`, mais os campos de empresa
  da raiz.

### Termos e privacidade (acesso 2026-10-05, no navegador)

- https://www.inhire.com.br/termo-e-condicoes-de-uso (última atualização 17 nov 2025).
  Define "Cliente" (empresa que contrata) e "Usuário" (preposto do Cliente); os deveres
  recaem sobre eles. Propriedade intelectual: "É vedado ao Cliente e aos seus Usuários
  copiar o conteúdo e/ou o layout da Plataforma, ou mesmo reproduzir qualquer parte do seu
  produto para quaisquer fins, ainda que não econômicos, sem autorização prévia e expressa
  da InHire." Engenharia reversa (dever do Usuário): "Direta ou indiretamente, não realizar
  engenharia reversa, copiar ou tentar copiar, decompor, decifrar ou de qualquer forma
  reproduzir elementos da Plataforma InHire." API: "A InHire não será responsabilizada
  pelas integrações realizadas pelo Cliente com a Plataforma InHire através da API
  disponibilizada." A única frase sobre coleta é a do InHire Companion (já citada acima),
  sobre o produto deles. Nada sobre leitura de páginas públicas de vagas por quem não é
  Cliente. Se essas cláusulas alcançam um terceiro que apenas lê a rota pública: não
  determinado (o texto delimita Cliente e Usuário, e o projeto não é nenhum dos dois; o
  texto também não diz que a leitura pública é livre).
- https://www.inhire.com.br/privacidade/ (política de privacidade): trata de dados de
  Candidatos e do Banco de Talentos. Não trata de leitura de vagas publicadas.
- Robots (hoje): `gx2.inhire.app` e `inhire.app`: `Disallow: /indique-uma-pessoa/` apenas;
  `www.inhire.com.br`: `Allow: /`; `api.inhire.app`: 403; `docs.inhire.com.br`: 404. Nada
  proíbe `/vagas` nem a rota da API; o host da API não declara.
- Não achei termos específicos para páginas de carreira (`*.inhire.app`) voltados a
  visitantes, nem termos de API separados. Questões de lei (por exemplo, base legal para
  reutilizar o conteúdo): não determinado; nenhuma fonte lida as trata.

### Dados pessoais

Nas respostas de lista e detalhe de gx2: nenhum e-mail ou telefone (busca por padrão no
JSON; o texto da descrição não foi lido). Os campos são de empresa e de vaga, não de
pessoa. Ainda assim `description` é texto livre da empresa e pode conter contato de
recrutador; o coletor deve passar pelo mesmo tratamento de PII dos outros tipos.

- **Usar:** `jobId`, `displayName` (título), `description`, `location`, `workplaceType`,
  `contractType`, `publishedAt` (ou `lastPublishedAt`), `status`, `tenantName`, e a URL
  pública `https://<tenant>.inhire.app/vagas/<jobId>/<slug>` para o link de volta.
- **Descartar:** `settings.*` (inclui corpo e assunto do e-mail automático a candidatos),
  `activeJobBoards`, `privacyPolicyUrl`, `about`, `background`, `logo`, `banner*`,
  `salaryCurrency` sem valor, e qualquer dado de formulário de inscrição.

### Comparação com os outros tipos

Parecido com **Greenhouse e Ashby** ("viável com ressalvas"): rota documentada como
pública e sem autenticação, documentação calada sobre terceiros, termos que obrigam o
cliente e não tratam de quem lê. Mais forte que eles em um ponto: a documentação diz
expressamente "público (sem autenticação)". Mais fraco que **Lever** em outro: não há
aviso de que as vagas "may be scraped by third parties" nem `robots.txt` legível no host
da API. Diferente de **Gupy** ("não viável"): não existe cláusula nomeada que proíba
agregar vagas.

### Condições para operar

- `User-Agent` identificável (nome do projeto e contato); nunca o de navegador.
- Uma chamada de lista por tenant por execução e uma chamada de detalhe por vaga nova ou
  alterada, em série, ritmo baixo (no máximo 1 requisição por segundo; a taxa de 20/s da
  documentação é de contas autenticadas e não é referência para o projeto). Sem repetir a
  lista sem necessidade.
- Parar o tenant em 403 ou 429 (respeitar `Retry-After` quando vier); 404 com
  `Tenant not found` é tenant inexistente, não insistir.
- Sem autenticação, sem candidatura automática, sem chamar `/forms/*`, sem usar
  `auth.inhire.app`.
- Mostrar sempre o link para a vaga original; remover a vaga ou o tenant a pedido da
  empresa ou da InHire; desabilitar o tipo se a InHire pedir.
- Descartar os campos listados acima e aplicar o filtro de PII ao texto.
- Descoberta de tenants: a rota não lista tenants, e um tenant desconhecido devolve 404 na
  API (a página `/vagas` devolve a mesma casca para qualquer nome). Cada tenant entra por
  curadoria ou descoberta já aceita no projeto, não por varredura de nomes.

### O que continua em aberto

- Não há resposta escrita da InHire sobre agregação por terceiros, limite da rota
  pública, armazenamento e reexibição. A documentação diz "público", mas não diz "para
  qualquer pessoa" nem "pode armazenar". Esta é a ressalva, como em Ashby e Greenhouse.
  Quem pode responder: suporte ou comercial da InHire. Rascunho:

  > Olá. Sou desenvolvedor de um radar pessoal de vagas, sem fins comerciais. Pretendo
  > ler, em baixa frequência e com User-Agent identificado, a rota pública documentada
  > `GET /job-posts/public/pages` (com `X-Tenant`) de páginas de carreira de empresas
  > clientes, guardar título, local e descrição por tempo limitado e exibir a vaga com
  > link para a página original. Isso é aceito? Há limite de taxa para essa rota? Removo
  > qualquer vaga a pedido.

- Mudança na documentação ou nos termos (de 17 nov 2025) reabre a revisão.

### O que as seções anteriores têm de errado ou desatualizado hoje

- "a API documentada parece destinada ao Cliente (autenticada)" (2026-09-30): corrigido.
  A autenticação vale para o resto da API; a rota de carreira é documentada como pública.
- "Falta ler a documentação": agora lida (no navegador, não por fetch).
- "Limites de taxa, hoje não documentados": há política documentada (20 req/s, burst 400),
  mas para contas autenticadas; para a rota pública segue não documentado.
- "A lista não traz descrição, tipo de contrato nem data": confirmado; o detalhe traz.
- Contagens: `lyncas` 28 itens (medição anterior) e `gx2` 10 itens; ambos sem paginação.

### Referências (acesso 2026-10-05)

- https://docs.inhire.com.br/guides/guias/pagina-de-divulgacao/listar/
- https://docs.inhire.com.br/api/obter-pagina-de-carreira/
- https://docs.inhire.com.br/api/obter-uma-pagina-de-divulgacao/
- https://docs.inhire.com.br/guides/auth/
- https://docs.inhire.com.br/guides/rate-limits/
- https://gx2.inhire.app/vagas e uma página de vaga do mesmo tenant
- https://www.inhire.com.br/termo-e-condicoes-de-uso
- https://www.inhire.com.br/privacidade/
- robots.txt de `gx2.inhire.app`, `inhire.app`, `www.inhire.com.br`, `api.inhire.app`,
  `docs.inhire.com.br`
