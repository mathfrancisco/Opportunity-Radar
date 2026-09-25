# Fase 18 — Varredura produtiva de sites

> **Consolidado na [Fase 20](../../44-roadmap-fase-20/README.md).** O status oficial destes cards passa a ser o da Fase 20
> ([SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md)). Os cards abaixo seguem como referência de escopo.

[Escopo e contratos](../../39-spec-varredura-produtiva.md).
Objetivo: cobertura operacional, frescor e oportunidades úteis por custo,
sem transformar falha, ausência de marcação ou página inalterada em ausência de vaga.

| Card | Depende de | Status |
| --- | --- | --- |
| [F18-01 — Mapa de cobertura e rendimento](f18-01-mapa-de-cobertura-e-rendimento.md) | F17-01, F17-07 | Backlog |
| [F18-02 — Descoberta limitada de sites e sitemaps](f18-02-descoberta-limitada-de-sites.md) | F17-09, F18-01 | Backlog |
| [F18-03 — Coletor JobPosting público](f18-03-coletor-jobposting-publico.md) | F18-02, F17-02, F17-06, F17-07 | Backlog |
| [F18-04 — Agenda por rendimento e orçamento de rede](f18-04-agenda-adaptativa-e-http-condicional.md) | F18-01, F17-07 | Backlog |
| [F18-05 — Delta, presença e retomada](f18-05-delta-presenca-e-retomada.md) | F18-04, F17-07, F17-06 | Backlog |
| [F18-06 — Análise útil com IA sob orçamento](f18-06-analise-util-sob-orcamento.md) | F18-05, F16-07, F16-08 | Backlog |
| [F18-07 — Preservação integral do perfil](f18-07-preservacao-do-perfil.md) | Nenhum | Backlog |
| [F18-08 — Backup consistente e restauração verificável](f18-08-backup-consistente-e-restauracao.md) | Nenhum | Backlog |
| [F18-09 — Prova do fluxo e da produtividade](f18-09-prova-do-fluxo-e-produtividade.md) | F18-01 a F18-08, F17-03 | Backlog |

## Invariantes

- Descoberta propõe; homologação habilita. IA não navega nem aceita termos.
- Coleta parcial, 304 sem inventário validado e falha não provam encerramento.
- Presença, mudança de conteúdo e processamento são fatos distintos.
- Mais requisições ou vagas duplicadas não significam produtividade.
- Perfil, evidência e candidaturas sobrevivem a edição, migração e restauração.
- Sem Ollama, a varredura e a busca textual continuam utilizáveis.

## Encerramento

F18-09 consolida aceite por contrato e relatório real. Ganhos sem suporte são
inconclusivos. As metas de recursos/ganho são registradas antes da comparação,
com limites por host/provedor e caminho de rollback.
