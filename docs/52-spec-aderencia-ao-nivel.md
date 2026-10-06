# SPEC 52 — Aderência ao nível: senioridade, oferta júnior/pleno e remoto (cards F52)

- **Data:** 2026-10-05
- **Estado (2026-10-06):** em implementação, nenhum card concluído.
  - F52-04: `matching-v4` entregue; o aceite espera o fim da reavaliação, que o
    `matching-v5` reiniciou.
  - F52-05: `matching-v5` mesclado (PR #46) e rodando na base de dev; o aceite espera a
    mesma reavaliação.
  - F52-01: script, relatório, amostra e proposta de rótulos; espera a revisão do dono.
  - F52-02: `seniority-v5` mesclado (PR #40) e aplicado na base de dev; cobertura de 62,7%
    nas áreas-alvo (meta de 60%). A precisão espera a revisão do dono.
  - F52-03 e F52-07: dependem do gold (SPEC 51, F51-11); proposta de rótulos e comando do
    portão prontos (PR #41).
  - F52-06, F52-08 e F52-09: não começaram. As decisões do dono para eles estão no §7 e no
    F52-06.
- **Origem:** relato do dono: a busca devolve vagas muito acima do nível dele (júnior/pleno,
  remoto). Medições na stack `opportunity-radar-dev` em 2026-10-05.
- **Relação com a [SPEC 51](51-spec-coleta-confiavel-e-busca.md)** (implementação parcial; ver
  o [roadmap 51](51-roadmap-coleta-confiavel/README.md)): a SPEC 51 trata do detalhe do
  Workday, da concorrência do worker por host, do gold das regras de conteúdo e da fila de IA.
  Esta spec não repete esses cards; o §5 diz onde cada assunto mora.

## 1. Objetivo

Fazer o topo da busca ser, na maioria, vaga que o dono pode de fato disputar. Sem filtro
fixo novo: o perfil continua dizendo o que aceita, e o produto passa a classificar melhor o
nível de cada vaga, a pesar o nível na ordenação e a buscar mais vagas do nível certo.

| Métrica (áreas-alvo) | Hoje | Meta |
|---|---:|---:|
| Vagas com senioridade conhecida | 50,8% | 80% |
| Vagas `JUNIOR` ou `MID` no catálogo | 147 (1,8%) | 600 |
| `RECOMMENDED` e `HIGH_PRIORITY` com nível acima do aceito | 164 de 1.515 | 0 |
| `RECOMMENDED` e `HIGH_PRIORITY` com senioridade `UNKNOWN` | 1.156 de 1.515 (76%) | menos de 30% |

As metas são propostas; o F52-01 confirma ou corrige depois da linha de base.

## 2. Estado medido (2026-10-05)

Perfil ativo: senioridades aceitas `JUNIOR`, `MID`, `UNKNOWN`; modo `remote`; contrato
`full-time`; país `BR`; áreas `SOFTWARE_ENGINEERING` e `DATA`.

Catálogo nas áreas-alvo, 8.186 vagas:

| Senioridade | Vagas | % |
|---|---:|---:|
| `UNKNOWN` | 4.031 | 49,2 |
| `SENIOR` | 2.183 | 26,7 |
| `MANAGER` | 682 | 8,3 |
| `STAFF` | 590 | 7,2 |
| `INTERN` | 264 | 3,2 |
| `LEAD` | 194 | 2,4 |
| `MID` | 101 | 1,2 |
| `DIRECTOR` | 95 | 1,2 |
| `JUNIOR` | 46 | 0,6 |

Modo de trabalho nas mesmas vagas: `UNKNOWN` 52,8%, `REMOTE` 34,5%, `HYBRID` 6,8%, `ONSITE`
5,9%. Vagas `JUNIOR` ou `MID` e `REMOTE`: 70.

Vagas `JUNIOR` ou `MID` por tipo de fonte (contagem por ocorrência):

| Tipo | Júnior/pleno | Total | % |
|---|---:|---:|---:|
| inhire | 62 | 371 | 16,7 |
| lever | 36 | 2.009 | 1,8 |
| workday | 25 | 2.688 | 0,9 |
| greenhouse | 17 | 2.175 | 0,8 |
| ashby | 5 | 1.272 | 0,4 |
| demais | 4 | 483 | 0,8 |

O inHire entrou hoje, com o lote de 98 empresas ainda pela metade, e já responde por cerca
de 40% das vagas júnior/pleno do catálogo.

Avaliações atuais com veredito `RECOMMENDED` ou `HIGH_PRIORITY`, por senioridade da vaga:
`UNKNOWN` 1.156, `SENIOR` 92, `INTERN` 85, `MID` 68, `JUNIOR` 42, `STAFF` 38, `MANAGER` 17,
`LEAD` 12, `DIRECTOR` 5.

## 3. Problemas

**P1. Quase não há vaga do nível do dono no catálogo.** 147 em 8.186. As fontes são, na
maioria, boards de empresas globais de tecnologia, que publicam sobretudo vagas sênior. Onde
há fonte brasileira (inHire), a proporção sobe de menos de 2% para 17%. Nenhuma regra de
ordenação conserta falta de oferta.

**P2. O classificador de senioridade erra títulos comuns.** Testado em 2026-10-05 com
`seniority_classification` sobre títulos reais do catálogo:

| Título | Resultado | Esperado |
|---|---|---|
| `Dev. Back-end Node.js Sênior \| Pix [Remoto]` | `UNKNOWN` | `SENIOR` |
| `Desenvolvedor(a) Backend Sênior - Node.js` | `UNKNOWN` | `SENIOR` |
| `Analista de Dados Júnior` | `UNKNOWN` | `JUNIOR` |
| `Senior Staff Engineer - Enterprise Messaging` | `UNKNOWN` | `STAFF` |
| `Software Engineer I`, `II`, `III` | `UNKNOWN` | `JUNIOR`, `MID`, `SENIOR` |
| `Software Architect (AWS, NodeJS)` | `UNKNOWN` | `STAFF` ou `SENIOR` |
| `Head of Engineering` | `UNKNOWN` | `DIRECTOR` |
| `Tech Lead \| Engenheiro(a) Backend Especialista` | `UNKNOWN` | `LEAD` |
| `Associate Software Engineer` | `UNKNOWN` | `JUNIOR` |
| `Systems Software Engineer - New College Grad 2026` | `UNKNOWN` | `JUNIOR` |
| `Desenvolvedor Pl/Sr` | `UNKNOWN` | `MID` e `SENIOR` |
| `Entry Level Developer` | `INTERN` | `JUNIOR` |

Dois padrões respondem pela maior parte: a palavra com acento (`Sênior`, `Júnior`) não casa,
enquanto `Sr` e `Jr` casam; e um título com dois níveis (`Senior Staff`, `Tech Lead ...
Especialista`) vira `UNKNOWN` em vez do nível mais alto. Quantas das 4.031 vagas `UNKNOWN`
cada padrão explica: não medido; o F52-01 mede.

**P3. `UNKNOWN` passa como se fosse do nível.** O perfil aceita `UNKNOWN`, o que é razoável:
recusar metade do catálogo por falta de dado esconderia vagas boas. Mas o resultado é que 76%
do topo da busca é vaga de nível desconhecido, e boa parte dela é sênior mal classificada
(P2). O fator `SENIORITY_SCOPE` está `UNKNOWN` em 23.845 de 43.283 avaliações atuais.

**P4. Vaga acima do nível ainda chega ao topo.** 164 avaliações `RECOMMENDED` ou
`HIGH_PRIORITY` são de vagas `SENIOR`, `STAFF`, `MANAGER`, `LEAD` ou `DIRECTOR`, que o perfil
não aceita. Ao mesmo tempo, 1.042 vagas `SENIOR` estão `INELIGIBLE`. Por que parte passa e
parte não: não determinado. Hipóteses a conferir no F52-04: avaliação anterior à
reclassificação da vaga, ou elegibilidade que não lê senioridade em algum caminho.

**P5. Estágio conta como recomendação.** 85 vagas `INTERN` estão `RECOMMENDED`, e o perfil
não lista `INTERN`. Mesma investigação do P4. Além disso, `Entry Level` é classificado como
`INTERN`, o que tira vaga júnior do alcance do perfil.

**P6. Remoto e país desconhecidos na metade das vagas.** `work_mode` é `UNKNOWN` em 52,8%, e
`allowed_countries` tinha 11,5% de cobertura na medição da SPEC 50. Uma vaga "remota" restrita
aos Estados Unidos aparece como candidata. As regras que leem isso da descrição existem e
estão desligadas, à espera do gold (SPEC 51, F51-11).

**P7. Tetos de coleta sem base.** O teto de 300 requisições por hora no inHire e o padrão de
200 não vieram de fornecedor nem de medição. Corrigidos em 2026-10-05 (PR #34: 1.200 e
1.000). Falta a tabela por tipo com o que cada fornecedor pede (F52-08).

## 4. Cards

Cada card é entregue sozinho, com teste, e medido contra o §1.

### F52-01 — Linha de base e amostra rotulada de senioridade

- **Problema:** P2, P3.
- **Mudança:** script que roda o classificador sobre todos os títulos das áreas-alvo e
  agrupa os `UNKNOWN` por padrão (acento, dois níveis, numeral, palavra não coberta, sem
  sinal). Amostra de 200 títulos `UNKNOWN` e 100 classificados, rotulada pelo dono.
- **Aceite:** relatório em `docs/pesquisas/` com a contagem por padrão e a precisão por
  nível; metas do §1 confirmadas ou corrigidas.
- **Teste:** o script roda no CI contra a amostra versionada.
- **Esforço / risco:** P / baixo. Sem mudança de comportamento.
- **Resultado (2026-10-06):** `scripts/measure_seniority_titles.py`, relatório em
  [f52-01-linha-de-base-senioridade.md](pesquisas/f52-01-linha-de-base-senioridade.md) e
  amostra de 300 títulos em `docs/pesquisas/f52-01-amostra-senioridade.json`, que roda no CI.
  Dos 4.121 `UNKNOWN`: 138 por acento, 375 com dois níveis, 136 com numeral, 577 com palavra
  não coberta e 2.895 (70,2%) sem sinal no título.
  - **Aberto:** a amostra não foi rotulada, então a precisão por nível não foi medida e o
    card não está concluído. Há uma proposta de rótulo por título, feita pelo modelo sem ver
    a resposta do classificador, em `docs/pesquisas/f52-01-amostra-senioridade-proposta.json`
    (14 de 300 discordam do `seniority-v5`, listadas primeiro). Proposta não é rótulo: a
    medição só conta entradas com `revisado_por` preenchido pelo dono.
  - **Meta decidida (2026-10-06):** o teto de cobertura só com o título é 65,3%; a meta do
    F52-02 passa a 60%.

### F52-02 — Classificador de senioridade: acentos, dois níveis e numerais

- **Problema:** P2, P5.
- **Mudança:** comparar sem acento (`Sênior`, `Júnior`, `Estágio`); com dois níveis no
  título, ficar com o mais alto, salvo lista explícita de faixas (`Júnior, Pleno e Sênior`,
  `Pl/Sr`), que vira o conjunto de níveis; numerais `I`, `II`, `III` depois de um cargo;
  `Architect`, `Head of`, `Associate`, `New Grad`, `Entry Level` (júnior, não estágio).
  Nova versão da regra (`seniority-v5`), aplicada ao catálogo por um script com dry-run, como
  o `retag_skills.py`.
- **Aceite:** todos os títulos da tabela do P2 classificados como esperado; precisão de 90%
  ou mais na amostra do F52-01; cobertura nas áreas-alvo de 65% só com o título.
- **Teste:** um caso por linha da tabela do P2, mais regressão sobre a amostra.
- **Esforço / risco:** M / médio. Muda a identidade? Não: senioridade não entra no
  fingerprint. Muda a elegibilidade de milhares de vagas de uma vez; rodar o dry-run antes.
- **Decisões do dono (2026-10-06):** faixa de níveis guarda o nível mais baixo e a faixa vai
  para a evidência (`range`), sem migração (Q1). `Entry Level` e `New Grad` são `JUNIOR` (Q3).
  `Architect` é `SENIOR` quando o título não tem outra palavra de nível. `Member of Technical
  Staff` não é `STAFF` e fica `UNKNOWN`. Palavra de nível vence numeral. Numerais acima de
  `III` ficam `UNKNOWN`. Só os níveis de `INTERN` a `STAFF` formam faixa. A meta de cobertura
  só com o título passa de 65% para 60%; os 80% do §1 são do F52-03.
- **Resultado (2026-10-06):** `seniority-v5` em `opportunities/domain.py`, com um teste por
  linha da tabela do P2. Reaplicação por `scripts/retag_seniority.py` (dry-run por padrão,
  `--apply` grava), com teste de integração em
  `tests/backend/opportunities/test_retag_seniority_integration.py`. Dry-run numa cópia da
  base de dev em [f52-02-reaplicacao-senioridade.md](pesquisas/f52-02-reaplicacao-senioridade.md):
  nas áreas-alvo a cobertura vai de 50,5% para 62,7% e `JUNIOR`+`MID` de 177 para 408.
  - **Aplicado na base de dev (2026-10-06, depois do merge do PR #40):** `pg_dump` antes
    (`dev-before-seniority-v5-apply-2026-10-06.dump`), depois `--apply`: 31.218 vagas lidas,
    4.732 reclassificadas, igual ao dry-run. Medido em seguida nas áreas-alvo: 5.320 de 8.484
    com nível conhecido (**62,7%**) e **410** vagas `JUNIOR` ou `MID`. No perfil ativo, o
    topo tinha 651 avaliações, 411 delas (63,1%) de nível `UNKNOWN` e 94 de nível acima do
    aceito; essas 94 são vagas recém-reclassificadas que o worker ainda não reavaliou
    (10.712 de 21.516 avaliações em `matching-v4`).
  - **Aberto:** a precisão de 90% depende dos rótulos. A proposta está em
    `docs/pesquisas/f52-01-amostra-senioridade-proposta.json`; só entradas com `revisado_por`
    preenchido pelo dono entram na medição.

### F52-03 — Senioridade pela descrição

- **Problema:** P3.
- **Mudança:** depende do gold da SPEC 51 (F51-11). Com a regra `description_years_min`
  ligada, anos de experiência pedidos passam a decidir o nível quando o título não decide.
- **Aceite:** cobertura de senioridade nas áreas-alvo de 80%, com precisão de 90% no gold.
- **Esforço / risco:** P aqui / o risco está no F51-11. 40% das vagas não têm descrição
  (Workday); para elas só o título vale.

### F52-04 — Por que vaga acima do nível é recomendada

- **Problema:** P4, P5.
- **Mudança:** investigar as 164 avaliações de nível não aceito e as 85 de `INTERN` no topo;
  corrigir a causa. Regra-alvo: nível conhecido e fora de `accepted_seniorities` nunca
  termina `RECOMMENDED` ou `HIGH_PRIORITY`.
- **Aceite:** zero avaliações atuais de topo com nível conhecido fora do aceito; teste de
  regressão com uma vaga `SENIOR`, uma `INTERN` e o perfil atual.
- **Esforço / risco:** P a M / baixo. Começar por aqui: é o erro mais visível.
- **Resultado (2026-10-06):** investigado na base de dev, pelo ponteiro
  `matching.current_assessment`. As duas hipóteses do P4 estavam erradas.
  - **`INTERN` no topo (P5):** as 85 avaliações são da versão arquivada do perfil
    (`60c45fa0`), que aceitava `INTERN`. No perfil ativo não há nenhuma. A contagem do §2
    somou os ponteiros de todas as versões de perfil; não havia defeito de elegibilidade.
  - **Nível acima do aceito (P4):** 140 avaliações de topo no perfil ativo (137 em
    `matching-v3`, 3 em `matching-v2`). Causa: regra deliberada do F48-13, que mantém
    `SENIOR` e acima elegíveis e só reduz o fator `SENIORITY_SCOPE` a 0,25. Com peso de 0,15,
    os outros fatores levavam a vaga de volta a `RECOMMENDED`.
  - **Correção:** `matching-v4`. Nível conhecido fora de `accepted_seniorities` continua
    elegível (F48-13 preservado) e para no máximo em `WATCHLIST`. Perfil sem preferência de
    nível e vaga de nível `UNKNOWN` não são afetados. Teste em
    `tests/backend/matching/test_domain.py`.
  - **Não feito aqui:** a troca de `RULES_VERSION` reavalia o catálogo uma vez; o aceite
    ("zero avaliações de topo com nível conhecido fora do aceito") só pode ser medido depois
    dessa reavaliação na base de dev. As avaliações da versão arquivada do perfil continuam
    no ponteiro; contá-las ou não nas métricas do §1 é decisão de medição.
  - **Medição do aceite (2026-10-06, 14h41 UTC):** não fechado. A reavaliação não terminou:
    no perfil ativo (`b0ad7958`), 2.350 de 21.378 avaliações atuais estão em `matching-v4`
    (7.845 em `matching-v2`, 11.183 em `matching-v3`). Há 88 avaliações de topo com nível
    conhecido fora do aceito, todas ainda em `matching-v2` (3) ou `matching-v3` (85);
    nenhuma em `matching-v4`. Repetir a contagem quando não restar avaliação anterior à v4.
    As métricas do §1 passam a contar só o perfil ativo.
  - **Medição do aceite (2026-10-06, 16h39 UTC):** não fechado, pelo mesmo motivo. No perfil
    ativo, 7.812 de 21.380 avaliações atuais estão em `matching-v4` (7.845 em `matching-v2`,
    5.723 em `matching-v3`); o worker reavalia cerca de 2.700 por hora. Restam 8 avaliações
    de topo com nível conhecido fora do aceito, todas anteriores à v4: 3 em `matching-v2`
    (`MANAGER`, `SENIOR`, `STAFF`) e 5 em `matching-v3` (3 `LEAD`, 2 `SENIOR`). Nenhuma em
    `matching-v4`. A regra está provada pelo teste de regressão; o número zero depende do fim
    da reavaliação, que as trocas de versão desta sessão (`seniority-v5`, `matching-v5`)
    reiniciam para as vagas que mudam.
  - **Medição do aceite (2026-10-06, 18h15 UTC):** não fechado. 10.900 de 21.531 avaliações
    atuais em `matching-v4`. Restavam 12 de topo com nível conhecido fora do aceito, todas
    anteriores à v4 (3 em `matching-v2`, 9 em `matching-v3`); nenhuma em `matching-v4`.
  - **Medição do aceite (2026-10-06, 19h33 UTC, logo depois do `matching-v5` entrar):** não
    fechado. De 22.122 avaliações atuais, 50 em `matching-v5`, 13.900 em `matching-v4`, 328
    em `matching-v3` e 7.844 em `matching-v2`. Restam 11 de topo com nível fora do aceito (3
    em `matching-v2`, 8 em `matching-v3`); nenhuma em `matching-v4` nem em `matching-v5`. O
    `matching-v5` reavalia o catálogo inteiro; a cerca de 2.700 avaliações por hora, leva
    por volta de 8 horas. Repetir a contagem quando só houver `matching-v5`.

### F52-05 — Peso do nível desconhecido na ordenação

- **Problema:** P3.
- **Mudança:** sem filtro novo. Uma vaga de nível `UNKNOWN` continua elegível, mas não passa
  de `WATCHLIST` sem outro sinal de nível (anos pedidos, faixa salarial, palavras da
  descrição). Vaga de nível conhecido e aceito ganha a frente no Inbox.
- **Aceite:** menos de 30% do topo com senioridade `UNKNOWN`; nenhuma vaga some do Inbox, só
  muda de faixa.
- **Teste:** regressão de matching com os 50 casos existentes, mais casos de nível
  desconhecido.
- **Esforço / risco:** M / médio. Muda `RULES_VERSION` e reavalia o catálogo uma vez.
- **Decisão do dono (2026-10-06, Q2):** confirmado. Entra como `matching-v5`, num único
  bump junto com qualquer outra mudança de matching, depois de `seniority-v5` (feito) e de
  `skills-v5` (se houver) aplicados na base de dev. Linha de base antes do `seniority-v5`:
  690 de 847 no topo com `UNKNOWN`; depois dele, 411 de 651.
- **Resultado (2026-10-06, PR #46):** `matching-v5` em `matching/domain.py`. Para perfil que
  declara os níveis aceitos, vaga de nível `UNKNOWN` continua elegível e para no máximo em
  `WATCHLIST`; perfil sem preferência de nível não muda. Nenhum outro sinal de nível é lido
  hoje, então todo `UNKNOWN` para ali; o F52-03 é quem traz o sinal. No Inbox, a ordem padrão
  põe os vereditos de topo antes e depois ordena por pontuação; a ordem `score` continua só
  por pontuação. Testes em `tests/backend/matching/test_domain.py` (teto, elegibilidade
  mantida, perfil sem preferência) e `tests/backend/dashboard/test_queries.py` (ordem); os
  casos de regressão existentes continuam passando.
  - **Limite conhecido:** dentro da faixa `WATCHLIST` a ordem é só por pontuação, então uma
    vaga de nível aceito com pontuação menor fica atrás de uma `UNKNOWN`.
  - **Aberto:** o aceite ("menos de 30% do topo com `UNKNOWN`; nenhuma vaga some do Inbox")
    só pode ser medido na base de dev depois da reavaliação. Às 19h33 UTC, com 50 avaliações
    em `matching-v5`, o topo tinha 624 avaliações, 413 de nível `UNKNOWN`, todas de versões
    anteriores. A regra leva esse número a zero; falta conferir quantas vagas sobram no topo
    e que o total do Inbox não cai.

### F52-06 — Mais oferta júnior/pleno remota no Brasil

- **Problema:** P1.
- **Mudança:** terminar o lote do inHire (98 empresas) e medir quantas vagas júnior/pleno
  remotas ele traz. Levantar outras fontes brasileiras com revisão de termos viável; Gupy
  segue proibida. Priorizar no catálogo empresas cujas fontes trazem o nível do dono
  (`COLLECTION_TARGET_AREA_FLOOR` já mede área; falta medir nível).
- **Aceite:** 600 vagas `JUNIOR` ou `MID` nas áreas-alvo; relatório por fonte com a contagem
  de vagas do nível.
- **Esforço / risco:** M / depende de revisão de termos por fonte nova.
- **Decisões do dono (2026-10-06, Q4):** primeiro, sem coletor novo, ampliar o catálogo com
  empresas brasileiras que já usam ATS homologado (Greenhouse, Lever, Ashby, Workable,
  Teamtailor, Recruitee, inHire) e terminar o lote de 98 do inHire, medindo `JUNIOR`/`MID`
  por fonte. Depois, revisão de termos em `docs/pesquisas/termos-<fonte>.md` para Sólides,
  Recrutei e Quickin; coletor só para a fonte com listagem pública por API ou feed
  documentado **e** termos que não proíbem coleta automatizada. Gupy continua proibida.
  Priorizar fontes pela proporção de vagas do nível aceito, ao lado do
  `COLLECTION_TARGET_AREA_FLOOR`. Nada disso foi executado ainda.

### F52-07 — Remoto de verdade: país e modo

- **Problema:** P6.
- **Mudança:** depende do gold da SPEC 51. Ligar as regras `work_mode:description_phrase` e
  `allowed_countries:description` quando passarem no portão; no Inbox, mostrar "remoto, país
  não informado" separado de "remoto no Brasil".
- **Aceite:** `work_mode` conhecido em 70% e `allowed_countries` em 50% das vagas remotas das
  áreas-alvo.
- **Esforço / risco:** P aqui / o risco está no F51-11.

### F52-08 — Tabela de ritmo por fornecedor

- **Problema:** P7.
- **Mudança:** uma tabela em `docs/17-fontes-coletores.md` com, por tipo de fonte: o que o
  fornecedor pede (com a fonte da informação), o teto por hora e o intervalo usados, e o
  consumo medido. Ajustar o que não tem base. Workday fica como está.
- **Aceite:** todo tipo com coletor tem linha na tabela; nenhum teto abaixo do consumo
  medido (o do Hacker News estava: 226 usados contra 200 gravados).
- **Esforço / risco:** P / baixo.

### F52-09 — Busca e coleta por script

- **Problema:** os scripts de coleta e busca não leem o nível do perfil.
- **Mudança:** `scripts/collect.py` e a busca por texto passam a relatar, por execução,
  quantas vagas do nível aceito cada fonte trouxe; `eval_search` ganha casos de nível
  (consulta "júnior remoto" não devolve sênior no topo).
- **Aceite:** relatório por fonte com a coluna de nível; casos de nível no conjunto de
  avaliação da busca.
- **Esforço / risco:** P / baixo.

## 5. O que fica na SPEC 51

| Assunto | Card da SPEC 51 |
|---|---|
| Descrição das vagas do Workday (40% do catálogo sem descrição) | [F51-03](51-roadmap-coleta-confiavel/cards/f51-03-workday-termos-e-contratos-reais.md), [F51-04](51-roadmap-coleta-confiavel/cards/f51-04-workday-cooldown-orcamento-counters.md), [F51-05](51-roadmap-coleta-confiavel/cards/f51-05-workday-piloto-backfill.md) |
| Worker coletando hosts diferentes em paralelo | [F51-08](51-roadmap-coleta-confiavel/cards/f51-08-worker-concorrencia-host-orcamento.md) |
| Gold e ligação das regras de conteúdo | [F51-11](51-roadmap-coleta-confiavel/cards/f51-11-gold-regras-v4-reclassificacao.md) |
| Fila e cota de IA, com dois provedores | [F51-10](51-roadmap-coleta-confiavel/cards/f51-10-fila-ia-justa-retry.md), [F51-12](51-roadmap-coleta-confiavel/cards/f51-12-ia-seletiva-cache-quotas.md) |

Dois itens não estão em nenhuma das duas specs e ficam registrados aqui como pendência: a
fila de 5.219 normalizações em `REVIEW_REQUIRED` e as 2.543 vagas sem nenhuma skill depois do
`skills-v4`.

- **Vagas sem skill (2026-10-06, PR #44):** `skills-v5` acrescenta `linux`, `c++` e `etl`, os
  únicos termos que são tecnologia inequívoca em 10 ou mais das 1.043 vagas das áreas-alvo
  com descrição e sem skill. Medição e lista de termos ambíguos em
  [skills-v5-termos-sem-skill.md](pesquisas/skills-v5-termos-sem-skill.md). Aplicado na base
  de dev com `retag_skills.py --apply --include-untagged`, depois de `pg_dump`
  (`dev-before-skills-v5-apply-2026-10-06.dump`): 38.954 linhas de skill, todas `skills-v5`,
  em 12.507 vagas, igual ao dry-run. Vagas sem skill no catálogo: de 19.224 para 18.742; nas
  áreas-alvo com descrição, de 1.043 para 974. A maior parte das que restam não cita
  tecnologia; taxonomia maior não resolve isso.
- **Fila `REVIEW_REQUIRED`:** não tratada. A decisão do dono de 2026-10-06 continua valendo:
  amostrar 50 de cada motivo, resolver em lote só "mesma fonte, `external_id` diferente e
  local ou modo diferente", nenhuma fusão automática.
- **8 testes de fila (2026-10-06, PR #46):** reproduzido numa suíte completa em banco
  reutilizado. A fila de avaliação lê as vagas pendentes mais antigas até o limite de 500;
  vagas deixadas por outros módulos de teste ficam pendentes para cada versão nova de perfil
  e empurram a vaga do teste para fora da página. Corrigido esvaziando o catálogo antes de
  cada teste em `test_evaluation_queue.py` e `test_reevaluation.py`. O limite não mudou.

## 6. Ordem

1. F52-04: erro visível, sem dependência.
2. F52-01 e F52-02: o classificador.
3. F52-06: oferta, em paralelo (o lote do inHire já está rodando).
4. F52-05: depois do F52-02, para não rebaixar vaga que o classificador novo resolveria.
5. F52-03 e F52-07: quando o gold da SPEC 51 passar.
6. F52-08 e F52-09: a qualquer momento.

## 7. Perguntas abertas

- **Q1.** Respondida em 2026-10-06: a faixa guarda o nível mais baixo; a faixa inteira vai
  para a evidência. Sem migração.
- **Q2.** Respondida em 2026-10-06: nível `UNKNOWN` para no máximo em `WATCHLIST` enquanto não
  houver outro sinal de nível. Hoje nenhum outro sinal está ligado, então todo `UNKNOWN` para
  em `WATCHLIST`. No Inbox, nível conhecido e aceito vem antes.
- **Q3.** Respondida em 2026-10-06: `Entry Level` e `New Grad` são `JUNIOR`. `INTERN` não
  entra em `accepted_seniorities`.
- **Q4.** Respondida em 2026-10-06: ver "Decisões do dono" no F52-06.
