# Fase 20 — o que já fizemos e o que falta

Atualizado em 2026-09-28. Branch `feature/f20-groq-e-consolidacao` (PR #25), CI verde em
`13d6605` (backend, migrações, frontend, Compose E2E e Playwright).

"Verde na CI" prova o comportamento com fakes e fixtures. Por isso cada card abaixo separa
**código** (implementado e testado) de **validação real** (provado com dados, uso ou tempo
reais).

## 1. Restrições em vigor

| Restrição | Efeito |
| --- | --- |
| Janela de sete dias na stack real `opportunity-radar`, T0 `2026-09-28T12:01:55Z` (`evidencias/f20-janela-7d-t0-2026-09-28b.json`) | F20-35, F20-38 e F20-49 só fecham depois de `2026-10-05T12:02Z`. A stack não pode parar, ser reconstruída nem reiniciada até lá. |
| A stack real não tem `restart` no compose | Se o Docker cair, a stack para. Conferir uma vez por dia (`docker compose -p opportunity-radar ps`). Incidentes dentro da janela: Docker caiu ~`2026-09-28T16:20Z`, religado com `start` às 16:43Z; a leva agendada das 15Z só rodou às 16Z. |
| Cota diária do Groq ≈ 170k tokens, compartilhada com o worker da stack real (`AI_ENABLED=true`) | Uma rodada de avaliação por dia, logo após a virada UTC, conferindo o uso do dia antes. |
| Stack real roda o código de `0d55de6` | F20-23, F20-24 e o `work_mode` v6 só entram nela depois da janela. |

## 2. Já feito

### Cards fechados (código + validação real)

| Card | Evidência principal |
| --- | --- |
| F20-01 / F17-03 | Gabarito full-text de 128 candidatos; `recall@10` full-text 0,3396 > `like` 0,2745 (`rotulagem/f20-01-relevancia-busca-fulltext.md`). Os demais checkboxes do F17-03 dependem da suíte de integração da CI. |
| F20-03 a F20-11, F20-13 a F20-17, F20-19, F20-20, F20-25, F20-26, F20-40 a F20-46 | Implementados com teste e CI verde (ver `README.md`). |
| F20-21 | 50 casos versionados (10 por grupo); baseline real `openai/gpt-oss-120b`: 50/50, p50 1.613 ms, 74.545 tokens. |
| F20-27 a F20-31 | Descoberta de ATS e coletores Workday, Teamtailor, Workable e Factorial homologados em boards reais. |
| F20-32 | Fechado como não viável: os termos da Gupy proíbem agregação. |
| F20-33, F20-34 | Critério 4 conferido; testes de componente da Inbox e do Overview. |
| F20-36, F20-37 | Descoberta limitada e coletor JobPosting validados em sites reais; endpoints de Anthropic e Apollo GraphQL homologados. |
| F20-39 | Retomada real: corte de conexão real gerou `PARTIAL` (20 vagas Adobe) e `resume_of_run_id` retomou 15, sem duplicata; `kill -9` confirmou o commit atômico; variantes de parser (`0042`) aceitas; 304 real em Greenhouse e Teamtailor. |
| F20-47 | E2E no navegador com falhas injetadas, verde na CI. |
| F20-48 | Upgrade do backup real e backfill retomado em 7 lotes, sem duplicata. |

### Validações reais feitas em cards ainda abertos

| Card | O que foi provado |
| --- | --- |
| F20-02 | Alias `ci` removido; acervo real reprocessado para `skills-v3` (1.735 linhas, `cicd` 221 → 112), com backup verificado. |
| F20-18 | Prompt `v2` implementado; rodada real parcial (10/50) não justificou trocar. `v1` segue padrão. |
| F20-24 | Reserva interativa real: worker parou no teto (`skipped_budget=6`) e a análise pela UI concluiu. |
| F20-23 | Sugestões assistidas implementadas (desligadas por padrão); 30 vagas reais rotuladas (39 campos); regra `work_mode` corrigida (`13d6605`, normalizador `v6`): 11/13 casos resolvidos, 0 errado. |

### Correções que surgiram na validação

- Quota Guard esperava ~10 h numa quase-estouro por minuto (`21c5ec8`).
- Coletores Workday, Teamtailor, Workable e Factorial não eram montados em execuções agendadas; `make collect` usava registro incompleto.
- Parser Factorial rejeitava vagas sem time.
- Cobertura de ATS do dashboard ignorava os ATS novos (`d0d3101`).
- Soak e E2E com literais desatualizados (`skills-v1`, métricas do Ollama, `seniority-v1`, job opcional do F20-23).
- Stack real sem `schedule` em nenhuma fonte: nada era coletado desde 2026-09-26. Corrigido para `0 */3 * * *`; 3 fontes de teste desativadas.

## 3. Falta — rodadas com o Groq real (uma por dia)

| Ordem | Card | Tarefa | Critério |
| --- | --- | --- | --- |
| 1 | F20-23 | Rodar a classificação assistida contra os 30 casos rotulados (`rotulagem/f20-23-amostra-unknown.json`); script pontual a escrever | Precisão registrada; nenhum valor determinístico alterado. Só então ligar `worker_suggest_enabled`. |
| 2–6 | F20-22 | 120B médio; 20B baixo e médio; Qwen baixo e médio (comandos em `docs/pesquisas/benchmark-modelos-groq.md`) | Revisão humana por relatório (recomendações pré-autorizadas) e decisão por `scripts/benchmark_report.py`. |
| 7 | F20-18 | Comparação completa dos 50 casos, `v2` × `v1` | `coverage` e português sobem; `inventions` 0; nada piora no `reserved`. |
| 8 | F20-24 | Amostra de aging sob Groq real | Itens fora do topo processados na proporção configurada. |

## 4. Falta — depois de `2026-10-05T12:02Z`

1. Medir T7 na stack real: F20-35 (`/search-metrics?window=7d`), F20-38 (agenda adaptativa, bytes evitados por ETag) e F20-49 (cinco comandos de `docs/pesquisas/produtividade-fase-20.md`).
2. Reconstruir a stack real com o código atual e reprocessar o acervo para o normalizador `v6`.
3. Aplicar os endpoints de Anthropic e Apollo GraphQL e ativar as fontes.
4. Adicionar `restart: unless-stopped` ao compose.
5. Medir de novo o UNKNOWN de senioridade (meta do F17-06/F20-02: metade de 50,62%) com a `v6` e, se aprovado, as sugestões do F20-23.

## 5. Falta — sanidade e pendências menores

| Item | Estado |
| --- | --- |
| Testes instáveis por banco de teste compartilhado | Resolvido (`79d45c0`): 6 causas de vazamento entre testes corrigidas; 8 rodadas completas (ordem padrão + 7 sementes via `RANDOM_ORDER_SEED`) com 981 aprovados e 0 falhas |
| `alembic check` e head única (F20-05) | Resolvido (`79d45c0`): `env.py` sem `include_schemas=True` nunca comparava os schemas reais; corrigido, modelos alinhados ao banco (índices declarados, `ondelete` do modelo corrigido), head única `20260926_0052`, sem migração nova |
| F20-38: orçamento compartilhado entre duas fontes do mesmo host | Sem par real no catálogo; incluir um antes de medir |
| F20-36: board da Airbyte | `404` real; nova rodada de descoberta |
| API sem endpoint para editar `schedule` de fonte | Lacuna registrada |
| Fixture `pre_f20_dump.sql` com `normalizer_version` escrito à mão | Quebra a cada troca de versão; derivar da constante |
| Overview e Sources com ATS novos sem teste visual | Aberto |
| GitGuardian no PR #25 | Causa não confirmada |
| Rotacionar a chave Groq usada nas rodadas | Com o usuário |

## 6. Último card

**F20-50 — Definition of Done e documentação final.** Começa quando as seções 3, 4 e 5
estiverem fechadas; depois, merge do PR #25 na `main`.
