# CARD F12-02 — Senioridade com procedência e métricas UNKNOWN

- **Status:** Backlog
- **Fase:** 12 — Escala e qualidade de fontes
- **Depende de:** Fase 10 — coleta e normalização por fonte
- **Bloqueia:** F12-05; métricas de senioridade da Fase 13
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§18, 20.2, 21–22 e itens 53–54 da §30

## Resultado

Cada senioridade canônica tem procedência verificável por fonte, e o dashboard mostra a
distribuição completa, incluindo a taxa de `UNKNOWN`.

## Contexto

O classificador atual encontra senioridade principalmente no título. Isso concentra a
distribuição conhecida em `SENIOR`, mas não prova que as fontes devolveram apenas vagas
sênior: títulos sem nível e níveis numéricos permanecem `UNKNOWN`.

## Escopo

- Definir mapeamento versionado por collector de campos estruturados homologados para a
  taxonomia canônica.
- Aplicar a precedência: campo estruturado homologado, marcador explícito no título e,
  caso ausente ou conflitante, `UNKNOWN`.
- Persistir a procedência, valor externo e versão do mapeamento da classificação.
- Exibir contagem e percentual de todos os níveis por fonte, incluindo `UNKNOWN`.
- Criar métricas que separem senioridade conhecida de lacuna de classificação.

## Fora de escopo

- Inferir senioridade por texto livre da descrição.
- Converter níveis ambíguos por aproximação.
- Homologar ou habilitar novas fontes.

## Notas de implementação

- `Principal`, `Associate`, níveis numéricos e termos sem equivalência aprovada ficam
  `UNKNOWN`.
- `UNKNOWN` nunca recebe fallback implícito para `SENIOR`.
- O mapeamento deve ser documentado por collector e evoluir por versão, preservando a
  explicação de classificações históricas.

## Critérios de aceite

- [ ] Cada collector documenta campos estruturados usados e o mapeamento externo.
- [ ] A procedência e a versão do mapeamento acompanham cada classificação.
- [ ] `UNKNOWN` não é convertido implicitamente para `SENIOR`.
- [ ] Conflito entre campo estruturado e título resulta em `UNKNOWN`.
- [ ] Dashboard mostra contagem e percentual por fonte, com `UNKNOWN` visível.
- [ ] Fixtures cobrem `JUNIOR`, `MID`, `SENIOR`, `LEAD`, conflito e `UNKNOWN`.

## Verificação

- Testes unitários das regras de precedência e do mapeamento versionado.
- Fixture por collector confirma procedência e classificação esperada.
- Teste de read model confirma a taxa de `UNKNOWN` no dashboard.

## Arquivos prováveis

- `src/opportunity_radar/opportunities/`
- `src/opportunity_radar/acquisition/collectors/`
- `apps/web/src/routes/`
- migrations e testes de oportunidades/dashboard correspondentes
