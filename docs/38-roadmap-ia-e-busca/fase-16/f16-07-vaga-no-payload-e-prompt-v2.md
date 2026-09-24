# CARD F16-07 — Vaga e experiências no payload, prompt `v2` em pt-BR com evidência

- **Status:** Backlog
- **Fase:** 16 — Camada local de IA
- **Depende de:** F16-05, F16-06
- **Bloqueia:** F16-11, F16-12
- **Origem:** [SPEC da camada de IA](../../36-spec-ollama.md), §4.1, §4.2, §4.3

## Resultado

O modelo lê a vaga — título, empresa, local e descrição limpa — e as experiências do
perfil, responde em português, e cada força ou risco vem com o trecho que o sustenta,
conferido por código.

## Contexto

Hoje o payload leva só o snapshot estruturado (`matching/service.py:372-410`): modo,
senioridade, contratos, skills, remuneração. Sem título nem descrição, o modelo não tem
como apontar exigência escondida no texto nem responsabilidade que não bate com o perfil.
O perfil vai sem experiências e projetos. O prompt está em inglês e não diz o idioma da
saída. É a maior perda de valor da camada (SPEC §2.1).

## Escopo

- **Bloco `posting`** no payload, separado do snapshot: `title`, `company_name`,
  `location_text`, `description` (limpa e orçada pelo F16-05) e `description_truncated`.
- **Reprodutibilidade:** `_analysis_request` hoje monta tudo a partir do estado persistido
  na avaliação. O `posting` vem da oportunidade no momento da análise, então a análise só
  roda se `opportunity.version == assessment.opportunity_version`; senão, é pulada com
  motivo — a reavaliação da vaga nova vai gerar outra avaliação. A análise grava o hash do
  `posting` enviado.
- **Perfil:** resumo das 5 experiências e projetos mais recentes — cargo, empresa, período,
  tecnologias, uma linha de descrição. Sem dados de contato.
- **Prompt `v2`** em `prompts/opportunity_analysis/v2/`: `system.md` em português,
  pedindo saída em pt-BR, apontando exigências ausentes do perfil e separando o que o
  anúncio afirma do que foi inferido; `user.md.j2` com a variável `posting`;
  `metadata.yaml` com `schema_version: analysis-v2`.
- **Schema `analysis-v2`:** `strengths` e `risks` viram listas de
  `{"claim": string, "evidence": string | null}`. `OUTPUT_SCHEMA_V2` em Python e
  `output.schema.json` gerado por `scripts/export_prompt_schema.py`.
- **Validador de evidência:** cada `evidence` não nulo precisa aparecer no payload enviado
  (comparação normalizada: minúsculas, espaços colapsados, sem pontuação de borda).
  Evidência inventada → `SCHEMA_MISMATCH`.
- **Seleção por configuração:** `OLLAMA_ANALYSIS_PROMPT` (`v1` | `v2`). O `v1` continua
  carregável. O padrão só muda para `v2` depois do relatório do F16-06.
- **Persistência e API:** as colunas JSONB de `strengths`/`risks` aceitam objetos; a API
  devolve objetos no `v2` e strings no `v1` (união tipada); a tela mostra a afirmação e,
  abaixo, o trecho entre aspas.

## Fora de escopo

- Contexto recuperado de vagas parecidas (F16-11).
- Poucos exemplos no prompt: só se o relatório mostrar ganho, e em outro PR.

## Notas de implementação

- `load_prompt` valida `schema_version` contra uma constante única hoje; passa a aceitar a
  versão declarada pelo diretório do prompt, com um schema por versão.
- `analysis_cache_key` já inclui `prompt_version` e `schema_version`: `v2` gera chaves
  novas sem regra nova.
- O `examples.json` do `v2` é reescrito no formato novo; os testes de `load_examples`
  validam cada exemplo contra o schema da própria versão.

## Critérios de aceite

- [ ] Com `v2`, o payload enviado contém o bloco `posting` e o resumo de experiências.
- [ ] Análise com evidência inexistente no payload é recusada como `SCHEMA_MISMATCH`.
- [ ] Análise de vaga cuja versão mudou depois da avaliação é pulada, com motivo gravado.
- [ ] `v1` e `v2` coexistem; a escolha é por configuração.
- [ ] O relatório do F16-06 com `v2` não piora nenhum critério em relação ao `v1` e
      melhora cobertura — só então o padrão passa a `v2`.

## Verificação

- **CI:** testes do payload `v2`, do validador de evidência (literal, normalizada,
  inventada), do loader com duas versões e da API com os dois formatos; E2E com o falso
  respondendo no formato da versão configurada.
- **Máquina de referência:** `make eval-analysis PROMPT=v2` comparado ao baseline `v1`,
  anexado ao PR.

## Arquivos prováveis

- `prompts/opportunity_analysis/v2/` (novo)
- `src/opportunity_radar/matching/analysis.py`, `prompts.py`, `ollama.py`, `service.py`
- `scripts/export_prompt_schema.py`
- `src/opportunity_radar/presentation/http/matching.py`
- `apps/web/src/features/matching/`, painel de análise
