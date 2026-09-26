# Revisão de termos — Teamtailor

- **Card:** F20-29 — Coletor Teamtailor
- **Data:** 2026-09-26
- **Decisão:** **Viável.** Segue para implementação do coletor.

## O que existe

Cada empresa cliente da Teamtailor publica seu board de vagas em um domínio próprio
(ex.: `jobs.<empresa>.com` ou `<empresa>.teamtailor.com`, a depender do domínio
customizado configurado pela empresa). Nesse domínio, a Teamtailor expõe um feed
público em `/jobs.json`, no formato **JSON Feed 1.1** (`https://jsonfeed.org/version/1.1`)
com dados adicionais de vaga embutidos em `_jobposting` usando o vocabulário
`schema.org/JobPosting`.

Verificado ao vivo em dois boards reais do catálogo (`jobs.seedtag.com`,
`jobs.lingokids.com`, ambos citados em `docs/pesquisas/auditoria-186-empresas.md`):

- `GET /jobs.json` retorna sem autenticação, sem chave de API e sem cookie de sessão.
- Estrutura de nível superior: `version`, `title`, `home_page_url`, `feed_url`, `items`.
- Cada item de `items`: `id` (uuid), `title`, `url`, `date_published`, `content_html`,
  `_jobposting` (objeto `schema.org/JobPosting`: `@context`, `@type`, `title`,
  `description`, `identifier`, `datePosted`, `hiringOrganization`, `jobLocation`).
- **Não há campo estruturado de departamento, senioridade, tipo de contrato ou
  remoto** — essas informações, quando existem, estão embutidas em texto livre
  em `description`/`content_html`. Isso está de acordo com a nota do card: mapear
  departamento (F20-03) e senioridade (F20-02) só para o que o endpoint realmente
  expõe — aqui, nada de estruturado, então nenhum mapeamento é aplicado.
- **Não há paginação**: o feed não tem `next_url` nem parâmro de página; os dois
  boards testados devolveram todas as vagas publicadas em uma única resposta.
  Isso contraria a hipótese da tabela original do card ("página pública... com feed,
  paginado") — a forma real é feed único, não paginado por página numerada. O
  coletor trata isso como uma "página" só, mas mantém o mesmo contrato de nunca
  confundir falha com board vazio (schema inesperado -> erro, não lista vazia).

## `robots.txt`

Idêntico nos dois boards testados (indicando política de plataforma, não por
empresa):

```
User-Agent: aihitdata
Disallow: /

User-Agent: *
Disallow: /app/
Disallow: /messages/
Disallow: /messenger/
Disallow: /facebook/tab/
Disallow: /jobs/internal/
Content-Signal: search=yes, ai-train=no, ai-input=yes

Sitemap: https://jobs.<empresa>.com/sitemap.xml
```

`/jobs.json` **não está na lista de `Disallow`** para `User-Agent: *`. O único
bloqueio total é para o bot nomeado `aihitdata`, que não se aplica a este coletor.
`Content-Signal` permite `ai-input=yes` (uso do conteúdo como entrada) e nega
`ai-train=no` (não treinar modelo com o conteúdo) — este card não treina modelo
nenhum, só lê e armazena a vaga, então não há conflito.

## Termos de uso

O formato JSON Feed é, por definição, um formato de **sindicação** — o mesmo
propósito de um feed RSS/Atom: publicar conteúdo para consumo automatizado por
terceiros (agregadores, leitores de feed, robôs de busca de vagas). A Teamtailor
não publica um endpoint de termos específico para o feed público de vagas (a
página `docs.teamtailor.com` documenta a API autenticada de cliente, não o feed
público); não foi encontrada nenhuma cláusula proibindo acesso automatizado ao
feed público em si. O robots.txt idêntico nas duas empresas testadas é o sinal
mais forte disponível, e ele permite.

## Condições para operar com segurança

- Identificar o coletor por `User-Agent` próprio (mesma prática dos outros
  coletores do projeto).
- Nenhum limite de taxa documentado publicamente; o coletor aplica o mesmo
  contrato de retentativa dos demais (`Retry-After` em 429, backoff, máximo de
  tentativas) por precaução, não porque a Teamtailor publique um limite.
- Sem paginação real: uma resposta 200 com `items` bem formado é o feed completo;
  registrar a contagem via telemetria (`record_items_announced`) a partir do
  tamanho de `items`, sem inferir mais páginas.
- Atribuir a fonte (nome da empresa e URL do board) ao registrar a vaga, prática
  já seguida pelos outros coletores.

## Conclusão

Sem proibição de automação encontrada; endpoint é um feed de sindicação público,
sem autenticação, com forma estável (JSON Feed 1.1 + schema.org JobPosting), sem
paginação e sem campos estruturados de departamento/senioridade. Sub-card segue
para implementação do coletor com essas correções em relação à hipótese original
da tabela do card-guarda-chuva (F20-29 e F17-10): **feed único, não paginado**.
