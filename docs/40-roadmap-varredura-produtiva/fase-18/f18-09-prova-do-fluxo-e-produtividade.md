# CARD F18-09 — Prova do fluxo e da produtividade

- **Status:** Backlog
- **Fase:** 18 — Varredura produtiva
- **Depende de:** F18-01 a F18-08, F17-03
- **Bloqueia:** Encerramento da Fase 18
- **Origem:** [SPEC 39](../../39-spec-varredura-produtiva.md), §10–11

## Resultado

O ciclo de varredura até candidatura tem prova pela interface, recuperação e relatório de utilidade/custo.

## Escopo

- Adicionar percurso mínimo de navegador no CI com API/boards/Ollama falsos: perfil completo → editar preferência → coleta → busca → análise → candidatura.
- Injetar paginação parcial, duas fontes discordantes, 304, erro de IA e restart nos pontos de confirmação; verificar ausência de perda/fechamento indevido.
- Exercitar upgrade de banco populado e retomada de backfill sem perder histórico; migração vazia sozinha não prova upgrade.
- Consolidar sete dias de baseline e janela comparável com metas pré-registradas. CI controlado prova contrato; relatório real prova produtividade.
- Atualizar docs/runbook com capacidades entregues, limitações e evidências; não marcar Done por existir código.

## Fora de escopo

- Ampliar para serviços distribuídos, IA remota ou coleta autenticada.
- Executar testes, migrações ou coletas reais nesta revisão documental.

## Critérios de aceite

- [ ] Percurso real de UI preserva perfil e cria candidatura sem terminal.
- [ ] Falhas/retomada não duplicam conteúdo nem encerram vaga ainda ativa.
- [ ] Upgrade/restore preservam histórico e permitem reprocessamento.
- [ ] Relatório mostra utilidade, frescor, cobertura e custo com suporte suficiente.

## Verificação

- **CI:** Executar cenários somente no pipeline.yml, usando dados determinísticos e anexando evidências do navegador.
- **Máquina de referência:** Relatório de produtividade e capacidade; não declarar ganho real a partir de dados sintéticos.
- Conforme AGENTS.md, validação local depende de pedido explícito.

## Arquivos prováveis

`.github/workflows/pipeline.yml`, tests/e2e, frontend, runbook e relatório em docs/pesquisas.
