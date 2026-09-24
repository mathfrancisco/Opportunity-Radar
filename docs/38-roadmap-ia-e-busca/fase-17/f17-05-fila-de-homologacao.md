# CARD F17-05 — Fila de homologação: propostas sem sonda, uma por vez

- **Status:** Backlog
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** F17-04, F17-02
- **Bloqueia:** Milestone P
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §4

## Resultado

O operador homologa dezenas de propostas em sequência numa única tela — testar,
revisar termos, habilitar, próxima — sem abrir fonte por fonte, e sem que nenhum passo do
gate seja pulado.

## Contexto

Com o F17-04, o número de propostas sobe de 6 para algumas dezenas. A tela de fontes da
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
- As fontes habilitadas em massa só devem ir ao ar depois do F17-02, para a Inbox filtrar
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
- **Máquina de referência:** homologar as propostas do F17-04 pela fila e registrar no PR
  quantas foram confirmadas e quantas falharam, com o motivo.

## Arquivos prováveis

- `apps/web/src/routes/SourcesPage.tsx`, `apps/web/src/components/HomologationQueue.tsx`
  (novo)
- `apps/web/src/features/sources/`
- `src/opportunity_radar/presentation/http/acquisition.py` (filtro, se preciso)
