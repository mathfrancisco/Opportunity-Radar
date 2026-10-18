# Summary de buscas salvas

## Contrato

`GET /saved-searches/summary` exige a mesma identidade autenticada das demais
rotas de buscas salvas. A resposta é uma lista de
`SavedSearchSummaryResponse`, que estende `SavedSearchResponse` com
`new_count: int | null` limitado a valores maiores ou iguais a zero quando presente.
`count_error` é `null` normalmente ou `"invalid_filters"` quando uma busca legada
não pode ser convertida em `InboxQuery`; nesse caso `new_count` é `null`, nunca zero.
Shapes incompatíveis em filtros conhecidos (incluindo busca, datas, coleções,
flags e limites numéricos não finitos) invalidam apenas o item correspondente;
campos desconhecidos continuam ignorados.

Cada item mantém `id`, `name`, `term`, `filters`, `last_opened_at` e
`created_at`. A lista preserva a ordenação existente: `created_at DESC`,
`id ASC`. `GET /saved-searches`, `GET /saved-searches/{id}/new-count` e as
rotas de escrita não mudam de contrato.

## Semântica da contagem

`new_count` continua sendo a contagem da mesma `InboxQuery` usada pela Inbox:
filtros salvos, corte `last_opened_at`, perfil do proprietário e deduplicação
por grupo de postagem. O patch SQL calcula as contagens por agregados condicionais
`COUNT DISTINCT`; não carrega uma página da Inbox para obter o total.

Na implementação anterior ao patch SQL, `all_areas: true` executava uma consulta
de lista e uma consulta de contagem por busca salva; sem cache global, 20 buscas
produziam 21 statements. Busca sem área explícita consultava o perfil ativo para
fallback; uma busca observou quatro statements.

## Evidência executada

Os testes da implementação anterior cobrem equivalência para 0, 1 e 20 buscas salvas contra
o total independente da Inbox legada, incluindo filtros, perfil explícito, corte,
deduplicação da consulta legada, ordenação, vazio, isolamento por `owner_sub`,
autenticação obrigatória e a restrição `new_count >= 0`. O teste de instrumentação registra as consultas
SQL e só deve executar com `RUN_DATABASE_INTEGRATION=1`,
`DATABASE_INTEGRATION_ISOLATED=1` e uma `DATABASE_URL` cujo banco termina em
`_test`. A medição histórica observou 1, 2 e 21 statements para 0, 1 e 20 buscas
com `all_areas: true`, em 0,007038 s, 0,056533 s e 0,461196 s.

## Patch SQL local — pré-merge, 2026-10-18

O patch agrupa contagens por `profile_version_id`, usa agregados condicionais
`COUNT DISTINCT`, compartilha fontes/aplicações e combina perfis com `UNION ALL`.
O fallback de perfil é resolvido uma vez. Filtros inválidos continuam isolados
por item como `new_count: null` e `count_error: "invalid_filters"`.

No benchmark sintético com 1.000 vagas, `all_areas` usou 1/2/2 statements para
0/1/20 buscas, contra 1/2/21 no caminho legado. O fallback ficou em quatro
statements para 1 e 20 buscas. Em 20 filtros variados, o legado executou 21 SQL
em 0,713900 s; o resumo executou 2 SQL em 0,092617 s. A igualdade de resultados
foi verificada nesse conjunto. A medição demonstra round trips reduzidos para
esses cenários; não demonstra custo de CPU ou latência constante.

Os testes PostgreSQL focados do patch tiveram 65 aprovações e seis avisos em
13,95 s; Ruff terminou limpo. São resultados pré-merge, não validação da árvore
integrada. O benchmark está registrado em
[`artifacts/saved-search-summary-sql-benchmark-2026-10-18.md`](artifacts/saved-search-summary-sql-benchmark-2026-10-18.md).

## Gate integrado focal — fotografia anterior

`npm run check` terminou com saída 0: lint/typecheck, 50 arquivos e 479 testes;
build em 2,09 s com aviso de chunk acima de 500 kB. Testes focados integrados
registraram 304 testes backend aprovados (três avisos, 18,80 s) e 84 frontend
aprovados. Essa fotografia focal é histórica e não substitui o gate completo atual
em [backend-validation.md](artifacts/backend-validation.md), nem confirma CI ou push.

## Evidência integrada anterior à correção final — fotografia de 2026-10-18

A matriz sintética atual registra uma chamada a `/saved-searches/summary` para
0, 5 e 20 buscas, além de 35/35 testes aprovados. O manifest registra HEAD
`c147ac5bf5aa3a07d258165374ae8ceeb0b0ce05` e árvore suja. Overview usa cinco
GETs em cada cardinalidade medida (0/5/20 buscas); Intake usa um POST e no máximo
um refetch por chave ativa afetada. Remount quente e TTL fresco não adicionam
GET; cinco minutos ocioso não adicionam polling. Os tempos continuam sendo de
fixture sintética, não latência real.

O gate backend completo integrado teve uma falha naquela árvore: 3.176 aprovados,
10 skipped e 32 avisos em 594,58 s. A falha isolada era o caso hostil de
`html_text`; o patch foi aplicado depois desta fotografia. A repetição completa da
árvore atual terminou aprovada, conforme [backend-validation.md](artifacts/backend-validation.md).
Isso não confirma CI ou push.

## Estado atual da validação — 2026-10-18

A mudança SQL e suas métricas permanecem a evidência de integração já registrada;
a suíte focada de `test_regions`, `test_content_rule_activation` e `test_domain`
reportou `295 passed in 4.97s`; separadamente, `test_html_text` passou 36 testes e
regressões de matching/normalização passaram 28. Esses resultados não são exclusivos
do endpoint de resumo. A revisão e o patch corretivo de
`html_text`, além da correção focada de regiões, têm seus resultados em
[regras-decisao.md](regras-decisao.md). Uma tentativa de suíte completa teve cinco
falhas de harness por montagens parciais (workflow ausente e frontend antigo); o RED
registrou 3175 aprovados e 11 skipped, antes da correção do setup. Corrigida a montagem
para o worktree completo somente leitura, cinco testes do harness passaram em 3,12 s.
A suíte backend completa atual terminou com `3181 passed, 10 skipped, 32 warnings in
635.11s (0:10:35)`; stdout em
[`artifacts/2026-10-18-r56-final-backend-current-tree.stdout.log`](artifacts/2026-10-18-r56-final-backend-current-tree.stdout.log).
Essa é validação local pré-publicação. Push e CI são acompanhados no PR; integração
remota em andamento, sem afirmar merge concluído.
Ruff raw terminou com `All checks passed!`; mypy raw terminou com
`Success: no issues found in 149 source files` (logs
`2026-10-18-r56-final-post-regions-ruff.stdout.log` e
`2026-10-18-r56-final-post-regions-mypy.stdout.log`). Os dados de senioridade
(300 amostras, 0 rotuladas) e conteúdo
(0/200) continuam insuficientes para alegar precisão.

## Gate backend observado

O gate do commit `abd3fbe` (anterior ao patch SQL) executou `pytest -q -p no:cacheprovider` com
o worktree montado em `/app` somente leitura e terminou em `2026-10-17 09:44:08 -03`,
exit code `0`: `2728 passed, 10 skipped, 15 warnings in 390.97s`. A execução usou
ambas as guardas de integração e o banco `opportunity_radar_r56_test` em uma rede
Docker dedicada. O Postgres foi criado sem mounts, com dados em tmpfs e sem portas
publicadas; migrations terminaram com exit code `0`. Output integral e proveniência
sanitizada estão em
`docs/56-regras-ux-trafego/artifacts/backend-validation-full-final-output.log` e
`docs/56-regras-ux-trafego/artifacts/backend-validation-full-final.log`. O log quiet
não discrimina os motivos dos 10 skips.
