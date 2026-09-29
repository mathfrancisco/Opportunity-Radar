# Revisão de termos — Factorial

- **Card:** F20-31 — Coletor Factorial
- **Data:** 2026-09-26
- **Decisão:** **Viável, com correção de forma.** Segue para implementação do coletor, mas
  **não existe endpoint JSON público** como hipotetizado na tabela do card-guarda-chuva —
  a forma real é uma página HTML server-renderizada por empresa, com os dados de cada vaga
  em atributos `data-*` estruturados. O coletor lê esses atributos (não texto livre), nunca
  faz raspagem de prosa.

## O que existe

Cada empresa cliente do Factorial publica seu board de vagas em um subdomínio próprio
`<empresa>.factorialhr.com` (ex.: `careers.factorialhr.com` — o próprio board do Factorial,
70+ vagas — e `agentero.factorialhr.com`, ambos citados em
`docs/pesquisas/auditoria-186-empresas.md`).

Verificado ao vivo em três boards (`agentero.factorialhr.com`, `careers.factorialhr.com`,
`currency-solutions.factorialhr.com`):

- `GET https://<subdominio>.factorialhr.com/` retorna HTML sem autenticação, sem chave de
  API e sem cookie de sessão — status 200, mesmo em navegação anônima.
- **Não há endpoint JSON público.** Diferente de Teamtailor (`/jobs.json`), a página é
  renderizada no servidor (Rails, pacote `CompanyPages`); todas as vagas já vêm completas
  no HTML inicial. A filtragem por time/local/contrato no navegador é só CSS/JS sobre o
  HTML já carregado — não há chamada XHR a uma API de vagas.
- A única API pública documentada do Factorial (`api.factorialhr.com`, ver
  `https://apidoc.factorialhr.com/`) é a API de administração de RH, autenticada por
  Bearer token por empresa cliente — não serve para ler o board público de vagas de uma
  empresa sem essa chave, e exigir essa chave contrariaria "Fora de escopo: fonte que
  exige login". Não é o endpoint deste coletor.
- Cada vaga aparece como um `<li class="job-offer-item">` com atributos estruturados:
  `data-job-postings-url` (URL canônica da vaga), `data-team-id`, `data-location-id`,
  `data-is-remote` (`"true"`/`"false"`), `data-contract-type` (ex.: `indefinite`). O
  título da vaga e os rótulos legíveis de time/local aparecem como texto em três `<div>`
  filhos, nessa ordem fixa (título, nome do time, nome do local) — confirmado nos três
  boards testados com contagens de vaga diferentes (2, ~70 e as de `currency-solutions`).
- **Não há paginação.** Nem `careers.factorialhr.com` (70+ vagas) nem os outros dois boards
  mostram parâmro de página, `next_url` ou "carregar mais" — todas as vagas do board vêm em
  uma única resposta HTML. Isso contraria a hipótese original da tabela do card
  ("página pública de vagas... "); a forma real é página única com todas as vagas embutidas
  (mesma correção que o card-irmão do Teamtailor já registrou para o feed dele).
  `capabilities.pagination` é portanto `False`.
- **Não há campo estruturado de senioridade.** O time (`data-team-id` + rótulo de texto)
  é o único agrupamento estruturado disponível e mapeia razoavelmente para "departamento";
  não há campo de senioridade nem descrição estruturada na página de listagem — a descrição
  completa só existe na página de detalhe de cada vaga (`data-job-postings-url`), que exigiria
  uma requisição HTTP extra por vaga. Por YAGNI/KISS e para não multiplicar chamadas por
  vaga sem necessidade comprovada, o coletor desta versão não busca a página de detalhe;
  a vaga fica com `description=None` quando a listagem não traz descrição — não é
  fabricação de campo ausente.

## `robots.txt`

Idêntico nos três boards testados (indica política de plataforma, não por empresa):

```
User-agent: *
Allow: /
```

Totalmente permissivo — nenhum `Disallow`, nenhum bloqueio a agente nomeado.

## Termos de uso

- `https://factorialhr.com/terms-of-use` é o contrato comercial entre o Factorial e a
  empresa cliente que paga a plataforma (condições de assinatura, cobrança, rescisão);
  não trata de acesso de terceiros ao board público de vagas nem menciona raspagem,
  automação ou crawlers como proibidos.
- A página `<subdominio>.factorialhr.com/terms` é o aviso de privacidade do candidato
  (LGPD/GDPR sobre dados pessoais enviados na candidatura) — também não trata de acesso
  automatizado à listagem pública.
- Não foi encontrada nenhuma cláusula, em nenhum dos documentos legais públicos do
  Factorial, proibindo acesso automatizado ao board público de vagas em si.

## Condições para operar com segurança

- Identificar o coletor por `User-Agent` próprio (mesma prática dos outros coletores).
- Nenhum limite de taxa documentado publicamente; o coletor aplica o mesmo contrato de
  retentativa dos demais (`Retry-After` em 429, backoff, máximo de tentativas) por
  precaução.
- Ler só os atributos estruturados (`data-job-postings-url`, `data-team-id`,
  `data-is-remote`, `data-contract-type`) e o texto dos três `<div>` de rótulo em ordem
  fixa dentro de cada `<li class="job-offer-item">`; qualquer `<li>` fora dessa forma
  conta como mudança de schema (erro), nunca como vaga vazia ou ignorada silenciosamente.
- Sem paginação real: uma resposta 200 com pelo menos um `<li class="job-offer-item">`
  bem formado (ou zero, legitimamente, se o board não tem vaga aberta) é o board completo;
  telemetria de itens anunciados vem da contagem de `<li>` encontrados, sem inferir mais
  páginas.
- Atribuir a fonte (nome da empresa e URL do board) ao registrar a vaga, prática já
  seguida pelos outros coletores.

## Conclusão

Sem proibição de automação encontrada; `robots.txt` permissivo nos três boards testados;
nenhum termo de uso público cobre ou proíbe acesso ao board de vagas. **Correção de forma
em relação à hipótese da tabela do card-guarda-chuva**: não há endpoint JSON, a forma real
é uma página HTML por empresa com uma única resposta (sem paginação) e com os dados de
cada vaga em atributos `data-*` estruturados, não em prosa livre. O coletor lê só esses
atributos estruturados, nunca faz raspagem de texto solto — está de acordo com "Fora de
escopo: raspagem de HTML quando existe endpoint estruturado", porque aqui **não existe**
endpoint estruturado alternativo (JSON) ao qual preferir; os atributos `data-*` são a única
fonte estruturada disponível. Sub-card segue para implementação do coletor com essas
correções em relação à hipótese original (F20-31 e F17-10): **página única HTML por
empresa, sem paginação, sem descrição estruturada na listagem, sem campo de senioridade**.
