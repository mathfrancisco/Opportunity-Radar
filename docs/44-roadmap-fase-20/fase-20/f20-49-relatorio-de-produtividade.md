# CARD F20-49 — Relatório de produtividade e custo

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** F — Encerramento
- **Depende de:** F20-47, F20-48
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-09](../../40-roadmap-varredura-produtiva/fase-18/f18-09-prova-do-fluxo-e-produtividade.md)

## Resultado

Sete dias de operação real mostram vagas úteis, frescor, cobertura e custo (rede, quota Groq, créditos Tavily) contra metas registradas antes.

## Contexto

As fontes de dado são: relatórios do F17-01 e F20-35, métricas do F20-20 e créditos do F20-43.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `docs/pesquisas/produtividade-fase-20.md` | metas, baseline, janela, resultado |

## Passos

1. Registrar metas no documento antes de começar (ex.: vagas úteis/dia, taxa de fallback < 5 %, 429 < 2 %).
2. Coletar 7 dias de baseline e 7 dias comparáveis.
3. Preencher: vagas úteis/dia, análises/dia, tokens/dia por modelo, taxa de fallback e 429, créditos Tavily, erros por tipo.
4. Marcar como inconclusivo todo efeito sem amostra suficiente.

## Não fazer

- Não usar dados sintéticos para declarar ganho.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] Relatório versionado com metas pré-registradas e resultados.

## Testes

- Nenhum teste novo.

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
