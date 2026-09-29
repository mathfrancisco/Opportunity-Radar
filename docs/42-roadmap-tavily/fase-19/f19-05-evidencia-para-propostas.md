# CARD F19-05 — Evidência para propostas de fonte

- **Status:** Backlog
- **Fase:** 19 — Integração Tavily
- **Depende de:** F19-02, F17-04, F17-05
- **Bloqueia:** Nenhum
- **Origem:** [SPEC 41](../../41-spec-tavily.md), §5, §9

## Resultado

Quando a Tavily encontra um resultado que aponta para um board de ATS já coberto pelo
radar (Ashby, Greenhouse, Lever) numa empresa sem `CompanySource` habilitada para esse
board, a evidência vira proposta de fonte na mesma fila que `scripts/discover_sources.py`
já alimenta — sem ingestão duplicada e sem pular sonda/homologação.

## Contexto

O F19-02 já marca esses resultados como `source_proposal_candidate` em vez de segui-los
como ingestão comum. Este card decide o que fazer com a marca: hoje ela não vira nada, e
a evidência se perde ao fim da execução.

## Escopo

- Rotina que lê os `CollectedItem` marcados `source_proposal_candidate=True` ao fim de
  uma execução da Tavily e cria (ou atualiza, se já existir e ainda estiver inerte) uma
  `SourceDefinition` proposta — mesmo formato de evidência que a F12-03 já usa: URL, ATS
  detectado, método de detecção (`"tavily_search"`), e o trecho que sustenta a
  identificação.
- Toda proposta nasce inerte: `terms_reviewed=false`, `collector_local_tested=false`,
  como qualquer proposta de `discover_sources.py` — este card não homologa nem habilita
  nada.
- Reexecução idempotente: a mesma URL/empresa não duplica proposta; evidência nova para
  uma proposta ainda inerte segue o mesmo caminho de correção que `proposals.py`
  (`follow_correction`) já define para propostas nascidas de `CompanySource`.
- Registro de qual via originou a proposta (Tavily vs. descoberta em HTML do F17-09 vs.
  varredura do F18-02), para poder medir taxa de acerto por via depois.

## Fora de escopo

- Marcar termos como revisados ou testar localmente.
- Homologar ou habilitar a fonte proposta.
- Ingestão da vaga encontrada como oportunidade — a Tavily não coleta o board inteiro,
  só aponta a existência dele; quem coleta é o collector nativo do ATS, depois de
  habilitado.
- Alterar a fila de homologação da F17-05 — este card só alimenta a mesma fila.

## Notas de implementação

- Reusar `IDENTIFIER_KEYS` de `acquisition/proposals.py` para extrair a chave do board a
  partir da URL, no mesmo padrão por ATS que a Frente A da SPEC de busca já define
  (`jobs.ashbyhq.com/<chave>`, `boards.greenhouse.io/<chave>`, `jobs.lever.co/<chave>`).
  Link fora do padrão não gera proposta automática — vira pendência, com o motivo, como
  a mesma Frente A já trata para links de pesquisa manual.
- A evidência guarda a consulta e o `rank`/`score` que a Tavily devolveu (metadata do
  F19-02), para auditoria de por que aquele resultado apareceu.
- Duas empresas diferentes apontando para o mesmo board por engano é erro de dado, não
  de proposta — a rotina não tenta resolver ambiguidade de empresa aqui.

## Critérios de aceite

- [ ] Resultado marcado `source_proposal_candidate` vira proposta inerte com evidência
      auditável (URL, ATS, método, trecho).
- [ ] Proposta nasce com `terms_reviewed=false` e `collector_local_tested=false`.
- [ ] Reexecução sobre o mesmo resultado não duplica proposta.
- [ ] URL fora do padrão de chave conhecido vira pendência registrada, não proposta
      malformada.
- [ ] A via de origem (Tavily) fica registrada na proposta, distinta de F17-09/F18-02.

## Verificação

- **CI:** fixture com URL de board conhecido gera uma única proposta inerte auditável;
  fixture com URL fora do padrão vira pendência; segunda execução sobre os mesmos dados
  não duplica; teste de idempotência com `proposals.py`.
- **Máquina de referência:** sem chamada real à Tavily; usa fixtures de `CollectedItem`
  já marcados pelo F19-02.

## Arquivos prováveis

- `src/opportunity_radar/acquisition/proposals.py`
- `src/opportunity_radar/acquisition/tavily.py`
- `scripts/discover_sources.py` (se a rotina reusar o mesmo script)
- `tests/acquisition/test_tavily_proposals.py` (novo)
