# CARD F12-01 — Baseline e relatório de cobertura de fontes

- **Status:** Backlog
- **Fase:** 12 — Escala e qualidade de fontes
- **Depende de:** Fase 10 — coleta agendada com resultado por fonte
- **Bloqueia:** F12-05; métricas de cobertura da Fase 13
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§18, 20.1, 21–22 e item 52 da §30

## Resultado

Há um baseline e um relatório por rodada que mostram cobertura real da aquisição, sem
tratar empresa do catálogo como fonte executável nem ausência de itens como falha.

## Contexto

O catálogo contém empresas pesquisadas, enquanto a coleta executa apenas
`SourceDefinition` habilitada e elegível. Uma rodada parcial pode resultar de fonte não
homologada, desabilitada, bloqueada, pulada, falha ou retorno legítimo de zero vagas.

## Escopo

- Medir as sete definições atuais antes de expandir fontes.
- Registrar e exibir empresas no catálogo, fontes propostas, homologadas, habilitadas e
  elegíveis na rodada.
- Registrar por fonte elegível: sucesso, falha, bloqueio por configuração, skip e número
  de `RawItem` produzidos.
- Produzir baseline inicial e relatório reconciliável por rodada.
- Distinguir explicitamente fonte não habilitada, fonte que não executou e fonte executada
  com zero itens.
- Montar requests somente com parâmetros compatíveis com as capabilities declaradas pelo
  collector; por exemplo, keyword search apenas para fontes que o suportam.

## Fora de escopo

- Descobrir ou homologar novas fontes.
- Alterar a taxonomia de senioridade.
- Alertas e métricas agregadas de operação da Fase 13.

## Notas de implementação

- O relatório deve partir de `SourceDefinition` e `SourceRun`, não inferir cobertura a
  partir de oportunidades normalizadas.
- Preservar o estado de cada fonte selecionada, inclusive quando o collector não é
  chamado por incompatibilidade de request.
- A capacidade de busca por keyword deve ser consultada antes de montar a requisição;
  não enviar `--keywords` indiscriminadamente.

## Critérios de aceite

- [ ] O baseline cobre as sete definições atuais e identifica quais são executáveis.
- [ ] O relatório reconcilia catálogo, propostas, fontes habilitadas e cada fonte elegível
      na rodada.
- [ ] Sucesso, falha, bloqueio por configuração, skip, não habilitada e zero itens são
      estados distintos.
- [ ] Zero itens não é contabilizado como erro.
- [ ] Uma falha permanece isolada da execução das demais fontes.
- [ ] Requests respeitam as capabilities de cada collector.
- [ ] O relatório permite explicar por que uma busca não cobriu todas as fontes.

## Verificação

- Fixture com uma fonte em cada estado e as contagens reconciliadas no relatório.
- Rodada com keyword confirma que somente collectors compatíveis recebem o parâmetro.
- Revisão manual do baseline contra `SourceDefinition`, `SourceRun` e `RawItem`.

## Arquivos prováveis

- `scripts/collect.py`
- `src/opportunity_radar/acquisition/`
- `src/opportunity_radar/worker.py`
- `apps/web/src/routes/`
- testes de aquisição e dashboard correspondentes
