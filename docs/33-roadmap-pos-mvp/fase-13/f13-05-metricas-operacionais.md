# CARD F13-05 — Métricas operacionais de fonte

- **Status:** Concluído em 2026-09-22
- **Fase:** 13 — Operação contínua
- **Depende de:** F13-01, Fase 12
- **Bloqueia:** F13-06
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§24–26 e §§19–22

## Resultado

A API e a Overview mostram saúde, cobertura e qualidade de senioridade por fonte nas
últimas 24 horas e nos últimos sete dias.

## Contexto

Uma fonte com zero vagas não equivale a uma fonte que não executou. A concentração de
níveis conhecidos em `SENIOR` também não prova oferta exclusivamente sênior enquanto
`UNKNOWN` continua alto.

## Escopo

- Agregar itens por run, taxa de dedupe, latência p95 e taxa de erro por código.
- Exibir cobertura de execução e estados que distinguem sucesso vazio, falha, bloqueio,
  pulo e fonte não habilitada.
- Exibir senioridade conhecida e `UNKNOWN` por fonte, com contagem, percentual e
  procedência do mapeamento.
- Disponibilizar as duas janelas de 24 horas e sete dias na API e Overview.

## Fora de escopo

- Mudar a inferência de senioridade, converter `UNKNOWN` para `SENIOR`, telemetria
  externa ou dashboards de terceiros.

## Notas de implementação

Baseie agregados em execuções e ocorrências persistidas, não em logs. Exiba dados
insuficientes explicitamente. Mantenha a versão do mapeamento ou a origem do nível
junto da distribuição para evitar inferência sem procedência.

## Critérios de aceite

- [x] API entrega todas as métricas requeridas para 24 horas e sete dias.
- [x] Overview diferencia fonte saudável, degradada, vazia e não executada.
- [x] Taxa de erro é segmentada por código.
- [x] Cobertura permite separar ausência de vagas de falta de execução.
- [x] Senioridade mostra `UNKNOWN` sem conversão implícita.
- [x] Contagem, percentual e procedência aparecem por fonte.

## Verificação

Monte fixtures com sucesso vazio, falha por código, fonte pulada e níveis conhecidos e
desconhecidos; compare os agregados da API com a Overview nas duas janelas.

## Arquivos prováveis

- `src/opportunity_radar/acquisition/`
- `src/opportunity_radar/opportunities/`
- `src/opportunity_radar/api/`
- `apps/web/src/routes/`
