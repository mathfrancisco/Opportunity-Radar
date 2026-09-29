# Cards da integração Tavily

A [SPEC 41](../41-spec-tavily.md) define a integração com a API REST da Tavily:
descoberta web, extração de conteúdo e, depois, evidência para propostas de fonte.
Os cards são planejamento; aceite exige evidência no CI, conforme a convenção de
[`docs/33`](../33-roadmap-pos-mvp/README.md) e [`docs/34`](../34-roadmap-interface/README.md).

- [Fase 19 — Integração Tavily](fase-19/README.md): cinco cards.
- [Fases 16/17](../38-roadmap-ia-e-busca/README.md): base de IA, precisão e busca.
- [Fase 18](../40-roadmap-varredura-produtiva/README.md): varredura produtiva de sites.

## Ordem e escopo

F19-01 é a base: sem cliente, configuração e mapeamento de erro, nenhum outro card
tem o que chamar. F19-02 depende de F19-01 e entrega o coletor de descoberta.
F19-03 (orçamento de créditos) pode andar junto com F19-02, porque ambos tocam a
mesma execução, mas o orçamento não depende do coletor terminado — só do cliente.
F19-04 (extração com cache) depende do coletor existir para saber quais URLs faltam
corpo. F19-05 é o mais distante: só faz sentido depois que a Frente A da SPEC de
busca ([docs/37](../37-spec-busca.md), F17-04/F17-05) já sabe o que fazer com uma
proposta de fonte.

Nenhum card desta fase habilita fonte sem sonda e homologação — o mesmo gate de
`docs/17-fontes-coletores.md` vale para a Tavily como para qualquer outro coletor.
