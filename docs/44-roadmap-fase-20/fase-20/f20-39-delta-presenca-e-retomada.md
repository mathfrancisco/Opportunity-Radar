# CARD F20-39 — Delta, presença e retomada

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** D — Varredura produtiva
- **Depende de:** F20-38
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-05](../../40-roadmap-varredura-produtiva/fase-18/f18-05-delta-presenca-e-retomada.md); [SPEC 39](../../39-spec-varredura-produtiva.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Dependências antigas de F17 foram fechadas por F20-01 a F20-03.

## Resultado

Revisitar confirma presença sem duplicar conteúdo ou IA; queda de execução retoma sem perda e sem encerramento incorreto.

## Escopo

- Persistir observação por run/item mesmo quando dedupe reaproveita RawItem. Separar hash bruto e hash semântico versionado.
- Hash semântico remove só ruído definido; mudança material invalida derivados, mudança cosmética não obriga inferência.
- 304 só reutiliza inventário completo persistido se toda a representação/manifest de páginas foi revalidada no mesmo escopo; resto fica parcial/desconhecido.
- Commit atômico de evidência, observações e checkpoint. Cursores de retomada, rotação de termos e watermark são distintos.
- Nova rodada completa começa do início; replay antigo não regride last_seen/content e payload expirado permanece explicitamente indisponível.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [ ] Duas visitas iguais atualizam presença sem conteúdo/IA duplicados.
- [ ] 304 não fecha vaga nem mascara inventário incompleto.
- [ ] Quedas antes/depois do commit retomam idempotentemente.
- [ ] Mudança material reprocessa; alteração cosmética não gera onda de análise.

## Verificação

- **CI:** Falhas injetadas entre fetch/commit, cursor repetido, 304 parcial/completo, dedupe, replay fora de ordem e retenção.
- **Máquina de referência:** Medir proporção de bytes, normalizações e inferências evitadas, preservando recall amostral.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`acquisition/service.py`, repository/models, opportunities/service.py, migrations de observações e fixtures.

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
docker compose -p f20-39 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-39 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-39 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
