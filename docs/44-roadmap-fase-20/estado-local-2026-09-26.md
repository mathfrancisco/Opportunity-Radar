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
| 21 | harness em `5c894c6`, 18 testes passaram | auditar/copiar 50 casos; snapshot parcial 14/50 concluídos e 36 falhos, revalidar após execução |
| 22–24 | pendentes | benchmark e contratos |
| 25 | implementado | validação final da fila |
| 26 | corrigido em `f6e4b16`: backend resolve o sobrevivente por `created_at` (empate pelo menor `id`) e publica `survivor_opportunity_id`/`absorbed_opportunity_id`; `confirm_duplicate` incrementa `version` quando move ocorrências/aplicações; normalização `MERGED` incrementa quando enriquecimento ou `search_skills` muda (no máximo uma vez por chamada; `NEW` não incrementa); UI invalida `['overview']` após confirmação | permitir nova sugestão de pares rejeitados após mudança material (recusa contextualizada por versão) e bloquear ciclo multi-hop em `confirm_duplicate` |
| 27 | código implementado | relatório real de descoberta por ATS |
| 28–32 | pendentes | termos/catálogo/prioridade antes de collectors |
| 33–35 | pendentes | métricas e funil |
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
- O worktree ativo antigo `.claude/worktrees/agent-ac111829ec6920204` executa o baseline
  F20-21; preservar sua execução e não copiar drafts. Seus 50 casos precisam de auditoria
  de privacidade antes de `git add -f` seletivo.
- `worktrees/f20-21-eval` está sincronizado e reservado para a correção F20-12; o
  worktree `f20-41-ai-manifest` contém `432dd78`, já integrado no root como `28bb03f`.

## Ordem de continuidade

1. Corrigir F20-12 e os P2 de F20-26.
2. Auditar os casos e medir F20-21; então F20-18, F20-22 e F20-35.
3. Produzir o relatório de F20-27; fazer F20-28–32, F20-33–34, D e F20-23–24.
