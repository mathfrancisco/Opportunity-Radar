# CARD F12-05 — Homologação e expansão para 20+ fontes

- **Status:** Backlog
- **Fase:** 12 — Escala e qualidade de fontes
- **Depende de:** F12-01, F12-02 e F12-03
- **Bloqueia:** Milestone K — Catálogo produtivo; Fase 13
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§19–22, milestone K e item 56 da §30

## Resultado

Vinte ou mais fontes estão habilitadas somente após homologação individual, com cobertura
e qualidade de senioridade mensuradas por fonte.

## Contexto

O catálogo de 220 empresas não é uma promessa de 220 integrações. A expansão precisa
começar pelo que é relevante e comprovável — CI&T (Lever), boards Greenhouse restantes e
uma segunda fonte remota — e manter a falha de cada fonte isolada.

## Escopo

- Priorizar CI&T (Lever), varredura de ATS detectável, boards Greenhouse adicionais e uma
  segunda fonte remota por feed ou query.
- Homologar individualmente endpoints, termos, collector e teste local antes de habilitar.
- Mapear campos de senioridade durante cada homologação usando F12-02.
- Habilitar vinte ou mais fontes aprovadas.
- Acompanhar expansão pelo relatório de cobertura do F12-01.

## Fora de escopo

- Habilitar automaticamente todas as propostas detectadas.
- Burlar termos de uso, rate limits ou gates de revisão.
- Tratar empresas catalogadas como fontes homologadas.
- Alterar o ciclo autônomo da Fase 10 ou os alertas da Fase 13.

## Notas de implementação

- Para cada fonte, a sequência é: evidência → revisão de termos → teste local do
  collector → homologação → habilitação.
- A fonte só pode receber request compatível com suas capabilities; keyword search não é
  universal.
- Uma fonte com zero vagas é saudável se executou com sucesso; ela não deve ser removida
  por ausência temporária de itens.

## Critérios de aceite

- [ ] Vinte ou mais fontes foram habilitadas após homologação individual.
- [ ] Cada fonte habilitada tem evidência, termos revisados e teste local registrados.
- [ ] A expansão preserva a distinção entre catálogo, proposta, homologada e habilitada.
- [ ] Campos de senioridade e mapeamento por collector foram registrados durante a
      homologação.
- [ ] O relatório mostra o resultado de cada fonte elegível em cada rodada.
- [ ] Falha de uma fonte não impede as demais.
- [ ] Requests enviados respeitam as capabilities de cada fonte.

## Verificação

- Checklist de homologação auditável para cada fonte habilitada.
- Rodada de coleta com fontes expandidas confirma isolamento de falha e estados de
  cobertura.
- Dashboard confirma distribuição de senioridade e taxa de `UNKNOWN` por fonte.

## Arquivos prováveis

- `scripts/discover_sources.py`
- `scripts/enable_sources.py`
- `scripts/collect.py`
- `src/opportunity_radar/acquisition/collectors/`
- `src/opportunity_radar/opportunities/`
- `apps/web/src/routes/`
- testes de aquisição, oportunidades e dashboard correspondentes
