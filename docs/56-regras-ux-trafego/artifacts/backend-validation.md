# Validação backend R56

## Estado da repetição integrada — 2026-10-18

**APROVADA.** A suíte backend completa da árvore atual terminou com `3181 passed, 10
skipped, 32 warnings in 635.11s (0:10:35)`. A saída integral está em
[`2026-10-18-r56-final-backend-current-tree.stdout.log`](2026-10-18-r56-final-backend-current-tree.stdout.log).
Esta é uma fotografia de validação local pré-publicação. Push e CI estão sendo
acompanhados no PR; a integração remota está em andamento e não é declarada concluída.

Uma execução RED anterior falhou por montagens parciais do harness: workflow ausente e
frontend antigo; registrou 5 falhas, 3175 aprovados e 11 skipped. Após corrigir a montagem
para usar o worktree completo somente leitura, os cinco testes de harness passaram em
3,12 s. O RED de harness não representa falha de produto. Uma fotografia backend anterior
ao patch de `html_text` teve 1 falha e 3176 aprovados, com 10 skipped; esse resultado
histórico está descrito abaixo.

Após a revisão do caso hostil de `html_text`, foi aplicado patch em
`src/opportunity_radar/platform/html_text.py`: uma abertura de tag só inicia o
parser quando há um terminador `>`. O teste de regressão correspondente está em
`tests/backend/platform/test_html_text.py`. O teste de `html_text` passou em 36 testes;
regressões de matching/normalização passaram em 28 testes. Separadamente, a suíte focada
de regiões, `test_content_rule_activation` e `test_domain` reportou `295 passed in 4.97s`;
esse resultado focado não substitui a suíte backend completa.

Na resolução de regiões, a execução red registrou 3 falhas e a green após correção
registrou 4 aprovados. Ruff raw terminou com `All checks passed!`; mypy raw terminou com
`Success: no issues found in 149 source files`. Esses checks não substituem a suíte
backend completa. Os logs raw são `2026-10-18-r56-final-post-regions-mypy.stdout.log`
e `2026-10-18-r56-final-post-regions-ruff.stdout.log`; os arquivos `final-mypy` e
`final-ruff` anteriores são saídas compactadas pelo RTK, não logs raw.

As amostras humanas continuam sem alteração: senioridade tem 300 entradas e 0
rotuladas; conteúdo tem 0/200 empregos rotulados. Nenhuma precisão foi medida.

## Prova histórica do backend — fotografia anterior ao patch de `html_text`

- Contêiner `r56-rules-ux-full-final`, imagem `f53-tenancy-api:latest`, comando `pytest -q -p no:cacheprovider`, mount do worktree em `/app` somente leitura. Início `2026-10-17 09:37:32 -03`; fim `09:44:08 -03`; exit code `0`.
- Resultado: `2728 passed, 10 skipped, 15 warnings in 390.97s (0:06:30)`. Output completo em [backend-validation-full-final-output.log](backend-validation-full-final-output.log); metadados e proveniência sanitizada em [backend-validation-full-final.log](backend-validation-full-final.log).
- A inspeção filtrada confirmou as guardas `RUN_DATABASE_INTEGRATION=1` e `DATABASE_INTEGRATION_ISOLATED=1`, banco `opportunity_radar_r56_test`, host `r56-postgres` e rede dedicada `r56-rules-ux-proof-20261017`. O contêiner PostgreSQL tinha `Mounts=[]`, diretório de dados em tmpfs de 1 GiB e nenhuma porta publicada; migrations no banco descartável terminaram com exit 0. Nenhum valor de conexão ou credencial foi registrado.
- SHA-256 dos arquivos cobertos pelo gate: `saved_searches.py` `020AC48ABEFCD520B6078F470419A9BBEFABAA4A69A1F94924F395915AF55C03`; `test_saved_searches.py` `016C2E2C27DA7F58667C64CF40529B7D23E0300B41AF5CA65CE62133E59A6DB8`.
- Os 10 skips não são individualizados pelo output quiet. Uma tentativa anterior foi intencionalmente interrompida a 42% após revisão identificar shapes de filtro adicionais; exit 137 e saída parcial foram preservados em [backend-validation-full-interrupted-shape-audit.log](backend-validation-full-interrupted-shape-audit.log) e não são tratados como gate aprovado.

## Evidência anterior recuperada

- Contêiner retido `r56gate-full-final`: `2728 passed, 10 skipped, 15 warnings in 522.82s`, exit 0, com as duas guardas e banco `_test`. A associação do banco a um Postgres descartável não pôde ser confirmada naquela rodada; a nova prova acima substitui essa lacuna para a validação final.

## Evidências anteriores

- Focados iniciais: `370 passed, 23 skipped`; Ruff passou; mypy: `Success: no issues found in 24 source files`.
- A primeira suíte ampla perdeu stdout por `docker run --rm`; cache preservou o teste que ainda interceptava listagem após a produção usar `count_opportunity_inbox`. Reteste retido: `1 passed in 5.26s`, exit 0.
- Suíte ampla anterior: `2726 passed, 10 skipped, 15 warnings in 540.22s`, exit 0.
- SQL `all_areas`: 0/1/20 buscas => 1/2/21 statements; 0,007038/0,056533/0,461196 s. Comparação Inbox legada: `6 passed in 5.15s`.
- Fallback de perfil ativo sem área: 1 busca => 4 statements (`1 passed in 3.95s`); `1 + N` não cobre esse caminho.
- Filtro legado inválido: item retorna `new_count: null`, `count_error: "invalid_filters"`; busca válida do mesmo owner preserva 1 (`17 passed in 5.91s`).
- Senioridade: v7, 300 entradas, 0 rotuladas, precisão nula. Conteúdo: gate bloqueado por ouro humano incompleto (0/200), sem mudança de gold.
