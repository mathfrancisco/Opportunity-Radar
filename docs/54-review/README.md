# Revisao visual - SPEC 54

Estes arquivos sao prototipos estaticos com dados sinteticos. Nao fazem chamadas de rede, nao representam autenticacao e nenhuma acao persiste dados.

## Abrir e reproduzir

Abra `inbox.html` ou execute `node serve-local.mjs` e acesse `http://127.0.0.1:54154/`. O servidor atende somente loopback.

Para gerar capturas e verificacoes, a partir da raiz do repositorio: `node docs/54-review/capture-playwright.cjs`. O runner sobe e encerra o proprio servidor em 127.0.0.1:54154 (falha com mensagem clara se a porta ja estiver ocupada) e usa o Playwright ja instalado em `tests/e2e/browser`. O runner PowerShell (`capture-screenshots.ps1`) e legado.

## Estado verificado em 2026-10-07

- Os prototipos de Inbox, detalhe, Pipeline e Overview tiveram aceite visual explicito em 2026-10-07 (ver "Aceite visual"), com dois ajustes ja aplicados. O aceite e apenas visual.
- F53 esta adiada para F54 local. Hospedagem, Clerk, backup/restore e cutover nao estao implementados.
- Houve spikes descartaveis em `../54-spike`; nenhum kit foi aprovado ou selecionado.
- Os prototipos nao foram publicados nem conectados a dados ou servicos.

## Aceite visual

- Data: 2026-10-07.
- Quem aceitou: o usuario, dono do repositorio.
- Resposta literal: "ACEITO E PODE SEGUIR COM TUDO , VEJA QUAL MELHOR BIBLIOTECA E PODE SEGUIR COM ELA".
- Escopo: os quatro prototipos (Inbox, Detalhe da vaga, Pipeline e Visao geral) como direcao visual para WP3-WP5 da SPEC 54, secao 7 / AC54-02.
- Ajustes recomendados na revisao e aceitos junto com a resposta, aplicados depois do aceite e verificados pelo runner: (1) Pipeline em desktop: etapas sem candidaturas viram colunas estreitas com nome e contagem em texto, e as sete etapas cabem em 1440 e 1280 px sem rolagem horizontal; (2) Detalhe da vaga em ate 900 px: o painel "Sua decisao" aparece logo apos o bloco do titulo e antes de "O que a vaga pede", com a mesma ordem no DOM e na tela.
- Limites que continuam valendo: e aceite somente visual. Nao e aceite da F53, de AC54-01, AC54-08 ou AC54-10, nem da SPEC 54 como um todo. Zoom real do browser, leitor de tela, reduced-motion e dispositivos fisicos continuam sem verificacao.

## Evidencia e limites

O runner grava `screenshots/capture-report.json` e `screenshots/verification.json` e sai com codigo diferente de zero se qualquer assercao falhar. Assercoes:

- nenhum `pageerror` nem erro de console;
- sem overflow horizontal (scrollWidth maior que clientWidth) em nenhuma captura padrao ou de estado;
- menu movel: apos o clique o painel fica visivel e `aria-expanded="true"`; apos Escape fica oculto, `aria-expanded="false"` e o foco volta ao botao;
- seletor de estado: em loading, empty, error e partial o painel fica visivel com titulo nao vazio; em error existe "Tentar novamente" e o clique volta ao estado padrao com o conteudo visivel;
- Inbox em 768 e 360 px: 5 `columnheader`, 4 `row` (cabecalho + 3) e 15 `cell` expostos por papel;
- Pipeline em 1440 e 1280 px: `.pipeline-board` sem overflow interno (scrollWidth menor ou igual a clientWidth) e as 7 etapas visiveis dentro da largura da tela;
- Detalhe em 768 e 360 px: o painel de decisao fica abaixo do titulo e acima de "O que a vaga pede", e o precede no DOM; no estado partial o aviso de IA aparece;
- qualquer requisicao fora de `http://127.0.0.1:54154` e bloqueada, registrada e reprovada.

Ultima execucao (exit 0): `captures: 45; state checks: 32` e `PASSED: all assertions satisfied`. Sao 45 capturas: 13 telas padrao (4 paginas em 1440, 768 e 360 px, mais `pipeline-1280.png`, capturada so para a Pipeline) e 32 estados (4 paginas, 4 estados, em 1440 e 360 px). Inbox em 768 e 360: `columnHeaders: 5, rows: 4, cells: 15`. Pipeline: `.pipeline-board` 1084/1084 em 1440 e 934/934 em 1280; 2 verificacoes de ordem do painel de decisao no detalhe (768 e 360).

Regressao deliberada (`.inbox-table thead{display:none}` reinserido em ate 900 px; ja revertida): exit 1, `FAILED: 4 assertion(s) violated`, incluindo `Inbox at 768: expected 5 columnheader roles, found 0` e `expected 4 row roles (header + 3), found 3` (o mesmo em 360).

Corrigido nesta rodada:

- Tabela da Inbox em mobile: removido o `display:none` do `thead`, de modo que o bloco que o oculta apenas visualmente passou a valer, e adicionados papeis ARIA explicitos (`table`, `rowgroup`, `row`, `columnheader`, `cell`) em `review.js`, porque o layout em cartoes usa `display:block`. A `caption` foi mantida.
- Tres defeitos visuais (regras CSS no fim de `review.css`): regua unica sob o titulo do detalhe, botoes `<a class="button">` centralizados e sem sublinhado (Overview), e espacamento entre grupos de navegacao na barra lateral e no menu movel. Nada mais no desenho foi alterado; as capturas PNG foram regeneradas.
- Timeout intermitente de `[data-state]`: nao foi reproduzido (6 execucoes do runner antigo contra um servidor externo e 5 do novo). Havia um servidor antigo ocupando a porta 54154, de sessao anterior, o que torna a dependencia de servidor externo o ponto fraco mais provavel, mas isso nao e causa comprovada. O runner agora sobe o proprio servidor, espera resposta HTTP e usa `waitForSelector('[data-state]')`. `review.js` troca `document.body.innerHTML` de forma sincrona antes de `DOMContentLoaded`, o que nao gera corrida.
- Overview: o texto "Busca salva: produto remoto - 2 novas vagas desde a ultima abertura" corresponde a contratos existentes: `SavedSearch.lastOpenedAt` (`last_opened_at`) e `GET /saved-searches/:id/new-count`, que retorna `new_count`, em `apps/web/src/features/saved-searches/api.ts`; a tela real exibe isso em `apps/web/src/routes/OverviewPage.tsx` ("Buscas salvas com vagas novas"). O valor 2 e sintetico.

Nao verificado:

- O teste CSS `body { zoom: 2 }` em 360 px (overflow 545/360) fica em `verification.json` como medicao informativa, sem assercao. Nao e zoom real do browser e nao valida reflow.
- Zoom real do browser, leitor de tela (a exposicao por papel foi medida pelo Playwright, nao ouvida), reduced-motion manual e dispositivos fisicos.
- CSS/JS de alguns templates continua minificado.

Filtros e acoes sao demonstrativos. Nao ha autenticacao, API, banco, publicacao ou persistencia. Nao interpretar estas capturas como aceite da SPEC.

## Marca Bateia

Conferencia visual e de pacote da marca Bateia (branch `feat/marca-bateia`, base 333167c), medida em 2026-10-20.

### Pacote (`npm run build` em `apps/web`)

- JS inicial: 216.86 kB gzip (768.32 kB bruto), um unico chunk `index-*.js`. Baseline vigente 215.83 kB (main em 01c7dfb, ja com Clerk): +1.03 kB, +0.48%; limite de +10% = 237.4 kB. Dentro do limite.
- O 150.07 kB citado no plano e o numero anterior ao Clerk e esta defasado; contra ele o crescimento seria +44.5%, mas a comparacao nao e valida, porque o Clerk entrou depois.
- CSS: 42.17 kB (8.82 kB gzip).
- Fontes `.woff2` emitidas: Schibsted Grotesk variavel 46 752 B + Young Serif 400 26 992 B = 73 744 B (73.74 kB). Apenas subconjunto latin.

### Captura

Os prototipos estaticos desta pasta (`capture-playwright.cjs`) nao exercitam o app real, entao eles nao foram reutilizados. Foi feito um runner novo, fora do repositorio e sem commit de capturas (scratchpad), com o Playwright de `tests/e2e/browser`:

- Build de Vite do app real, com `@clerk/react` e `@clerk/localizations` trocados por stubs (usuario assinado ou nao, controlado por flag) e a API simulada por `page.route` em `/api/*` com dados sinteticos. Nao e o build de producao: Clerk e backend reais nao foram usados. O CSS gerado e identico ao de producao (mesmo hash).
- Matriz: 11 caminhos (landing deslogada, Visao geral, Inbox, Detalhe da vaga, Pipeline, Perfil, Empresas, Detalhe da empresa, Fontes, Fila de homologacao, Status) x 5 larguras (320, 360, 768, 1280, 1440 px) x 2 temas (claro e escuro, via `localStorage` `bateia-theme`, confirmado em `data-theme`) = 110 capturas de pagina inteira.
- Dados sinteticos cobrem titulo longo (130 caracteres) e empresa com nome longo, os seis vereditos, a regua de pepitas e o fator desconhecido.

Resultados:

- Rolagem horizontal (`scrollWidth > clientWidth`): 0 de 110 capturas, inclusive 320 px nos dois temas.
- `pageerror`: 0. Requisicoes fora de 127.0.0.1: 0 (bloqueadas e registradas).
- Erros de console: 150, todos "404 Not Found" de endpoints que o runner nao simulou (`/analysis-metrics`, `/ai-budget`, `/source-metrics`, `/source-health`, `/source-coverage`, `/health/ready`, `/profile/versions`, `/profile/suggestions`, `/companies/:id`). Por isso Status, Fontes, Detalhe da empresa e Empresas mostram estado vazio ou de erro; o conteudo real dessas telas (WP5, nao migradas) nao foi avaliado.
- Inspecao visual de PNGs em 320 px: landing (BrandMark ao lado de "Entrar" e "Criar conta"), Inbox (regua de pepitas, chip de veredito, titulo longo) e Detalhe (titulo longo, regua, lista de fatores, tema escuro). Regua, veredito e titulo cabem sem corte; titulos longos quebram em varias linhas.

### Problemas encontrados

- Cabecalho da landing em 320 px: o botao "Criar conta" quebra em duas linhas. Cabe, sem rolagem, mas e uma quebra pouco elegante. Nao corrigido nesta tarefa. A inspecao foi feita em imagem reduzida; nao houve medicao do botao.
- `AuthenticationShell` em `apps/web/src/app/App.tsx` (telas de entrar e criar conta) ainda usa o quadrado com "O" em vez do BrandMark. As telas SignIn/SignUp nao foram capturadas (Clerk stubado). Nao corrigido.
- Nenhum defeito de layout (estouro horizontal, corte de texto) nas telas migradas.

### Nao verificado

- Leitor de tela, zoom real do navegador, aparelho fisico, reduced-motion manual.
- E2E com Docker, backend real e Clerk real (login, SignIn/SignUp, UserButton).
- Contraste visual do tema escuro alem do que `styles.test.ts` ja cobre; as capturas escuras foram so olhadas em amostra (Detalhe em 320 px).
- Telas WP5 (Empresas, Fontes, Homologacao, Perfil, Status) com dados reais; apenas rolagem horizontal e erros de pagina foram medidos.
- Fontes de producao em hospedagem real (cache, CSP).
