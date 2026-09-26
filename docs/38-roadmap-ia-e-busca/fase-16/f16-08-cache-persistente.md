# CARD F16-08 — Cache persistente na tabela de análises

- **Status:** Base integrada (PR #20); identidade completa ainda pendente
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
cobre modelo, prompt, schema e versões. A consulta persistente já foi integrada;
o reforço pendente inclui payload efetivo e opções que alteram a resposta.

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
- Apagar análises antigas: as chaves antigas ficam auditáveis, sem reuso na nova versão.

## Notas de implementação

- A cópia é uma linha nova, não um ponteiro: a tabela é histórico append-only por
  avaliação, e cada avaliação precisa da sua linha.
- `ck_match_analysis_completed_payload` exige `summary`, `model_id` e
  `recommended_review` na linha `AI_COMPLETED`; a cópia carrega os três.

## Identidade ampliada

- `analysis-key-v2`: hash do payload final, prompt/schema efetivos, versões de
  perfil/vaga/regras/taxonomia, modelo resolvido e configuração de inferência
  (`num_ctx`, `num_predict`, `seed`, temperatura, amostragem e servidor).
- Uma única função define a chave usada no serviço, LRU e persistência.
  A consulta inicial por assessment só retorna resultado de identidade compatível.
- Alteração de corte, limpador ou contexto recuperado muda a chave se mudar a entrada.
- `refresh` e avaliação comparativa ignoram ambos os caches; falhas não são acertos.
- Linhas antigas não são apagadas nem reutilizadas como se fossem v2.

## Critérios de aceite

- [ ] Duas avaliações com a mesma chave geram uma chamada ao modelo, não duas, mesmo com
      reinício do worker entre elas.
- [ ] A linha reaproveitada identifica a origem e tem métricas nulas.
- [ ] O log do job conta os reaproveitamentos.

- [ ] Alterar opções, prompt efetivo, modelo resolvido ou payload impede reuso.
- [ ] Refresh e avaliação fazem chamada real mesmo com os dois caches preenchidos.
- [ ] A consulta por assessment não contorna a verificação da identidade.

## Verificação

- **CI:** teste de integração com adaptador contador: analisar, recriar serviço e
  adaptador (simulando reinício), analisar outra avaliação de mesma chave, conferir uma
  chamada.

## Arquivos prováveis

- `src/opportunity_radar/matching/service.py`, `matching/repository.py`
- `tests/backend/matching/`
