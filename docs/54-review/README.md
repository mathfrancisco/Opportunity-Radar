# Revisao visual - SPEC 54

Estes arquivos sao prototipos estaticos com dados sinteticos. Nao fazem chamadas de rede, nao representam autenticacao e nenhuma acao persiste dados.

## Abrir e reproduzir

Abra `inbox.html` ou execute `node serve-local.mjs` e acesse `http://127.0.0.1:54154/`. O servidor atende somente loopback. `capture-playwright.cjs` gera as capturas locais; o runner PowerShell e legado.

## Estado verificado em 2026-10-07

- Os prototipos de Inbox, detalhe, Pipeline e Overview ainda aguardam aceite visual explicito.
- F53 esta adiada para F54 local. Hospedagem, Clerk, backup/restore e cutover nao estao implementados.
- Houve spikes descartaveis em `../54-spike`; nenhum kit foi aprovado ou selecionado.
- Os prototipos nao foram publicados nem conectados a dados ou servicos.

## Evidencia e limites

O relatorio local registra 44 capturas: 12 telas padrao (4 paginas em 1440, 768 e 360 px) e 32 estados (4 paginas em 1440 e 360 px), sem overflow nos viewports normais reportados. `verification.json` registra zero erros JavaScript; Escape fecha o menu movel e devolve o foco ao botao. O teste CSS `body { zoom: 2 }` em viewport 360 encontrou overflow: 545/360. Isso nao valida zoom real do browser. O runner nao afirma que falha diante de regressao.

Pendencias: o `thead` de `.inbox-table` some em mobile e remove cabecalhos de coluna para tecnologias assistivas; o runner precisa assertions que falhem por regressao; o timeout intermitente do seletor `[data-state]` segue sem causa diagnosticada. CSS/JS de alguns templates esta minificado. A Overview exibe "2 novas desde ultima abertura", dado possivelmente inexistente; mapear ao contrato ou remover antes da migracao. Leitor de tela, zoom real, reduced-motion e dispositivos fisicos nao foram validados manualmente.

Filtros e acoes sao demonstrativos. Nao ha autenticacao, API, banco, publicacao ou persistencia. Nao interpretar estas capturas como aceite da SPEC.