# CARD F20-35 — Mapa de cobertura e rendimento

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** D — Varredura produtiva
- **Depende de:** F20-01, F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-01](../../40-roadmap-varredura-produtiva/fase-18/f18-01-mapa-de-cobertura-e-rendimento.md); [SPEC 39](../../39-spec-varredura-produtiva.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Dependências antigas de F17 foram fechadas por F20-01 a F20-03.

## Resultado

Cada empresa mostra se está coberta, por que não está e qual é a próxima ação. O operador mede vagas únicas úteis por custo e atraso.

## Escopo

- Estender search-metrics com funil catálogo → descoberta → homologação → habilitação → coleta completa recente, contando empresas canônicas.
- Separar cobertura cadastrada de operacional e tipos ATS sem coletor. Guardar motivo, última tentativa e próxima ação por lacuna.
- Medir requisições, bytes, erros, vagas únicas novas, suporte de julgamento, rendimento útil, frescor e atraso de processamento; sem datas confiáveis, atraso de descoberta é null.
- Atribuição multifuente separa primeira descoberta e contribuição. Marcas ausentes não são negativas; comparar coortes/janelas iguais.
- Registrar baseline de sete dias e metas/tetos antes da mudança. Recall amostral usa snapshots manuais de boards estratificados, sem prometer recall global.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [ ] Fonte habilitada falhando não conta como operacional.
- [ ] Aliases e oportunidades multifuente não inflam totais.
- [ ] Cada métrica expõe janela, denominador, suporte e null quando indisponível.
- [ ] Relatório registra baseline, lacunas acionáveis e plano de comparação.

## Verificação

- **CI:** Fixtures de fontes saudáveis/falhas, aliases, multifuente, datas ausentes e marcas parciais; endpoint e apresentação no painel.
- **Máquina de referência:** Relatório de baseline e amostra manual dos boards; não executar nesta tarefa documental.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`dashboard/metrics.py`, `dashboard/queries.py`, API de dashboard, telas de empresas/fontes, migrations de métricas quando necessário.

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
docker compose -p f20-35 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-35 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-35 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
