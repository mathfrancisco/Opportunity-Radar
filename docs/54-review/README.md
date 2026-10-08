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
