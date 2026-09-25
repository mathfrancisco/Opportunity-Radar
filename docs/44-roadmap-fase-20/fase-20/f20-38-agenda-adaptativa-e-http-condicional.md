# CARD F20-38 — Agenda por rendimento e orçamento de rede

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** D — Varredura produtiva
- **Depende de:** F20-35
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-04](../../40-roadmap-varredura-produtiva/fase-18/f18-04-agenda-adaptativa-e-http-condicional.md); [SPEC 39](../../39-spec-varredura-produtiva.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Dependências antigas de F17 foram fechadas por F20-01 a F20-03.

## Resultado

A coleta revisita fontes pelo frescor e rendimento, respeitando limites agregados e sem abandonar fontes pouco observadas.

## Escopo

- Estender scheduler/política existentes com next_due_at, motivo, limites min/max e custo recente; persistir cooldown por host/provedor.
- Compartilhar orçamento entre coleta, probe e descoberta. Aging e reserva inicial de 10% para exploração evitam exclusão permanente; teto de política prevalece.
- Requisições condicionais por representação/escopo com ETag/Last-Modified; validar Vary, cache-control e configuração.
- 429/503 respeitam Retry-After em segundos/data, backoff/jitter e estado após restart; falha de uma fonte não bloqueia outras.
- 304 mantém semântica de revalidação, não ausência. Até F20-39 (antigo F18-05) comprovar manifest completo, não usar 304 para encerrar vaga.
- Não adaptar por falta de marcação humana; registrar plano e permitir rollback ao agendamento fixo.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [ ] Nenhum host excede orçamento ao combinar fontes, sondas e descoberta.
- [ ] Fonte pouco observada volta a ser visitada dentro do máximo configurado
      quando há capacidade; insuficiência de orçamento gera atraso explícito,
      sem violar limites do provedor.
- [ ] Cooldown sobrevive a reinício; Retry-After não é ignorado.
- [ ] Mesma coorte mantém cobertura/recall e reduz custo ou atraso medido.

## Verificação

- **CI:** Relógio controlado: concorrência por host, fairness, cooldown/restart, 304, validadores incompatíveis e rollback.
- **Máquina de referência:** Comparação de sete dias antes/depois com requisições, bytes, frescor e cobertura sob mesmos tetos.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`acquisition/scheduling.py`, política HTTP dos coletores, worker e migrations de estado de host/representação.

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
docker compose -p f20-38 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-38 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-38 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
