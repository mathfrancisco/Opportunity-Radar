# CARD F16-11 — Contexto recuperado para a análise (RAG)

- **Status:** Backlog
- **Fase:** 16 — Camada local de IA
- **Depende de:** F16-06, F16-07, F16-09
- **Bloqueia:** Nenhum
- **Origem:** [SPEC da camada de IA](../../36-spec-ollama.md), §11, §11.1

## Resultado

A análise de uma vaga recebe as três vagas mais parecidas que já têm decisão do operador,
e comenta a vaga à luz dessas decisões — sem que isso mude score, veredito ou a
reprodutibilidade da análise.

## Contexto

Um modelo de 8B erra menos com o contexto certo entregue pronto do que procurando por
conta própria. O operador já decidiu vagas parecidas antes — abriu candidatura, descartou,
marcou relevância (F17-01). Hoje a análise não sabe nada disso. Chamada de ferramenta
pelo modelo foi descartada na SPEC §11: acrescenta turnos, latência e uma decisão não
determinística num fluxo que precisa ser reproduzível.

## Escopo

- **Recuperação:** pelos vetores do F16-09, as 3 vagas mais próximas que têm pelo menos uma
  decisão: candidatura (estágio atual ou encerramento), descarte, ou marcação de relevância
  do F17-01 quando existir.
- **Bloco `similar_decisions`** no payload: título, empresa, veredito e decisão de cada uma,
  com a similaridade.
- **Prompt `v3`** (ou `v2.1`, conforme a convenção de versão), com a instrução de usar o
  bloco para comentar e nunca para decidir. O schema continua sem score e sem veredito.
- **Reprodutibilidade:** os ids recuperados e o estado de decisão de cada um entram na
  `cache_key`. A análise grava os ids recebidos (`context_refs`, JSONB).
- **Gate:** só vira o padrão se o relatório do F16-06 mostrar melhora de cobertura ou
  fidelidade sem estourar a meta de latência da SPEC §3.2.

## Fora de escopo

- Chamada de ferramenta pelo modelo (function calling).
- Recuperar trechos de outras descrições para dentro do prompt.

## Notas de implementação

- Sem decisões suficientes no acervo, o bloco vai vazio, e o prompt precisa tratar vazio
  como "sem histórico", não como sinal.
- O orçamento do F16-05 passa a ter duas partes elásticas; o bloco recuperado tem teto
  fixo pequeno e vem antes da descrição na prioridade de corte.

## Limites de uso

Este card é opcional após o Milestone P e a varredura básica. Não bloqueia fonte
nova nem busca textual. Excluir própria vaga e duplicatas; recuperar decisões do
perfil compatível, sem interpretar ausência de candidatura como rejeição.
Persistir o snapshot das decisões, suas versões e hashes no payload da
`analysis-key-v2`, não apenas ids mutáveis. Avaliar com corte temporal: decisões
posteriores ao caso avaliado não podem entrar no contexto.

## Critérios de aceite

- [ ] O payload leva até 3 decisões parecidas, e a análise grava quais recebeu.
- [ ] Mudar a decisão de uma vaga recuperada muda a chave de cache.
- [ ] O relatório do F16-06 comparando com e sem o bloco está anexado.
- [ ] O padrão só muda se o relatório sustentar.

## Verificação

- **CI:** testes da recuperação com vetores e decisões fixos, da chave de cache com
  contexto e do payload com bloco vazio e cheio.
- **Máquina de referência:** `make eval-analysis` com e sem o bloco.

## Arquivos prováveis

- `src/opportunity_radar/matching/service.py`, `analysis.py`, `ollama.py`
- `src/opportunity_radar/opportunities/embeddings.py`
- `prompts/opportunity_analysis/v3/` (novo)
- `migrations/versions/*_analysis_context_refs.py`
