# CARD F20-25 — Fila de homologação

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-05](../../38-roadmap-ia-e-busca/fase-17/f17-05-fila-de-homologacao.md); [SPEC 37](../../37-spec-busca.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Dependências antigas F17-02, F17-04 e F17-07 são fechadas pelo F20-03.

## Resultado

O operador homologa dezenas de propostas em sequência numa única tela — testar,
revisar termos, habilitar, próxima — sem abrir fonte por fonte, e sem que nenhum passo do
gate seja pulado.

## Contexto

Com o F20-03 (antigo F17-04), o número de propostas sobe de 6 para algumas dezenas. A tela de fontes da
Fase 14 homologa uma por vez, abrindo o painel de cada cartão. A sonda do F14-06 impõe 60 s
entre testes da mesma fonte, não entre fontes diferentes.

## Escopo

- Visão **"Fila de homologação"** na tela de fontes: lista das propostas desabilitadas,
  ordenadas pela prioridade da empresa, com o estado de cada uma (sem sonda, sonda falhou,
  evidência confirmada, pronta para habilitar).
- **Modo sequencial:** mostra uma proposta por vez, com a empresa, a evidência da pesquisa,
  o link do board e três ações em ordem — "Testar o collector", "Termos revisados" com a
  data, "Habilitar" — e "Pular" / "Próxima".
- **Testar várias:** botão que sonda as propostas selecionadas uma de cada vez, respeitando
  `Retry-After` quando houver 429, com progresso e resultado por linha. Só a sonda roda
  em lote; termos e habilitação continuam um por um.
- Contadores no topo: quantas sem sonda, com sonda falha, confirmadas, habilitadas.

## Fora de escopo

- Marcar termos revisados ou habilitar em lote: é afirmação humana sobre cada fonte.
- Coletar logo após habilitar: o agendamento do worker cuida disso.

## Notas de implementação

- Usar as mesmas rotas do F14-02 e do F14-06; nenhum endpoint novo além, se preciso, de um
  filtro `?status=proposed` na listagem de fontes.
- O lote de sondas no frontend é sequencial (`for … await`), para não disparar requisições
  paralelas contra a API.
- As fontes habilitadas em massa só devem ir ao ar depois do F20-03 (antigo F17-02), para a Inbox filtrar
  as áreas; o card declara essa dependência e a tela avisa se o perfil não tem áreas de
  interesse.

## Critérios de aceite

- [ ] A fila lista as propostas por estado e prioridade.
- [ ] O modo sequencial leva de uma proposta à próxima sem voltar à lista.
- [ ] O lote de sondas respeita `Retry-After` e mostra o resultado de cada uma.
- [ ] Termos e habilitação nunca acontecem em lote.

## Verificação

- **CI:** testes de componente da fila (estados, sequência, lote com 429 simulado); teste do
  filtro de listagem, se criado.
- **Máquina de referência:** homologar as propostas do F20-03 (antigo F17-04) pela fila e registrar no PR
  quantas foram confirmadas e quantas falharam, com o motivo.

## Arquivos prováveis

- `apps/web/src/routes/SourcesPage.tsx`, `apps/web/src/components/HomologationQueue.tsx`
  (novo)
- `apps/web/src/features/sources/`
- `src/opportunity_radar/presentation/http/acquisition.py` (filtro, se preciso)

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
docker compose -p f20-25 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-25 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-25 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
