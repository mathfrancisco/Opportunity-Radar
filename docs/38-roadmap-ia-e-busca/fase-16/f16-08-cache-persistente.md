# CARD F16-08 — Cache persistente na tabela de análises

- **Status:** Em revisão
- **Fase:** 16 — Camada local de IA
- **Depende de:** F16-03
- **Bloqueia:** Nenhum
- **Origem:** [SPEC da camada de IA](../../36-spec-ollama.md), §6.4

## Resultado

Uma análise já feita para a mesma chave é reaproveitada depois de um reinício do worker,
sem chamar o modelo de novo.

## Contexto

O adaptador tem um LRU em memória de 256 entradas (`matching/ollama.py:44`), que morre a
cada reinício. A tabela `match_analysis` já guarda cada análise com a `cache_key`, que
cobre modelo, prompt, schema, versão da vaga e versão do perfil — mas ninguém consulta a
tabela antes de chamar o modelo.

## Escopo

- Em `MatchingService.analyze`, antes de chamar o adaptador: procurar a análise
  `AI_COMPLETED` mais recente com a mesma `cache_key` (índice
  `ix_match_analysis_cache_key` já existe).
- Encontrada: gravar uma linha nova para a avaliação atual copiando o conteúdo, com
  `detail = "reaproveitada da análise <id>"` e métricas `null` (não houve chamada).
- Não encontrada: fluxo atual (LRU em memória → modelo).
- Contador de reaproveitamento no log do job (`reused`).

## Fora de escopo

- Cache compartilhado entre máquinas.
- Expirar análises antigas: a chave já muda quando algo relevante muda.

## Notas de implementação

- A cópia é uma linha nova, não um ponteiro: a tabela é histórico append-only por
  avaliação, e cada avaliação precisa da sua linha.
- `ck_match_analysis_completed_payload` exige `summary`, `model_id` e
  `recommended_review` na linha `AI_COMPLETED`; a cópia carrega os três.

## Critérios de aceite

- [ ] Duas avaliações com a mesma chave geram uma chamada ao modelo, não duas, mesmo com
      reinício do worker entre elas.
- [ ] A linha reaproveitada identifica a origem e tem métricas nulas.
- [ ] O log do job conta os reaproveitamentos.

## Verificação

- **CI:** teste de integração com adaptador contador: analisar, recriar serviço e
  adaptador (simulando reinício), analisar outra avaliação de mesma chave, conferir uma
  chamada.

## Arquivos prováveis

- `src/opportunity_radar/matching/service.py`, `matching/repository.py`
- `tests/backend/matching/`
