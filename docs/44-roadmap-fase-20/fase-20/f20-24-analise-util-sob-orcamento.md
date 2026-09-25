# CARD F20-24 — Análise útil sob orçamento de quota

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-39, F20-17, F20-16, F20-12
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-06](../../40-roadmap-varredura-produtiva/fase-18/f18-06-analise-util-sob-orcamento.md), [F16-04](../../38-roadmap-ia-e-busca/fase-16/f16-04-aquecimento-e-fila-por-valor.md)

## Ajustes da Fase 20

- O orçamento é a quota diária do Groq (F20-12), não tempo de GPU.
- Reservar parte da quota para análise pedida na UI; o worker nunca consome essa reserva.
- A fila por valor do F16-04 (elegível, score, frescor, prioridade da empresa) entra aqui; o aquecimento não.
- Arquivos: `src/opportunity_radar/worker.py` (`analyze_pending`), `src/opportunity_radar/matching/service.py` (seleção da fila), `src/opportunity_radar/matching/repository.py`, `src/opportunity_radar/platform/config.py` (`worker_analyze_batch_size`, `worker_analyze_verdicts`, novo `ai_interactive_reserve_requests: int = 100`), `src/opportunity_radar/platform/ai/quota.py` (reserva interativa).
- Reserva interativa: o worker chama `QuotaGuard.reserve` com teto `day_requests - ai_interactive_reserve_requests`; a análise pedida pela UI usa o limite cheio.
- Sugestões de campo deste card são as do F20-23; não criar outra tabela.
- Testes: `tests/backend/matching/test_analysis_queue.py` (ordem por valor, pulo sem mudança, reserva interativa) e `tests/backend/platform/ai/test_quota.py`.

## Resultado

A IA ajuda a decidir sobre vagas novas/alteradas e lacunas relevantes com evidência, dentro da quota diária do Groq.

## Escopo

- Usar identidade completa e reuso do F20-16; mesma vaga sem mudança não paga nova inferência.
- Priorizar recomendadas/alta prioridade e revisão com lacuna; aging e amostra de elegíveis pouco priorizadas avaliam perdas do funil.
- Orçamentos configuráveis de chamadas, tokens e tempo por ciclo/dia. Limite adia com motivo e registra custo de falhas.
- Sugestões de campo ficam separadas do canônico; aplicar exige revisão, trecho/origem e correção versionada. IA não muda score nem navega.
- Medir riscos/lacunas confirmados, falsos alertas, custo por análise útil e tempo humano por amostra. Não tratar clique ou ausência de candidatura como relevância.
- Rollback da política mantém análises históricas; sem Groq, coleta/matching/Inbox continuam.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [ ] Revisita sem mudança não chama IA; alteração material invalida reuso.
- [ ] Budget adia sem perder oportunidade nem bloquear o worker.
- [ ] Sugestão não altera campo/matching antes da confirmação.
- [ ] Relatório compara fila atual e política nova com suporte e custo/qualidade.

## Verificação

- **CI:** Adaptador contador, clock controlado, budget, aging, indisponibilidade e confirmação concorrente com expected_version.
- **Máquina de referência:** Amostra estratificada julgada pelo operador e carga real combinada; efeito sem suporte é inconclusivo.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`matching/service.py`, repository, worker, métricas e painel de análise; esquema separado de sugestões/correções.

## Não fazer

- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não habilitar fonte sem passar pelo gate de homologação.
- Não fazer chamada real a boards, Groq ou Tavily no CI; usar `httpx.MockTransport` ou os servidores falsos de `tests/e2e/`.
- Não adicionar dependência nova sem registrar o motivo no PR.
- Não usar LLM neste card, salvo quando a seção "Ajustes da Fase 20" disser o contrário.

## Como trabalhar este card

1. Ler "Ajustes da Fase 20" primeiro: eles prevalecem sobre o texto herdado.
2. Ler "Arquivos prováveis" e confirmar cada caminho com `ls`/`grep` antes de editar; caminho inexistente vira nota no PR.
3. Escrever primeiro os testes dos critérios de aceite, depois o código.
4. IDs antigos no texto aparecem como `F20-xx (antigo F1x-yy)`; a tabela completa está no README da Fase 20.
5. O que depende do acervo real ("Máquina de referência") é medido fora do CI e colado no PR.

## Comando de verificação

```bash
docker compose -p f20-24 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-24 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-24 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
