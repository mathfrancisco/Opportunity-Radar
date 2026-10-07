# SPEC 50 — estado da implementação

- **Atualizado em:** 2026-10-07 (seção "Sexta sessão")
- **Branch:** a SPEC 50 entrou em `main` pelo PR #26, mesclado em 2026-10-05 (`46ebbed`). A
  continuação está no PR #31 (`f50-fontes-e-inhire`, base `main`); ver "PR #31" abaixo. O que
  veio depois está em "PRs #32 a #37 e SPECs 51 e 52". Nada foi aplicado na stack
  `spec46full`.
- **Verificação:** suíte completa do backend na branch `f50-pendencias`, com integração em
  banco `_test` de um projeto Compose descartável, migrado até `20261005_0064`:
  `1776 passed, 16 skipped`; `ruff check .` e `mypy` sem erros. Os testes do frontend não
  rodaram localmente. No PR #31 a suíte tinha dado `1769 passed, 16 skipped`, e no PR #26,
  `1602 passed, 10 skipped`.

## Decisões do dono (2026-10-05)

- **Q1:** detalhe do Workday não revisado; construído atrás de flag por fonte, desligada.
- **Q2:** piso de 30%, medido nas três últimas execuções completas.
- **Q3:** sim, como na spec. Fuso e autorização de trabalho viram `NOT_APPLICABLE`; país
  desconhecido só bloqueia se o perfil marcar `sponsorship_required`.
- **Q4:** embeddings continuam desligados (registro no card F50-11 da spec).
- **Q5:** áreas-alvo `SOFTWARE_ENGINEERING` e `DATA`, contrato `full-time`.
- **F50-08:** liberar `DELETE` de avaliações para o job de poda foi aprovado.
- **F50-12.3:** gravar a vaga concorrente no motivo de revisão foi aprovado.

## Cards

| Card | Estado | Commit | Falta |
|---|---|---|---|
| F50-01 | Script e linha de base entregues | `06199c0`, `55a5adf` | Gold rotulado por pessoa: 200 vagas, 50 por fonte. Precisão não medida. |
| F50-02 | Mecânica entregue, nada ligado | `846fd74` | Gold passar no portão; depois preencher `GATED_RULES`, ligar as regras e reclassificar. |
| F50-03 | Entregue atrás de flag desligada | `8e8b82b` | Revisão de termos relida em 2026-10-05: veredito "a confirmar", flag continua desligada. Captura real da resposta de detalhe. |
| F50-04 | Entregue | `6e85c93` | Medir o aceite depois de três execuções completas por fonte. |
| F50-05 | Entregue | `3248382` | `ai` em 24,1% do catálogo, contra a meta de menos de 15% (simulação; não medido de novo depois do `retag_skills.py`). Amostra rotulada de 100 vagas. |
| F50-06 | Entregue | `954cdf0` | Aceite de 50% não sai só daqui: contrato e senioridade desconhecidos ainda seguram. |
| F50-07 | Entregue | `bce10f6` | `EXPLAIN ANALYZE` da fila em base de produção. |
| F50-08 | Entregue; ligado só na stack de dev | ver `git log` | Dry-run de 2026-10-05 na base de dev: 1.403 apagáveis de 66.648. Falta ver a primeira execução real do job e o `EXPLAIN` em volume real. O padrão do código continua desligado. |
| F50-09 | Entregue como `v3`, desligado por padrão | `bc6a4a3`, `514ffd2` | Funciona contra o Groq, mas não reduz a saída. Falta a avaliação de qualidade `v1` contra `v3`. |
| F50-10 | Entregue | `58d24a1`, `5ff2647` | `/inbox` em ~0,6 s na cópia de 25 mil vagas. Falta medir em produção. |
| F50-11 | Decisão registrada na spec | — | Nada. |
| F50-12 | Item 1 e gravação da concorrente entregues; itens 2 e 3 medidos | `51c7271`, `6f48ee2`, `0b585be` | Decisões do dono sobre duplicatas e revisões. |

## F50-08: como ficou

- A migração `20261005_0064` libera só `DELETE` em `match_assessment` e `match_factor`, e só
  em transação que ligue `matching.allow_prune`. `UPDATE` continua sempre recusado. Só o job
  de poda liga a opção.
- O job preserva: a avaliação mais recente por vaga e versão de perfil, toda avaliação
  apontada por `matching.current_assessment`, toda avaliação com análise de IA ou análise em
  andamento, e todas as avaliações de um par vaga e versão de perfil que tenha candidatura.
- O ponteiro escolhe a mais recente por versão da vaga e `assessed_at`; a poda usa
  `created_at`. Quando as duas ordens discordam, uma linha a mais fica guardada por vaga.
- Padrões: desligado no worker, 7 dias de retenção, lotes de 500. O script só apaga com
  `--apply`.
- Não medido: plano da consulta em volume real; o job nunca rodou contra dados reais.

## Pontos abertos por card

**F50-02**
- O script de reclassificação move o `fingerprint` junto com o modo de trabalho. Se outra
  vaga já tiver a identidade nova, o modo de trabalho daquela vaga fica como estava e o caso
  sai em `fingerprint_collisions` no relatório; o script não mescla nem cria revisão.
- O `fingerprint` novo vem da evidência bruta, não dos campos gravados. Se título ou empresa
  gravados estiverem defasados em relação à evidência, a identidade segue a evidência.
- Sem teste para o escopo padrão a partir das áreas-alvo do perfil ativo.

**F50-03**
- A fixture de detalhe é sintética. Se um tenant responder em outro formato, os detalhes
  contam como falha e as vagas ficam só com a listagem.
- Um 429 no detalhe interrompe os detalhes da execução, mas não grava cooldown do host.
- O cálculo do orçamento restante ignora um cooldown em vigor.
- Os contadores de detalhe ficam só na telemetria em memória.

**F50-04**
- A parcela por fonte usa as três últimas execuções completas, mesmo medidas com áreas-alvo
  antigas. Depois de trocar as áreas do perfil, o filtro leva até três execuções para refletir.
- As execuções do Hacker News agora terminam completas, então a fonte passa a poder fechar
  vagas que somem do tópico.

**F50-05**
- A palavra solta `ml` também saiu da regra de `ai`.
- Uma vaga que só cita LLM ou RAG recebe também `ai`.
- "React Native" também conta como `react`.
- Os identificadores novos têm espaço (`spring boot`, `react native`); um perfil que grave
  `springboot` não casa.

**F50-06**
- `RULES_VERSION` é `matching-v3`. Junto com `skills-v4`, invalida as avaliações uma vez.
- Na regressão, a elegibilidade continua 40 `UNKNOWN` e 10 `INELIGIBLE` em 50 casos.

**F50-07**
- Faixas de recência: até 3, 7, 14 e 30 dias, copiadas de `_recency_measurement`.
- `input_hash` ainda inclui o dia; uma avaliação manual em outro dia grava uma linha nova.
- A fila roda um `NOT EXISTS` por vaga elegível a cada passada. Custo não medido.
- No primeiro ciclo depois do deploy, toda vaga que cruzou uma faixa volta à fila uma vez.

**F50-09**
- Já existia um prompt `v2` (F20-18); o novo é `v3`, com base no `v1`.
- Tokens de entrada estimados: 1.058 no `v1`, 865 no `v3`, redução de 18%. A meta de 800 não
  foi atingida.
- Teto de saída de 600 tokens só com `v3`, não testado contra o provedor. Uma lista acima do
  limite falha em vez de ser cortada.

**F50-10**
- `connect_args` com `options` sobrescreve um `options=` que já esteja na `DATABASE_URL`, e
  um pooler em modo transação pode recusar esse parâmetro.
- Página vazia do Inbox usa uma segunda consulta para os totais.
- A API passa a ter um segundo pool de conexões, ao lado do que o adapter de análise usa.

**F50-12**
- Duplicatas `title_location_window`: 0 de 108 pares parece republicação; a regra não deve
  confirmar sozinha.
- `EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED` responde por 503 linhas. O grosso da fila são
  4.367 de `SAME_COMPANY_AND_TITLE_DIFFERENT_IDENTITY`, não medidas.
- Detalhes em [f50-12-duplicatas-e-identidade](../pesquisas/f50-12-duplicatas-e-identidade.md).

## Medições no `spec46full` (somente leitura, 2026-10-05)

- Cobertura das regras de conteúdo em 14.593 vagas com descrição: `seniority` 62,2%,
  `work_mode` 39,3%, `allowed_countries` 11,5%.
- Catálogo nas áreas-alvo: 27,7% (6.970 de 25.124).
- Vagas das áreas-alvo com descrição e ao menos uma skill pela taxonomia nova: 4.279 de 5.177
  (82,7%). Isso é teto para `TECHNOLOGY_FIT` conhecido, não a taxa do fator.

## PR #31: fontes e coletor inHire (2026-10-05)

Branch `f50-fontes-e-inhire`, base `main`. Não muda o esquema do banco; a última migração
continua `20261005_0064`.

- `robots.txt` lido com o `User-Agent` do produto, em `companies/discovery.py` e em
  `limited_discovery.py`; boards do Ashby com ponto no nome passam na validação.
- Todo coletor envia o `User-Agent` do produto.
- Rota `PATCH /sources/{id}/company-source`, que vincula uma fonte existente à fonte da
  empresa do mesmo tipo e board.
- Coletor `inhire`, com teto de 300 requisições por hora no host `api.inhire.app`.
- Revisões de termos de Ashby, Greenhouse e Lever, e fechamento da do inHire como "viável
  com ressalvas".

Fontes criadas, lote do inHire e pendências:
[f50-fontes-2026-10-05](../pesquisas/f50-fontes-2026-10-05.md).

## PRs #32 a #37 e SPECs 51 e 52 (2026-10-05 e 2026-10-06)

| PR | Branch | Estado | Conteúdo |
|---|---|---|---|
| #32 | `f50-pendencias` | Mesclado em `main` (`2e46f69`) | Link e releitura do inHire, `scripts/retag_skills.py`, pendências da SPEC 50. |
| #33 | `f50-tokenharbor` | Mesclado em `main` (`3e4aed8`) | Modelos gratuitos da Token Harbor como reserva do Groq. |
| #34 | `f50-inhire-ceiling` | Fechado, contido no #37 | Teto do host do inHire de 300 para 1.200 requisições por hora; padrão de 200 para 1.000. |
| #35 | `f52-spec-aderencia-ao-nivel` | Fechado, contido no #37 | Texto da SPEC 52. |
| #36 | `f50-inhire-lote-final` | Fechado, contido no #37 | Resultado final do lote do inHire em [f50-fontes-2026-10-05](../pesquisas/f50-fontes-2026-10-05.md). |
| #37 | `feat/f51-coleta-confiavel` | Aberto, base `main` | Junta #34, #35, #36 e o trabalho em andamento da SPEC 51. |

O PR #37 leva o esquema do banco de `20261005_0064` para `20261005_0067` (telemetria de
operações de IA, orçamento do Workday por host físico e contadores de detalhe, claims de
execução por fonte).

Verificação da branch do PR #37 em 2026-10-06, num projeto Compose descartável com banco
`_test`: `ruff check .` e `mypy` sem erros; `alembic upgrade head`, `downgrade base` e
`upgrade head` concluídos; suíte completa do backend com integração: `1843 passed, 10
skipped`. Os testes do frontend não rodaram localmente.

O que não cabe mais na SPEC 50 continua em duas specs:

- [SPEC 51 — coleta confiável e busca verificável](../51-spec-coleta-confiavel-e-busca.md):
  detalhe do Workday (pendência do F50-03), gold e ligação das regras de conteúdo (F50-01 e
  F50-02), worker, telemetria e fila de IA. Cards e ponto em que a implementação parou em
  [roadmap 51](../51-roadmap-coleta-confiavel/README.md) e no
  [checkpoint](../51-roadmap-coleta-confiavel/implementation-checkpoint.md).
- [SPEC 52 — aderência ao nível](../52-spec-aderencia-ao-nivel.md): classificador de
  senioridade, peso do nível na ordenação e oferta júnior/pleno remota. Proposta; nenhum card
  implementado.

## PRs #40 a #42 (2026-10-06)

| PR | Conteúdo | Estado |
|---|---|---|
| #40 | `seniority-v5` e `scripts/retag_seniority.py` (SPEC 52, F52-02); proposta de rótulo dos 300 títulos | Mesclado (`6ed1646`) |
| #41 | Amostra de 368 vagas do F50-01 versionada em `rotulagem/`, proposta de rótulos e leitor do gold que só conta casos com `revisado_por` (F51-11) | Mesclado (`f361884`) |
| #42 | `CLAUDE.md` versionado, `.claude/` no `.gitignore`, `matching-v4` em `docs/09-ddd-tatico.md` | Mesclado (`804e555`) |

- O gold do F50-01 continua sem rótulo confirmado. A proposta está em
  `rotulagem/f50-01-amostra-para-rotular-proposta.json`; o portão do F50-02/F51-11 segue
  fechado e `GATED_RULES` não mudou.
- O catálogo da stack de dev foi reclassificado para `seniority-v5`; ver a
  [SPEC 52](../52-spec-aderencia-ao-nivel.md), F52-02.
- Pendências que continuam sem card: a fila `REVIEW_REQUIRED` e as vagas sem skill
  (`skills-v5`). Não foram tratadas nesta sessão.
- Segunda sessão de 2026-10-06 (PRs #44 a #46): `skills-v5` (`linux`, `c++`, `etl`) mesclado
  e aplicado na base de dev; `matching-v5` (nível `UNKNOWN` para em `WATCHLIST`) mesclado, com
  a reavaliação do catálogo em curso; os 8 testes de fila foram reproduzidos e corrigidos. A
  fila `REVIEW_REQUIRED` continua sem tratamento. Detalhes na
  [SPEC 52](../52-spec-aderencia-ao-nivel.md), §4 (F52-05) e §5.

## Sessões de 2026-10-06 (terceira e quarta) e 2026-10-07 (quinta), PRs #48 a #68

Este arquivo não foi atualizado entre a segunda e a quinta sessão. O trabalho desse período é
das SPECs 51 e 52; o detalhe está no
[roadmap 51](../51-roadmap-coleta-confiavel/README.md), no
[checkpoint](../51-roadmap-coleta-confiavel/implementation-checkpoint.md) e na
[SPEC 52](../52-spec-aderencia-ao-nivel.md). O que toca a SPEC 50:

- **Gold do F50-01:** rótulos aprovados pelo dono (PRs #48 e #49). Nenhuma regra por
  descrição passou no portão; `GATED_RULES` não mudou. Uma amostra nova, com suporte, espera
  rótulo do dono (PR #60).
- **Fila `REVIEW_REQUIRED`:** tratada em 2026-10-07 (PR #67). De 5.607 linhas, 4.455 eram a
  mesma vaga publicada por cidade ou modo e foram resolvidas em lote; ficaram 1.152 para
  decisão caso a caso. Detalhe na SPEC 52, §5.
- **inHire:** as 98 fontes passaram a coletar de hora em hora (PR #66), depois de medir que
  230 de 244 requisições de detalhe de uma passada eram releitura de vaga já guardada.
- **Stack de dev:** em 2026-10-07 roda o `main` com os PRs até o #66; `seniority-v6`
  aplicado; 135 fontes de hora em hora, 98 do inHire de hora em hora, 18 a cada 6 horas.

## Sexta sessão (2026-10-07), PRs #69 e #70

Nenhuma mudança em `src`. O detalhe está no
[roadmap 51](../51-roadmap-coleta-confiavel/README.md), no
[checkpoint](../51-roadmap-coleta-confiavel/implementation-checkpoint.md) e na
[SPEC 52](../52-spec-aderencia-ao-nivel.md).

- **SPEC 51:** o PR #70 só traz testes, para dez critérios de aceite que estavam sem
  cobertura completa; os cards trazem o nome do teste de cada critério. O merge reabriu a
  janela de sete dias do F51-18: abre em 2026-10-07 14:28:49 UTC e fecha em 2026-10-14
  14:28:49 UTC. Nenhum card da SPEC 51 está concluído.
- **F52-06, oferta júnior/pleno:** 159 empresas brasileiras com board no inHire foram
  curadas, cadastradas pela API do produto e habilitadas em cinco lotes de hora em hora. Em
  2026-10-07, 18h14 UTC: 530 vagas `JUNIOR` ou `MID` nas áreas-alvo (eram 369 às 13h40 UTC),
  contra a meta de 600. Faltam 70; o card continua aberto. Relatório por fonte em
  [f52-06-vagas-do-nivel-por-fonte-2026-10-07.md](../pesquisas/f52-06-vagas-do-nivel-por-fonte-2026-10-07.md).
- **Termos:** Quickin a confirmar; Sólides e Recrutei não viáveis hoje. Nenhum coletor novo.
- **Fila `REVIEW_REQUIRED`:** 1.370 linhas às 18h14 UTC; cresce com a coleta. Proposta de
  regra por motivo em
  [fila-review-required-proposta-2026-10-07.md](../pesquisas/fila-review-required-proposta-2026-10-07.md),
  à espera de decisão do dono. Nada foi resolvido.
- **Stack de dev:** roda o `main` em `3aaca63`. O catálogo tem 522 empresas, 408 com fonte
  habilitada. São 257 fontes inHire, todas de hora em hora; ao todo, 392 fontes de hora em
  hora. A passada horária do inHire faz cerca de 260 requisições de lista, mais o detalhe
  das vagas novas.
- **Vistos e não tratados:** a fonte Greenhouse da HubSpot falhou com `404`
  (`SOURCE_NOT_FOUND`) em todas as execuções de 2026-10-07. A execução da Accenture no
  Workday terminou `PARTIAL` com `PARSER_SCHEMA_CHANGED` às 13h25 UTC; a agenda dela é
  diária, às 06h00 UTC, e a execução seguinte não tinha ocorrido no fim da sessão.
- **Dependem do dono:** F51-09 AC01, F51-10 AC04, o risco de fechamento por dois `304`
  seguidos no F51-13 e as regras A, B e C da fila de revisão. Continuam bloqueados: rótulos
  da amostra (F51-11, F52-03, F52-07), aprovação Workday nos 5 tenants (F51-03, F51-05), gold
  de busca com dois revisores (F51-17), definição de "resultado útil" (F51-12 AC06) e
  amostra humana de recall (F51-02).

## Stack de desenvolvimento `opportunity-radar-dev`

É a base local de trabalho: o código do checkout sobre o catálogo real, em volumes próprios.
API em `127.0.0.1:8000`, frontend em `127.0.0.1:3000`. Todo comando leva
`-p opportunity-radar-dev -f compose.yaml`. Operação em
[30-runbook](../30-runbook.md), seção "Stack de desenvolvimento com a base real".

- O banco foi criado em 2026-10-05 a partir de um `pg_dump` do volume
  `opportunity-radar-recovery-a7a43`, que ficou intacto como cópia do estado anterior à
  SPEC 50.
- As fontes novas de 2026-10-05 entraram nessa base, pela API do produto.
- Continuam desligados nela: as regras de classificação por descrição e o `fetch_detail` do
  Workday. A poda de avaliações foi ligada nela em 2026-10-05, depois do dry-run.
- O catálogo dela está inteiro em `skills-v4` desde 2026-10-05 (`scripts/retag_skills.py`).
- Experimentos que alteram dados vão para uma stack descartável com outro nome de projeto,
  não para esta.

## Medições na stack de teste `f50test` (2026-10-05, stack removida)

A `f50test` foi removida em 2026-10-05, depois de as fontes entrarem na base de dev. Os
números desta seção ficam como registro; não dá mais para repeti-los nela.

Era uma stack local com o código da branch e uma cópia do banco da `spec46full` (25.267
vagas), migrada até `20261005_0064`, com API em `127.0.0.1:8001` e frontend em
`127.0.0.1:3001`.

Estavam ligados nela: `AI_ANALYSIS_PROMPT=v3`, `WORKER_ASSESSMENT_RETENTION_ENABLED=true`,
piso de coleta 0,30, timeout de consulta, e as seis regras de classificação por descrição. As
regras foram ligadas só nessa cópia, sem o portão de 90% ter passado. O `fetch_detail` do
Workday ficou desligado (Q1).

Medido pelo endpoint HTTP, cinco chamadas cada:

| Endpoint | Antes da correção `5ff2647` | Depois |
|---|---|---|
| `/inbox?limit=20` | 4,0 a 6,5 s | 0,58 a 0,65 s (1,1 s na primeira) |
| `/inbox`, todas as áreas | — | 0,45 a 0,47 s |
| `/overview` | 4,8 a 5,4 s | 0,92 a 1,10 s |
| `/search-metrics` | 4,6 a 4,7 s | 1,03 a 1,12 s |
| `/funnel-metrics` | 1,25 a 1,36 s | 1,30 a 1,43 s |

A causa do `/inbox` lento era compilação JIT de uma subconsulta repetida, mais três
consultas rodando para cada linha filtrada. A tabela `matching.current_assessment` sozinha
não resolvia.

Outros resultados:

- **Elegibilidade com `matching-v3`:** em 10.442 vagas reavaliadas, 990 `ELIGIBLE`, 1.329
  `INELIGIBLE` e 8.123 `UNKNOWN`. Decidida em 22%, abaixo da meta de 50%.
- **Hacker News:** execução `SUCCEEDED`, 204 itens vistos, nenhum inválido.
- **Contadores de área-alvo:** gravados em toda execução. Um Workday mediu 24 vagas na área e
  277 fora.
- **Prompt `v3`:** uma análise pela API terminou `AI_COMPLETED`. As quatro listas vieram
  exatamente no limite (4, 5, 3, 4), então o corte pode estar agindo em toda resposta.
- **Poda:** o job foi registrado mas não chegou a rodar; ele segue o intervalo da retenção
  de payloads.
- **Cota de IA:** a cota diária já estava esgotada no banco copiado, então o worker não
  analisou nada com `v3`.

Dois achados que mudam leituras anteriores:

- A taxonomia `skills-v4` só vale para vagas normalizadas depois da troca. A versão fica
  gravada nas skills de cada vaga; o catálogo existente continua `skills-v3` até ser
  renormalizado. Os 24,1% de `ai` são uma simulação sobre título e descrição, não o estado do
  banco.
- O `v3` não reduz a saída: 457 a 584 tokens em chamadas reais, contra 455 a 502 do `v1`. O
  teto subiu de 600 para 800 porque o Groq conta tokens de raciocínio no limite.

## Antes do deploy

1. Aplicar as migrações `0062`, `0063` e `0064`. A `0063` faz o backfill dos ponteiros.
2. Rodar `scripts/retag_skills.py` em dry-run e depois com `--apply`, para levar o catálogo
   existente a `skills-v4`, e esperar a reavaliação completa do catálogo (taxonomia e regras
   mudaram).
3. Rodar `scripts/prune_assessments.py` em dry-run e ler o relatório antes de ligar a poda.
4. Rodar `scripts/reclassify_content.py` em dry-run e ler `fingerprint_collisions` antes de
   qualquer `--apply`. Isso só faz sentido depois de o gold passar no portão.
5. Depois de três execuções completas por fonte, repetir as consultas do §2 da spec e
   atualizar a tabela do §1.
