# CARD F12-03 — Descoberta de fontes com evidência

- **Status:** Backlog
- **Fase:** 12 — Escala e qualidade de fontes
- **Depende de:** Fase 10 — operação de coleta estável
- **Bloqueia:** F12-04; F12-05
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§19–22 e item 55 da §30

## Resultado

`scripts/discover_sources.py` varre empresas do catálogo e cria propostas idempotentes de
fonte, com evidência, sem habilitar nem homologar collectors.

## Contexto

Identificar um ATS não torna um endpoint seguro ou pronto para coleta. A descoberta reduz
trabalho de pesquisa, mas termos, teste local e habilitação precisam continuar decisões
explícitas.

## Escopo

- Criar `scripts/discover_sources.py` para varrer empresas do catálogo por ATS detectável.
- Registrar a evidência que sustenta cada proposta.
- Criar somente `SourceDefinition` proposta e desabilitada.
- Reportar empresa sem ATS detectável em vez de silenciá-la.
- Garantir reexecução idempotente, sem duplicar propostas.

## Fora de escopo

- Marcar termos como revisados.
- Testar localmente ou homologar collector.
- Habilitar fontes, coletar vagas ou alterar schedules.
- Criar a ação de UI do F12-04.

## Notas de implementação

- Toda proposta nova deve manter `reviewed_at` nulo, `terms_reviewed=false` e
  `collector_local_tested=false`.
- Evidência deve permitir auditoria humana do ATS, URL e método de detecção.
- Catálogo e propostas devem permanecer entidades distintas das fontes executáveis.

## Critérios de aceite

- [ ] O script propõe fontes sem habilitar nenhuma.
- [ ] Toda proposta contém a evidência que a sustenta.
- [ ] Empresas sem ATS detectável são reportadas explicitamente.
- [ ] Reexecução não duplica propostas.
- [ ] Propostas novas preservam o gate de termos e homologação.

## Verificação

- Fixture com ATS detectável gera uma única proposta desabilitada e auditável.
- Fixture sem ATS aparece no relatório do script.
- Segunda execução sobre os mesmos dados não cria nova proposta.

## Arquivos prováveis

- `scripts/discover_sources.py`
- `scripts/import_research_catalog.py`
- `src/opportunity_radar/acquisition/`
- testes de scripts e aquisição correspondentes
