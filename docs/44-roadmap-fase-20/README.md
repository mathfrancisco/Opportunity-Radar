# Fase 20 — IA cloud no Groq e consolidação das fases 16 a 19

[Escopo e contratos](../43-spec-llm-cloud-e-consolidacao.md).

Objetivo: tirar toda a inferência da máquina local usando só o Groq e, na mesma fase,
fechar tudo o que ficou pendente nas fases 16 a 19. Cada card é autocontido: os cards
herdados trazem o escopo original copiado, com uma seção "Ajustes da Fase 20" no topo.
O status oficial passa a ser o desta fase.

## Cards

### Bloco A — Fechamento do que está em revisão

| Card | Depende de | Status |
| --- | --- | --- |
| [F20-01 — Baselines e relatórios da busca](fase-20/f20-01-baselines-e-relatorios-da-busca.md) | Nenhum | Backlog |
| [F20-02 — Curadoria manual de `skills-v2`](fase-20/f20-02-curadoria-skills-v2.md) | Nenhum | Backlog |
| [F20-03 — Conferência de aceite de F17-02, F17-04 e F17-07](fase-20/f20-03-conferencia-de-aceite-da-busca.md) | Nenhum | Backlog |

### Bloco B — IA cloud no Groq

| Card | Depende de | Status |
| --- | --- | --- |
| [F20-04 — Remover o Ollama do compose, da config e do worker](fase-20/f20-04-remover-ollama-do-compose-config-e-worker.md) | F20-17 | Backlog |
| [F20-05 — Remover os embeddings locais e a busca por significado](fase-20/f20-05-remover-embeddings-locais.md) | Nenhum | Backlog |
| [F20-06 — Health, doctor, scripts e testes sem Ollama](fase-20/f20-06-health-doctor-scripts-e-testes-sem-ollama.md) | F20-04, F20-05, F20-08 | Backlog |
| [F20-07 — Porta `LLMProvider` e `GroqProvider`](fase-20/f20-07-porta-llmprovider-e-groqprovider.md) | Nenhum | Backlog |
| [F20-08 — Configuração da IA cloud e segredos](fase-20/f20-08-configuracao-e-segredos.md) | F20-07 | Backlog |
| [F20-09 — Tarefas (`AITask`) e roteamento por tarefa](fase-20/f20-09-tarefas-e-roteamento.md) | F20-07, F20-08 | Backlog |
| [F20-10 — Retry com jitter e fallback entre modelos](fase-20/f20-10-retry-e-fallback-entre-modelos.md) | F20-09 | Backlog |
| [F20-11 — Circuit breaker por modelo](fase-20/f20-11-circuit-breaker-por-modelo.md) | F20-10 | Backlog |
| [F20-12 — Quota Guard persistente por modelo](fase-20/f20-12-quota-guard-persistente.md) | F20-10 | Backlog |
| [F20-13 — Token Guard por tarefa](fase-20/f20-13-token-guard-por-tarefa.md) | F20-09 | Backlog |
| [F20-14 — Saída estruturada: JSON Schema estrito e validação](fase-20/f20-14-saida-estruturada-e-validacao.md) | F20-07 | Backlog |
| [F20-15 — PII sanitizer e perfil mínimo](fase-20/f20-15-pii-sanitizer-e-perfil-minimo.md) | F20-07, F20-40 | Backlog |
| [F20-16 — Identidade de cache com provedor e rota](fase-20/f20-16-identidade-de-cache-com-provedor.md) | F20-17 | Backlog |
| [F20-17 — `GroqAnalysisAdapter` na porta de análise](fase-20/f20-17-groq-analysis-adapter.md) | F20-11, F20-12, F20-13, F20-14, F20-15 | Backlog |
| [F20-18 — Prompt `v2`: vaga e experiências no payload, pt-BR com evidência](fase-20/f20-18-prompt-v2-com-a-vaga.md) | F20-17, F20-21 | Backlog |
| [F20-19 — Telemetria de chamadas sem PII](fase-20/f20-19-telemetria-de-chamadas.md) | F20-17 | Backlog |
| [F20-20 — Métricas da IA na API, no Overview e no `doctor`](fase-20/f20-20-metricas-na-api-overview-e-doctor.md) | F20-19, F20-11, F20-12 | Backlog |
| [F20-21 — Conjunto de avaliação completo e baseline no Groq](fase-20/f20-21-conjunto-de-avaliacao-no-groq.md) | F20-17 | Backlog |
| [F20-22 — Benchmark 120B × 20B × Qwen e escolha por tarefa](fase-20/f20-22-benchmark-de-modelos.md) | F20-21 | Backlog |
| [F20-23 — Classificação e extração assistidas para campos ambíguos](fase-20/f20-23-classificacao-assistida.md) | F20-22, F20-02, F20-03 | Backlog |
| [F20-24 — Análise útil sob orçamento de quota](fase-20/f20-24-analise-util-sob-orcamento.md) | F20-39, F20-17, F20-16, F20-12 | Backlog |

### Bloco C — Busca: cobertura e precisão

| Card | Depende de | Status |
| --- | --- | --- |
| [F20-25 — Fila de homologação](fase-20/f20-25-fila-de-homologacao.md) | F20-03 | Backlog |
| [F20-26 — Candidato a duplicata (sem sinal vetorial)](fase-20/f20-26-candidato-a-duplicata.md) | F20-01 | Backlog |
| [F20-27 — Descoberta de ATS](fase-20/f20-27-descoberta-de-ats.md) | F20-03 | Backlog |
| [F20-28 — Coletor Workday](fase-20/f20-28-coletor-workday.md) | F20-27, F20-03 | Backlog |
| [F20-29 — Coletor Teamtailor](fase-20/f20-29-coletor-teamtailor.md) | F20-27, F20-03 | Backlog |
| [F20-30 — Coletor Workable](fase-20/f20-30-coletor-workable.md) | F20-27, F20-03 | Backlog |
| [F20-31 — Coletor Factorial](fase-20/f20-31-coletor-factorial.md) | F20-27, F20-03 | Backlog |
| [F20-32 — Coletor Gupy](fase-20/f20-32-coletor-gupy.md) | F20-27, F20-03 | Backlog |
| [F20-33 — Palavras-chave do perfil](fase-20/f20-33-palavras-chave-do-perfil.md) | F20-03, F20-40 | Backlog |
| [F20-34 — Buscas salvas](fase-20/f20-34-buscas-salvas.md) | F20-01 | Backlog |

### Bloco D — Varredura produtiva

| Card | Depende de | Status |
| --- | --- | --- |
| [F20-35 — Mapa de cobertura e rendimento](fase-20/f20-35-mapa-de-cobertura-e-rendimento.md) | F20-01, F20-03 | Backlog |
| [F20-36 — Descoberta limitada de sites e sitemaps](fase-20/f20-36-descoberta-limitada-de-sites.md) | F20-27, F20-35 | Backlog |
| [F20-37 — Coletor JobPosting público](fase-20/f20-37-coletor-jobposting-publico.md) | F20-36, F20-03 | Backlog |
| [F20-38 — Agenda por rendimento e orçamento de rede](fase-20/f20-38-agenda-adaptativa-e-http-condicional.md) | F20-35 | Backlog |
| [F20-39 — Delta, presença e retomada](fase-20/f20-39-delta-presenca-e-retomada.md) | F20-38 | Backlog |
| [F20-40 — Preservação integral do perfil](fase-20/f20-40-preservacao-do-perfil.md) | Nenhum | Parcial — `794b519`; conferir o restante |
| [F20-41 — Backup consistente e restauração verificável](fase-20/f20-41-backup-consistente-e-restauracao.md) | Nenhum | Backlog |

### Bloco E — Tavily

| Card | Depende de | Status |
| --- | --- | --- |
| [F20-42 — Cliente Tavily e configuração](fase-20/f20-42-tavily-cliente-e-configuracao.md) | Nenhum | Feito |
| [F20-43 — Orçamento de créditos Tavily e telemetria](fase-20/f20-43-tavily-orcamento-de-creditos.md) | F20-42 | Feito |
| [F20-44 — Collector de descoberta web](fase-20/f20-44-tavily-collector-de-descoberta-web.md) | F20-42, F20-43 | Feito |
| [F20-45 — Extração de conteúdo com cache](fase-20/f20-45-tavily-extracao-com-cache.md) | F20-44 | Backlog |
| [F20-46 — Evidência da Tavily para propostas de fonte](fase-20/f20-46-tavily-evidencia-para-propostas.md) | F20-44, F20-25 | Backlog |

### Bloco F — Encerramento

| Card | Depende de | Status |
| --- | --- | --- |
| [F20-47 — Percurso E2E no navegador com falhas injetadas](fase-20/f20-47-percurso-e2e-e-falhas-injetadas.md) | F20-17, F20-39, F20-40, F20-25 | Backlog |
| [F20-48 — Upgrade de banco populado e retomada de backfill](fase-20/f20-48-upgrade-de-banco-populado.md) | F20-41, F20-12, F20-19 | Backlog |
| [F20-49 — Relatório de produtividade e custo](fase-20/f20-49-relatorio-de-produtividade.md) | F20-47, F20-48 | Backlog |
| [F20-50 — Definition of Done da fase e documentação final](fase-20/f20-50-definition-of-done-e-docs.md) | F20-01 a F20-49 | Backlog |

## Ordem de execução

1. **A (F20-01 a 03), F20-40, F20-41** — fechar a busca em revisão, perfil e backup. Em
   paralelo com o bloco B.
2. **F20-05** — tirar embeddings locais (independente).
3. **F20-07 → F20-08 → F20-09** — porta, configuração e roteamento do Groq.
4. **F20-10, F20-13, F20-14, F20-15** em paralelo; depois **F20-11, F20-12**.
5. **F20-17** — adapter Groq ligado; depois **F20-16** (chave de cache).
6. **F20-04 → F20-06** — só agora remover o Ollama (o adapter novo já substitui o antigo).
7. **F20-19 → F20-20** e **F20-21 → F20-18, F20-22** — telemetria, métricas, avaliação, prompt `v2`, benchmark.
8. **C (F20-25 a 34)** e **D (F20-35 a 39)**, respeitando dependências.
9. **E (F20-42 a 46)** a qualquer momento após F20-42; F20-46 espera F20-25.
10. **F20-23, F20-24** — IA seletiva, depois do benchmark e do delta.
11. **F (F20-47 a 50)** — prova e encerramento.

A numeração identifica trabalho, não impõe sequência. Cada card lista suas dependências.

## Como um card é executado

- Cada card é uma branch e um PR: `feature/f20-NN-<slug>`.
- Ler o card inteiro, depois a SPEC 43 nas seções citadas em "Origem".
- Seguir "Passos" na ordem; "Não fazer" é regra, não sugestão.
- Rodar o "Comando de verificação" com `-p f20-NN` (projeto isolado) e colar a saída no PR.
- Migrações: usar o próximo número livre e `down_revision` = saída de `alembic heads`.
- Dúvida que o card não responde: parar e registrar a pergunta no PR, sem inventar.

## Correspondência com os cards antigos

| Antigo | Fase 20 |
| --- | --- |
| F16-01, F16-02, F16-04 | removidos (F20-04 a F20-06); fila por valor do F16-04 em F20-24 |
| F16-03, F16-13 | F20-19, F20-20 |
| F16-05 | F20-13 |
| F16-06 | F20-21 |
| F16-07 | F20-15, F20-18 |
| F16-08 | F20-16 |
| F16-09, F16-10, F16-11, F17-13 | fora da fase (sem embedding no Groq) |
| F16-12 | F20-22 |
| F17-01, F17-03 | F20-01 |
| F17-06 | F20-02 |
| F17-02, F17-04, F17-07 | F20-03 |
| F17-05, F17-08, F17-09 | F20-25, F20-26, F20-27 |
| F17-10 | F20-28 a F20-32 (um por ATS) |
| F17-11, F17-12 | F20-33, F20-34 |
| F18-01 a F18-05 | F20-35 a F20-39 |
| F18-06 | F20-24 |
| F18-07, F18-08 | F20-40, F20-41 |
| F18-09 | F20-47 a F20-49 |
| F19-01, F19-03, F19-02, F19-04, F19-05 | F20-42, F20-43, F20-44, F20-45, F20-46 |

IDs antigos citados dentro dos cards herdados seguem esta tabela.

## Invariantes

- a saída do modelo nunca altera elegibilidade, score, veredito nem fator;
- sem chave, sem quota ou com o Groq fora do ar, o radar funciona inteiro, sem comentário;
- nenhuma PII nem segredo vai para o Groq, para a Tavily ou para o log;
- nenhuma chamada real ao Groq ou à Tavily roda no CI;
- descoberta propõe, homologação habilita; coleta parcial não prova encerramento;
- toda troca de prompt ou modelo passa pelo conjunto de avaliação.

## Verificação na fase

Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.
O que depende de chave real ou do acervo real — benchmark, baseline, relatórios — roda na
máquina de referência e fica registrado no PR de cada card.
