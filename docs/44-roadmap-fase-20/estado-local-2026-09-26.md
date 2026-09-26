# Estado local da Fase 20 — 2026-09-26

Trabalho consolidado no [PR #25](https://github.com/mathfrancisco/Opportunity-Radar/pull/25),
branch `feature/f20-groq-e-consolidacao`. Não representa fechamento da fase.

| Cards | Estado e evidência | Próximo passo |
| --- | --- | --- |
| 01 | baseline presente, mas enviesado/manual pendente | avaliação comparável |
| 02 | skills-v2 local em `e46b755` | F17-06 segue aberto: UNKNOWN 50,62% |
| 03 | implementado | validação final da fase |
| 04–11 | implementados | validação final da fase |
| 12 | corrigido em `b5072fd`: `settle()` direciona o restante reportado pelo provedor conforme `reset_requests_seconds`/`reset_tokens_seconds` (> 60 s: dia; <= 60 s: minuto; ausente: escopo desconhecido, não armazenado); migration `20260926_0034` adiciona `requests_ceiling`/`tokens_ceiling` nullable, gravados como menor valor absoluto observado e sem aumento na janela; `reserve()` aplica `LEAST(limite interno, teto)` | nenhuma pendência além da validação final da fase |
| 13–17 | implementados | validação final da fase |
| 18 | não iniciado; depende de 21 | executar depois da avaliação |
| 19–20 | implementados | validação final da fase |
| 21 | harness pronto (`2f5defd`, `94edd57`); casos locais carregam, mas a distribuição mínima não foi atingida; baseline real não executado | rotular as famílias curtas, revisar 41 descrições e executar o baseline Groq; registrar `docs/pesquisas/eval-analysis-groq-baseline.md` |
| 22–24 | pendentes | benchmark e contratos |
| 25 | implementado | validação final da fila |
| 26 | corrigido em `f6e4b16`: backend resolve o sobrevivente por `created_at` (empate pelo menor `id`) e publica `survivor_opportunity_id`/`absorbed_opportunity_id`; `confirm_duplicate` incrementa `version` quando move ocorrências/aplicações; normalização `MERGED` incrementa quando enriquecimento ou `search_skills` muda (no máximo uma vez por chamada; `NEW` não incrementa); UI invalida `['overview']` após confirmação | permitir nova sugestão de pares rejeitados após mudança material (recusa contextualizada por versão) e bloquear ciclo multi-hop em `confirm_duplicate` |
| 27 | código implementado | relatório real de descoberta por ATS |
| 28–32 | pendentes | termos/catálogo/prioridade antes de collectors |
| 33–35 | 33–34 pendentes; 35 implementado em `8a67d1a`, corrigido em `102a53d`, com evidências em `6606bf3` e `9d2dc5d`. `company_coverage_funnel` conta empresas canônicas distintas por etapa e usa `of_previous`; `enabled_but_unhealthy` inclui execução mais recente bem-sucedida, mas incompleta. `useful_yield_metrics` usa uma coorte de sobreviventes canônicos, exclui duplicatas absorvidas, limita marcas de relevância e contribuições de ocorrências à janela, valida datas de publicação contra a primeira observação canônica e informa taxas com suporte. Sem mínimo artificial de 20 marcas: 0% permanece 0; `None` só ocorre com denominador zero. Critério 4 aberto | critério 4: baseline de sete dias, alvos e tetos declarados, e plano comparativo na máquina de referência. Política ainda aberta: diante de datas de publicação confiáveis conflitantes, o atraso usa a mais antiga contra a primeira observação canônica. Verificações do implementador: 12 testes em `tests/backend/dashboard/test_coverage_funnel.py`; 53 em `tests/backend/dashboard` com `RUN_DATABASE_INTEGRATION=1`; `ruff check .` limpo; `mypy` limpo (108 arquivos) |
| 36–39 | pendentes | varredura e consolidação |
| 40 | implementado | validação final |
| 41 | round trip real implementado | manifesto não inclui novas tabelas AI |
| 42–45 | implementados | validação final |
| 46 | owner catalog/evidência implementados (`41a3ecf`, `fa93d15`) | adicionar regressão de falha real de flush |
| 47–50 | pendentes | implementar em ordem de dependência |

## Estado operacional

- `28bb03f` adiciona cliente PostgreSQL 17 ao CI e a variável de retenção. A execução
  `36251420005` falhou no gate de versão: 17 instalou, mas PATH ainda resolve o cliente
  16; o próximo patch deve antepor `/usr/lib/postgresql/17/bin` e gravá-lo em `GITHUB_PATH`.
- GitGuardian sinaliza duas ocorrências históricas de fixture bearer dummy. A evidência
  aponta falso positivo; não reescrever histórico. Falta a classificação no dashboard.
- O worktree antigo `.claude/worktrees/agent-ac111829ec6920204` foi apenas lido. Seus 50
  casos foram copiados para `prompts/opportunity_analysis/eval/cases/` no root; estão
  unstaged e excluídos por `.git/info/exclude`. O loader real carrega os 50 casos; os
  splits são `tuning` e `reserved`, e `group` é `sha256(company)[:12]` por definição
  (`scripts/export_eval_cases.py:113`), usado pela verificação de leakage em
  `matching/evaluation.py`. A auditoria não encontrou credenciais, e-mail, CPF, telefone
  ou link que não seja da vaga. `payload.profile_snapshot` contém exatamente `skills`,
  `countries`, `accepted_work_modes`, `accepted_contract_types`,
  `accepted_seniorities` e `work_authorization` (relevantes para os rótulos), além de
  `profile_version_id` e `evidence_refs` (valores placeholder zerados). 41 descrições
  com mais de 500 caracteres ainda precisam de revisão manual de nomes. A distribuição é
  backend 8, fullstack 3, `ai` 1, `fora_de_area` 19, `ineligible` 10 e synthetic 9; não
  atende ao mínimo de 10 para Java, fullstack, IA, fora de área e inelegível, e backend
  não comprova Java. O corpus local mediu 648 oportunidades, 1296 avaliações de match
  e 670 itens brutos; o filtro do exporter produziu 492 linhas `REVIEW_REQUIRED`, sem
  outros vereditos elegíveis, e não exporta `INELIGIBLE`. Os 492 drafts foram exportados
  para `prompts/opportunity_analysis/eval/drafts/` (gitignored, não versionados). A
  planilha `data/evals/labeling-worksheet-2026-09-26.csv` (gitignored) tem 110 linhas:
  os 50 casos existentes e 60 candidatos priorizados, com `family_proposed` e
  `expected_verdict_proposed` vazios para preenchimento do operador e coluna
  `needs_privacy_review`. Não copiar drafts às cegas. O harness já aceitava `--model`;
  agora uma recusa de quota marca `QUOTA_BLOCKED`, interrompe a execução e sai com 1.
  `--quota-wait-seconds` (padrão 0) ativa espera opcional; `94edd57` restaura essa
  opção, e o Makefile repassa `QUOTA_WAIT`. O baseline real foi deliberadamente
  adiado; faltam rótulos para as famílias curtas, as 41 revisões manuais, a execução
  Groq e `docs/pesquisas/eval-analysis-groq-baseline.md`.
- `worktrees/f20-21-eval` está sincronizado e reservado para a correção F20-12; o
  worktree `f20-41-ai-manifest` contém `432dd78`, já integrado no root como `28bb03f`.

## Ordem de continuidade

1. Corrigir F20-12 e os P2 de F20-26.
2. Auditar os casos e medir F20-21; então F20-18, F20-22 e F20-35.
3. Produzir o relatório de F20-27; fazer F20-28–32, F20-33–34, D e F20-23–24.
