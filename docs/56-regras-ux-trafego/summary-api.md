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
por grupo de postagem. A contagem usa a coluna de janela já calculada pela
consulta da Inbox e pede apenas a linha representativa que a carrega; ela não
materializa uma página de 200 oportunidades só para obter o total.

Com `all_areas: true`, o endpoint executa uma consulta de lista e uma consulta
de contagem por busca salva. Não existe cache global. Busca sem área explícita
consulta o perfil ativo para fallback; a medição isolada de uma busca observou quatro statements.

## Evidência executada

Os testes de integração cobrem equivalência para 0, 1 e 20 buscas salvas contra
o total independente da Inbox legada, incluindo filtros, perfil explícito, corte,
deduplicação da consulta legada, ordenação, vazio, isolamento por `owner_sub`,
autenticação obrigatória e a restrição `new_count >= 0`. O teste de instrumentação registra as consultas
SQL e só deve executar com `RUN_DATABASE_INTEGRATION=1`,
`DATABASE_INTEGRATION_ISOLATED=1` e uma `DATABASE_URL` cujo banco termina em
`_test`. Foram observados 1, 2 e 21 statements para 0, 1 e 20 buscas com
`all_areas: true`, em 0,007038 s, 0,056533 s e 0,461196 s.

## Gate backend observado

O contêiner `r56-rules-ux-full-final` executou `pytest -q -p no:cacheprovider` com
o worktree montado em `/app` somente leitura e terminou em `2026-10-17 09:44:08 -03`,
exit code `0`: `2728 passed, 10 skipped, 15 warnings in 390.97s`. A execução usou
ambas as guardas de integração e o banco `opportunity_radar_r56_test` em uma rede
Docker dedicada. O Postgres foi criado sem mounts, com dados em tmpfs e sem portas
publicadas; migrations terminaram com exit code `0`. Output integral e proveniência
sanitizada estão em
`docs/56-regras-ux-trafego/artifacts/backend-validation-full-final-output.log` e
`docs/56-regras-ux-trafego/artifacts/backend-validation-full-final.log`. O log quiet
não discrimina os motivos dos 10 skips.
