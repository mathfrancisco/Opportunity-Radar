# Revisão UX — fluxos prioritários

Este protótipo é uma proposta revisável anterior a qualquer mudança nas telas de produção. Os registros, nomes e contagens nele são fictícios. A navegação e o seletor de estados são demonstrações locais, sem API, fonte de web, telemetria ou gravação.

## Fluxos incluídos

1. **Inbox → oportunidade:** comparar prioridade, fatores conhecidos e desconhecidos; abrir uma oportunidade para consultar a origem e os detalhes. A prioridade e os fatores são apresentados como avaliação determinística, separada da análise semântica. Ação primária: abrir a oportunidade; o detalhe mantém a ação existente de registrar candidatura.
2. **Oportunidade → Pipeline:** passar ao acompanhamento da candidatura iniciada manualmente. A etapa pertence à candidatura e permanece conceitualmente separada do ciclo de vida da oportunidade.
3. **Pipeline → encerradas:** alternar candidaturas em andamento e encerradas manualmente. A regra das duas coletas completas consecutivas é explicada no detalhe da oportunidade: coleta parcial ou com falha não a encerra e outra fonte ativa que ainda a encontre a preserva. Quando a evidência persistida não está disponível, o texto diz isso explicitamente.
4. **Visão geral → Inbox/Pipeline:** mostrar somente tipos de contagem já expostos pelo Overview atual, com atalhos para as superfícies existentes. Os valores demonstrativos são fictícios e não propõem métricas novas.

## Problemas e proposta antes/depois

- **Modalidade e senioridade cruas na Inbox/filtro →** rótulos de leitura em português: Remoto, Híbrido, Presencial, Não informado; Estágio, Júnior, Pleno, Sênior, Staff, Liderança, Principal e Não informada. São apenas rótulos de interface, sem mudar enum ou filtro interno.
- **Prioridade sem contexto suficiente →** resumo da origem, frescor, fatores e desconhecidos ao lado da decisão; no detalhe, evidência e lacunas ficam visíveis. Valores de score e fatores servem somente de conteúdo fictício para revisar a hierarquia, não são recomendação real.
- **Falha, ausência ou atraso confundidos com vazio definitivo →** demonstrações nomeadas de carregamento, erro recuperável, vazio e dados desatualizados. Conteúdo anterior fica qualificado como histórico quando a avaliação é stale. O seletor é identificado como ferramenta do protótipo, não como recurso do produto.
- **Ciclo da vaga confundido com candidatura encerrada →** Pipeline representa as etapas manuais da candidatura. O detalhe da oportunidade explica a regra de duas coletas completas consecutivas e preservação por outra fonte ativa, sem transferir essa regra ao Pipeline.
- **Dúvida sobre atuação automática →** toda passagem para candidatura é manual; o protótipo não sugere autocandidatura ou alteração automática de perfil.

## O que preservar na implementação futura

- Rotas, deep links, URL e estado atual dos filtros; nomes internos dos enums e contratos de dados.
- Score, veredito, fatores, elegibilidade e análise semântica como conceitos existentes e separados; nenhum score/modelo ou ação automática nova.
- Estados e ações atuais de Inbox, detalhe, Pipeline e Overview; contagens do Overview ficam limitadas ao que a API/tela expõe atualmente.
- Identidade petróleo/ardósia, tokens de [DESIGN.md](../../DESIGN.md), densidade de lista, texto em português e estrutura sem redesenho integral ou biblioteca nova.
- Uma ação primária por contexto; navegação por teclado, foco visível de 3 px e alvos de pelo menos 44 px abaixo de 768 px são requisitos de implementação a validar, não resultados certificados por este protótipo.

## Arquivos de produção alterados após o aceite

- `apps/web/src/routes/InboxPage.tsx` e `InboxPage.test.tsx` — rótulos, orientação e atualização explícita.
- `apps/web/src/routes/OpportunityDetailPage.tsx` e `OpportunityDetailPage.test.tsx` — contexto da avaliação e posição do painel decisório.
- `apps/web/src/routes/PipelinePage.tsx` e `PipelinePage.test.tsx` — consulta sob demanda da aba e separação do encerramento manual.
- `apps/web/src/routes/OverviewPage.tsx` e `OverviewPage.test.tsx` — resumo agregado de buscas e estados de erro.
- `apps/web/src/routes/StatusPage.tsx` e `StatusPage.test.tsx` — não infere ambiente de execução pelo modo de build; usa “Ambiente não informado” sem configuração confiável.
- `apps/web/src/features/saved-searches/{api.ts,useSavedSearches.ts,api.test.ts}` — contrato aditivo do resumo e cache.
- `apps/web/src/features/opportunities/labels.ts` — rótulos compartilhados para modalidade e senioridade.
- `apps/web/src/routes/CompanyDetailPage.tsx` e `CompanyDetailPage.test.tsx` — revisão de configurações estruturadas com campos sensíveis omitidos.

## Aceite e aplicação

O protótipo [prototipo.html](prototipo.html) foi aprovado explicitamente pelo usuário antes das mudanças visuais de produção. A implementação enxuta preserva as rotas, ações, filtros e paginação. `GET /saved-searches/summary` acrescenta `new_count` inteiro não negativo para itens válidos; para busca legada com filtros inválidos, o contrato acordado retorna `new_count: null` e `count_error: "invalid_filters"`. A interface mostra essa contagem como indisponível, não soma `null` como zero e mantém as demais buscas da resposta. Os filtros booleanos e numéricos aceitos pelo backend são preservados.

Na Inbox, score, fatores desconhecidos, análise semântica e frescor têm orientação junto da lista, além dos rótulos em português. No detalhe, a decisão determinística e seus estados aparecem no painel ao lado das ações, antes da descrição; a análise semântica segue separada e consultiva. Pipeline carrega apenas a aba escolhida e mantém o encerramento da candidatura como ação manual. Overview consome um resumo agregado e distingue carregamento, erro recuperável e recurso desativado. Status mostra “Ambiente não informado”, pois o modo do bundle não comprova o ambiente da API. Configurações de revisão são resumidas por campos seguros, respeitando mascaramento.

## Evidência UX capturada

O runner `run-isolated-ux.mjs` montou Inbox, detalhe, Pipeline e Visão geral em viewport 360, 768 e 1440, mais erro recuperável no Inbox, estado desatualizado no detalhe, vazio no Pipeline e carregamento no Overview: 16 capturas. A Visão geral espera texto da fixture e dados renderizados antes da captura; detalhe espera `#decisao` e “Filtros eliminatórios”. O cenário loaded falha em alertas inesperados. As imagens estão em [ux-captures](ux-captures/), com proveniência em [report.json](ux-captures/report.json); uma comparação dos 12 estados carregados da base `a7f62e3` está em [baseline-a7f62e3](ux-captures/baseline-a7f62e3/).

Resultado da execução anterior à correção final: `screenshots: 16`, `failures: []`, `blockedRequests: []`, nenhuma rolagem horizontal, e nenhum controle tocável abaixo de 44×44 px em 360 px nas quatro rotas. A inspeção tabulada cobriu os oito primeiros pontos de foco na Inbox em 1440 px: skip link, marca e seis itens de navegação exibiram outline sólido de 3 px. A inspeção visual manual das quatro capturas móveis mostrou conteúdo legível e sem clipping evidente; isso é observação das imagens, não teste de leitor de tela ou de usabilidade com participantes. Essas capturas antecedem o patch final de `html_text` e não são replay da árvore atual.

A checagem de contraste calcula luminância relativa sRGB e `(LmaisClaro + 0,05) / (LmaisEscuro + 0,05)` a partir dos tokens CSS. Pares avaliados: `ink/canvas` 15,32:1, `subtle/canvas` 7,77:1, `muted/surface` 6,34:1, `danger-ink/danger-surface` 7,19:1, `warning-ink/warning-surface` 7,88:1 e `surface/accent` (texto de ação primária) 7,58:1; todos acima do limite nominal 4,5:1 usado para texto. Isso cobre apenas esses valores de token, não cada estado, combinação renderizada ou requisito WCAG.

A comparação visual usou um worktree detached em `a7f62e302dc7633a005c5e7ada66402e0fa71435`, com runner, configuração, fixture, shim Clerk e query client de suporte sobrepostos para igualar o método e as respostas. As mesmas 12 capturas carregadas apresentaram 18 alvos abaixo de 44 px na base: seis na Inbox, cinco no detalhe, um no Pipeline e seis no Overview. Depois dos ajustes móveis, a captura final encontrou zero em cada rota. Ao inspecionar as imagens, não observei clipping evidente em nenhuma das duas versões; essa observação não mede preferência nem desempenho de tarefa. A base e o resultado final não demonstram diferença de cache: a fixture não testa retry/frescor real, e seu `staleTime: 0` não comprova comportamento de dados em cache.

Os testes de Inbox verificaram deep link com filtros ativos e parâmetros correspondentes na API, paginação via `offset`, tamanho por URL/limite e reset da página ao filtrar; a implementação oferece 10/25/50/100 itens. A interação de busca continua submetida pelo formulário. Um teste com `createMemoryRouter` verifica voltar/avançar entre parâmetros de busca e filtro e sincronização do campo de busca com a URL; isso prova o histórico do Router em memória, não a integração manual com controles do navegador real. Os testes focados de Inbox, detalhe, Pipeline, Overview e resumo de buscas salvas passaram 67/67. `StatusPage.test.tsx` já verifica “Ambiente não informado”; a fixture visual de 16 capturas não inclui a página Status. Os textos visíveis das capturas estão em português, e não encontrei `[object Object]` nas capturas examinadas.

Comando da matriz (PowerShell; Node 24.19 do runtime local):

```powershell
$env:TEMP = (Join-Path (Resolve-Path 'docs/56-regras-ux-trafego').Path '.tmp')
$env:TMP = $env:TEMP
$env:UX_PLAYWRIGHT_MODULE = 'C:\Users\mathf\Documents\GitHub\Opportunity-Radar\tests\e2e\browser\node_modules\playwright\index.mjs'
$env:UX_BROWSER_EXECUTABLE = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
& 'C:\Users\mathf\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' docs/56-regras-ux-trafego/run-isolated-ux.mjs
```

Saída literal da execução final: `EXIT:0`. Testes focados, de `apps/web`:

```text
Test Files  4 passed (4)
Tests       62 passed (62)
```

Os caminhos de Edge, Playwright e Node 24.19 acima foram confirmados no host em 2026-10-18. O relatório da execução anterior registra HEAD `a7f62e302dc7633a005c5e7ada66402e0fa71435`, working tree dirty e SHA-256 do conteúdo-fonte analisado. As exclusões do hash são `docs/56-regras-ux-trafego/ux-captures/`, `docs/56-regras-ux-trafego/artifacts/`, `docs/56-regras-ux-trafego/.tmp/`, `apps/web/.tmp/`, `.validation/` e `.worktrees/`; o runner aplica as exclusões ao diff rastreado e à lista de arquivos não rastreados. O teste isolado de proveniência confirmou digest invariável ao mudar saída rastreada e digest diferente ao mudar fonte rastreada.

Clerk real, APIs externas, backend, dados/frescor de produção, leitores de tela, contraste de cada estado renderizado, zoom e teclado até o fim dos fluxos não foram exercitados. Os quatro estados especiais são respostas de fixture offline; o carregamento é deliberadamente mantido como fixture pendente e o cenário stale não prova comportamento de cache. Este documento não certifica conformidade WCAG, benchmark de usabilidade, build/lint/typecheck amplo nem conclusão da fase.

## Follow-up histórico de frontend — 2026-10-17

No checkout `C:\\Users\\mathf\\Documents\\GitHub\\Opportunity-Radar\\.worktrees\\r56-rules-ux-traffic`,
o campo de busca da Inbox passou a manter o rascunho local até o submit e a restaurar o
valor canônico da URL ao navegar pelo histórico. Ao aplicar uma busca salva sem `search`,
o rascunho é limpo explicitamente; mudanças comuns de filtro não o apagam. O teste de
regressão cobre esse caso e o histórico do Router continua coberto em
`InboxPage.test.tsx` (31 testes focados, saída 0 com Node 24.19).

O gate amplo `npm run check` concluiu com saída 0 após apontar `TEMP` e `TMP` para
`apps/web/.tmp`: lint, typecheck, 48 arquivos/431 testes Vitest e build passaram. A evidência
visual acima segue limitada às fixtures offline; o gate não certifica backend ou CI.

O snapshot de métricas gerado por esse check (`E680692F...AEA26C`) foi substituído pelo replay
estreito de tráfego: [`artifacts/request-metrics-final.json`](artifacts/request-metrics-final.json)
tem hash corrente `4AA64231...4EBE` e digest de fonte `a614db4f...b777`. A revisão independente
não encontrou issues nos manifestos, rotas, contagens e p50/p95. Há uma exceção explícita ao
orçamento de escrita: a interação Intake mantém `submitManualRun` seguido de `normalizeRun`,
portanto não se declara uma escrita por mutação nem aceite total de critérios. A saída e a
proveniência do frontend ficam em `artifacts/frontend-gate-dependencies.md`.

O gate backend do commit `abd3fbe` também terminou com saída 0 em banco efêmero isolado (`2728 passed`,
`10 skipped`, 15 avisos, 390.97 s). Essa evidência valida o escopo de backend exercitado, sem
transformar as fixtures UX em prova de dados de produção ou remover a exceção de duas escritas
do Intake. Este resultado é histórico e anterior aos patches SQL/Intake e à integração local de
`main`.

## Continuação de Intake e integração — 2026-10-18

O patch frontend local passou 49 testes em dois arquivos e lint; o backend teve 65 testes
aprovados e seis avisos em 13,95 s, com Ruff limpo. Esses resultados são pré-merge. A interação
usa um POST HTTP `manual-intake` para aquisição e normalização, mas pode realizar várias escritas
SQL. Falhas de normalização retornam erro estruturado com `run_id` para recuperação. Não se
conclui que há uma única escrita ou que os critérios de tráfego foram aceitos sem a validação
integrada.

A `main` inclui o cartão de orçamento de IA no Overview, elevando a medição histórica de quatro
GETs para um alvo integrado de cinco GETs. Regenere a matriz de tráfego e proveniência após a
integração. As 16 capturas, 35 testes de tráfego, 431 testes de frontend e 2.728 testes backend
registrados acima pertencem à evidência anterior ao patch; não validam os novos commits.

A evidência humana continua insuficiente para precisão de senioridade (300 amostras, nenhuma
rotulada) e conteúdo (0 de 200). Não declarar precisão, conformidade UX certificada ou conclusão
da fase com base nas capturas sintéticas.

## Gates integrados focais — fotografia anterior, 2026-10-18

`npm run check` integrado terminou com saída 0: lint/typecheck, 50 arquivos/479 testes e build
em 2,09 s, com aviso de chunk acima de 500 kB. Testes focados integrados registraram backend
304 aprovados, três avisos em 18,80 s, e frontend 84 aprovados. O gate completo de backend
continua pendente. Naquela fotografia, tráfego e UX ainda aguardavam regeneração/capturas na
árvore integrada. Não há confirmação de CI ou push atual.

## Replay UX integrado — fotografia anterior à correção, 2026-10-18

Uma execução posterior do runner gerou 16 capturas com Microsoft Edge instalado e respostas de
API offline. O relatório registra zero falhas e zero requests bloqueadas/inesperadas. A inspeção
coordenada cobriu desktop e mobile; no mobile verificou alvos de toque e no desktop percorreu
foco por teclado com outline de 3 px. Na fixture, o cartão de orçamento aparece como “Desligada”.
Relatório e imagens estão em [ux-captures](ux-captures/) e
[report.json](ux-captures/report.json). Isso é evidência sintética e visual, não comprova dados
de produção, acessibilidade WCAG ou usabilidade com participantes.

A proveniência desse replay é transitória: regenere capturas e digest global depois que a árvore
estabilizar. O patch para o teste hostil `html_text` foi aplicado posteriormente e a suíte backend
completa está **PENDENTE**. Não tratar essas capturas como validação visual final da árvore atual.

## Estado atual — 2026-10-18

O replay offline da árvore atual gerou 16 capturas no Microsoft Edge instalado, com
`failures: []` e `blockedRequests: []`. Não houve overflow horizontal; os quatro cenários
móveis não tiveram controles abaixo de 44×44 px, e os oito primeiros focos da Inbox em
1440 px mantiveram outline sólido de 3 px. A evidência está em [ux-captures](ux-captures/),
no [report.json](ux-captures/report.json) e no transcript
[2026-10-18-r56-final-ux.stdout.log](artifacts/2026-10-18-r56-final-ux.stdout.log).
Uma primeira tentativa revelou que Chokidar observava o perfil temporário do Edge dentro de
`apps/web/.tmp`; a configuração do fixture agora ignora esse diretório, mantendo `TEMP`/`TMP`
e os critérios de avaliação inalterados. O stdout da falha de readiness está preservado em
`artifacts/2026-10-18-r56-final-ux-css-diagnostic-red.stdout.log`.

O digest do workspace exclui os mesmos prefixos de artefatos do diff de arquivos rastreados
e não rastreados. A prova isolada confirmou que mudanças em capturas rastreadas não alteram
o hash e mudanças em fonte rastreada alteram. O gate backend local pré-publicação terminou
com `3181 passed, 10 skipped, 32 warnings in 635.11s (0:10:35)`; push e CI são acompanhados
no PR, sem afirmar integração remota concluída.

Uma tentativa de suíte backend completa teve cinco falhas de harness por montagens
parciais (workflow ausente e frontend antigo). Após corrigir a montagem para o worktree
completo somente leitura, cinco testes focados passaram em 3,12 s. Ruff raw terminou com
`All checks passed!` e mypy raw com `Success: no issues found in 149 source files`;
logs raw: `2026-10-18-r56-final-post-regions-ruff.stdout.log` e
`2026-10-18-r56-final-post-regions-mypy.stdout.log`. O gate backend local pré-publicação
passou com `3181 passed, 10 skipped, 32 warnings in 635.11s (0:10:35)`. Push e CI são
acompanhados no PR; a integração remota não é declarada concluída. O replay UX atual está
registrado na seção acima. Os limites humanos e de fixture descritos neste documento
permanecem aplicáveis.
