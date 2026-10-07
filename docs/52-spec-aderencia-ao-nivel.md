# SPEC 52 — Aderência ao nível: senioridade, oferta júnior/pleno e remoto (cards F52)

- **Data:** 2026-10-05
- **Estado (2026-10-07):** em implementação; F52-01, F52-02, F52-04 e F52-05 concluídos.
  - F52-04: **concluído** (quarta sessão). Medido em 2026-10-07, 02h44 UTC, com a
    reavaliação terminada: nenhuma avaliação de topo com nível fora do aceito.
  - F52-05: **concluído** (quarta sessão). Na mesma medição, nenhuma avaliação de topo com
    nível `UNKNOWN`; o total do Inbox não caiu. A ordem do Inbox passou a ler os níveis
    aceitos (PR #51).
  - F52-08 e F52-09: código em `main` (PR #56); ver os cards.
  - F52-01: **concluído** (terceira sessão). Rótulos aprovados pelo dono (PR #49); precisão
    de 95,3% na amostra.
  - F52-02: **concluído** (terceira sessão). `seniority-v5` com cobertura de 62,7% (meta de
    60%) e precisão de 95,3% (meta de 90%).
  - F52-03 e F52-07: **bloqueados pelo portão do F51-11**. Com o gold confirmado, nenhuma
    regra por descrição passa (ver F52-03); as regras continuam desligadas.
  - F52-06: **em andamento**. Lote do inHire terminado (98 fontes) e medição por fonte
    feita em 2026-10-07: 369 vagas `JUNIOR` ou `MID` nas áreas-alvo, contra a meta de 600.
    A ampliação do catálogo não foi feita.
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
  - **Rótulos aprovados e precisão medida (2026-10-06, PRs #48 e #49):** o dono aprovou a
    proposta em bloco, como está; `revisado_por: "mathfrancisco"` gravado nas 300 entradas
    (0 antes, 300 depois), sem mudar valor. Comando:
    `python scripts/measure_seniority_titles.py --sample docs/pesquisas/f52-01-amostra-senioridade-proposta.json`
    (Python local, `PYTHONPATH=src`). Resultado: 300 entradas medidas, **precisão de 95,3%**
    (142 de 149 emissões). Por nível: `SENIOR` 69/69, `MANAGER` 23/29 (79,3%), `STAFF` 14/14,
    `MID` 11/11, `INTERN` 9/9, `JUNIOR` 7/8, `LEAD` 6/6, `DIRECTOR` 3/3. Dos 151 títulos que
    a regra deixa `UNKNOWN`, 144 também não têm nível no rótulo; 7 têm (4 sem sinal, 3 com
    numeral).
  - **O que erra:** `Manager` como parte do nome do cargo (`Program Manager`, `Product
    Manager`, `Account Manager`) vira nível `MANAGER`, inclusive quando o título traz
    `Senior`, `Staff` ou `Principal` (6 casos); `Associate` em `Data Labeling Associate` vira
    `JUNIOR` (1 caso). Correção fica para uma próxima versão da regra; não foi feita aqui.
  - **Decisão tomada pelo agente (2026-10-06):** os leitores passam a ler a sugestão de uma
    entrada assinada que não tem rótulo próprio (PR #48) — a autorização do dono era gravar
    só `revisado_por`, e com `nivel_rotulado` nulo a medição contava zero entradas. Sugestão
    sem assinatura continua sem ser lida.
  - **Estado:** concluído. As metas do §1 ficam: cobertura só com o título em 60% (atingida);
    os 80% dependem do F52-03, que está bloqueado.
  - **`seniority-v6` (2026-10-06, PR #53):** corrige os erros acima. `Program Manager`,
    `Product Manager`, `Account Manager` e `Product Marketing Manager` deixam de emitir
    `MANAGER`; o nível vem das outras palavras do título ou fica `UNKNOWN`. `Labeling
    Associate` deixa de emitir `JUNIOR`. Na mesma amostra a precisão vai de 95,3% (142 de
    149) para 99,3%; `MANAGER` de 23/29 para 23/23. `LEAD` vai de 6/6 para 6/7: o erro que
    resta é o título que lista vários cargos (`SWE, Tech Lead, ML Engineer, Product
    Manager, ...`), que era `MANAGER` errado e virou `LEAD` errado; não foi criada regra
    para lista de cargos com base num caso só. **Não aplicado na base de dev:** faltam o
    dry-run, o `pg_dump` e o `--apply`. O efeito em títulos fora da amostra (por exemplo
    `Group Product Manager`) não foi medido.

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
  - **Precisão (2026-10-06, PR #49):** 95,3% na amostra do F52-01, acima da meta de 90%;
    detalhe por nível no F52-01. `MANAGER` isolado fica em 79,3%.
  - **Estado:** concluído. Tabela do P2 com um teste por linha, precisão de 95,3% e cobertura
    de 62,7% contra a meta decidida de 60%.

### F52-03 — Senioridade pela descrição

- **Problema:** P3.
- **Mudança:** depende do gold da SPEC 51 (F51-11). Com a regra `description_years_min`
  ligada, anos de experiência pedidos passam a decidir o nível quando o título não decide.
- **Aceite:** cobertura de senioridade nas áreas-alvo de 80%, com precisão de 90% no gold.
- **Esforço / risco:** P aqui / o risco está no F51-11. 40% das vagas não têm descrição
  (Workday); para elas só o título vale.
- **Resultado do portão (2026-10-06):** bloqueado. Com o gold confirmado (368 vagas),
  `seniority:description_years_min` emite em 3 casos e acerta 1 (33,3%); o portão pede 20
  emissões e 90%. `description_years_range`, `description_entry_phrase` e
  `description_intern_phrase` não emitem nenhuma vez. A regra continua desligada, não há
  sinal de nível novo e o `matching-v6` não tem o que incluir daqui. Sem a regra, a
  cobertura continua em 62,7%. Ver o F51-11 para o que destrava.

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
  - **Medição do aceite (2026-10-06, 20h57 UTC):** não fechado. De 22.122 avaliações atuais,
    4.250 em `matching-v5`, 9.700 em `matching-v4`, 328 em `matching-v3` e 7.844 em
    `matching-v2`. Restam 11 de topo com nível fora do aceito, todas em `matching-v2` (3) ou
    `matching-v3` (8); nenhuma em `matching-v4` nem em `matching-v5`. Consulta: contar em
    `matching.current_assessment` do perfil `b0ad7958`, com `verdict` em `RECOMMENDED` ou
    `HIGH_PRIORITY`, as vagas com `seniority` fora de `JUNIOR`, `MID` e `UNKNOWN`.
  - **Escopo da medição (2026-10-06, quarta sessão):** a condição "só `matching-v5` em
    `matching.current_assessment`" não é alcançável. A fila de avaliação
    (`pending_evaluation_ids`) só reavalia vaga aberta (`DISCOVERED` ou `ACTIVE`) das
    áreas-alvo ou de área `UNKNOWN`. Às 21h13 UTC, 7.705 ponteiros do perfil ativo estavam
    fora disso e ficam na versão antiga: 1.228 de vagas fechadas e 6.477 de vagas abertas
    de outras áreas, com 66 avaliações de topo entre eles (54 fechadas, 12 de outras
    áreas). O Inbox padrão não lista vaga fechada. O aceite passa a ser medido sobre vagas
    abertas das áreas-alvo (`SOFTWARE_ENGINEERING` e `DATA`), que é o escopo do §1.
  - **Medição do aceite (2026-10-07, 02h44 UTC):** fechado. Nesse escopo, as 8.116
    avaliações atuais do perfil `b0ad7958` estão em `matching-v5`. Topo com 188 avaliações;
    nenhuma com nível fora de `JUNIOR` e `MID` (meta: 0).
  - **Estado:** concluído. Regra provada pelo teste de regressão em
    `tests/backend/matching/test_domain.py` e número zero medido na base de dev. Fora do
    escopo medido continuam avaliações antigas de vagas fechadas e de outras áreas, que o
    worker não reavalia.

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
  - **Medição (2026-10-06, 20h57 UTC):** não fechado, reavaliação em 4.250 de 22.122. Topo
    com 447 avaliações, 236 de nível `UNKNOWN` (52,8%), nenhuma delas em `matching-v5`: as 21
    avaliações de topo já em v5 são todas `JUNIOR` ou `MID`. Avaliações não `INELIGIBLE` no
    perfil ativo: 18.188 (referência para "o total do Inbox não cai").
  - **Limite conhecido, tratado (2026-10-06, PR #51):** a ordem padrão do Inbox passou a
    ser veredito de topo, depois nível conhecido e aceito, depois pontuação, recência e id.
    Os níveis aceitos são lidos de `profile.employment_preference` dentro da mesma
    consulta; `UNKNOWN` nunca conta como aceito, mesmo quando o perfil o lista. As ordens
    `score` e `recency` e a ordem com termo de busca não mudaram, e `RULES_VERSION`
    continua `matching-v5`. Cinco testes em `tests/backend/dashboard/test_queries.py`.
  - **Medição do aceite (2026-10-07, 02h44 UTC):** fechado, no escopo descrito no F52-04
    (vagas abertas das áreas-alvo, todas em `matching-v5`). Topo com 188 avaliações,
    nenhuma de nível `UNKNOWN` (meta: menos de 30%). Avaliações não `INELIGIBLE` no perfil
    ativo: 18.217, contra a referência de 18.188; o total do Inbox não caiu.
  - **Estado:** concluído.

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
  `COLLECTION_TARGET_AREA_FLOOR`.
- **Medição (2026-10-07, base de dev):** o lote do inHire terminou: 98 fontes, todas com
  execução `SUCCEEDED`, 1.676 vagas. Vagas abertas das áreas-alvo (`SOFTWARE_ENGINEERING` e
  `DATA`), sem duplicata: 186 `JUNIOR` e 183 `MID`, **369 no total, contra a meta de 600**;
  3.049 continuam com nível `UNKNOWN`. Por tipo de fonte (uma vaga com duas fontes conta nas
  duas):

  | Fonte | `JUNIOR` ou `MID` | Vagas das áreas-alvo | Proporção | `JUNIOR` ou `MID` e remotas |
  |---|---:|---:|---:|---:|
  | Workday | 128 | 1.978 | 6,5% | 1 |
  | inHire | 106 | 498 | 21,3% | 60 |
  | Lever | 54 | 1.921 | 2,8% | 30 |
  | Greenhouse | 54 | 2.081 | 2,6% | 4 |
  | Ashby | 17 | 1.207 | 1,4% | 5 |
  | Hacker News | 7 | 202 | 3,5% | 1 |
  | Workable | 3 | 163 | 1,8% | 0 |
  | Factorial, Teamtailor, Remotive | 0 | 42 | 0% | 0 |

  O inHire tem a maior proporção e quase dois terços das vagas remotas do nível. As fontes
  inHire passaram a coletar de hora em hora (PR #66).
- **Não feito:** a ampliação do catálogo. Das 362 empresas, 249 têm fonte habilitada e as
  outras 113 só têm página de carreiras. Chegar a 600 pede empresas novas: a cerca de uma
  vaga do nível por fonte inHire, faltam por volta de 230 vagas. O caminho já aceito é
  curadoria de empresas brasileiras em `docs/pesquisas/empresas-adicionais.md`, depois
  `import_research_catalog.py`, `discover_ats.py` e `enable_sources.py`. A revisão de termos
  de Sólides, Recrutei e Quickin também não foi feita.

### F52-07 — Remoto de verdade: país e modo

- **Problema:** P6.
- **Mudança:** depende do gold da SPEC 51. Ligar as regras `work_mode:description_phrase` e
  `allowed_countries:description` quando passarem no portão; no Inbox, mostrar "remoto, país
  não informado" separado de "remoto no Brasil".
- **Aceite:** `work_mode` conhecido em 70% e `allowed_countries` em 50% das vagas remotas das
  áreas-alvo.
- **Esforço / risco:** P aqui / o risco está no F51-11.
- **Resultado do portão (2026-10-06):** bloqueado. `work_mode:description_phrase` acerta 7
  de 8 emissões (87,5%); `allowed_countries:description` erra a única emissão. Nenhuma chega
  às 20 emissões nem aos 90%. As duas continuam desligadas; a separação "remoto, país não
  informado" no Inbox não foi feita.

### F52-08 — Tabela de ritmo por fornecedor

- **Problema:** P7.
- **Mudança:** uma tabela em `docs/17-fontes-coletores.md` com, por tipo de fonte: o que o
  fornecedor pede (com a fonte da informação), o teto por hora e o intervalo usados, e o
  consumo medido. Ajustar o que não tem base. Workday fica como está.
- **Aceite:** todo tipo com coletor tem linha na tabela; nenhum teto abaixo do consumo
  medido (o do Hacker News estava: 226 usados contra 200 gravados).
- **Esforço / risco:** P / baixo.
- **Resultado (2026-10-06, PR #56):** tabela em `docs/17-fontes-coletores.md` §6.3, com o
  pico medido na base de dev entre 2026-09-25 e 2026-10-06 (requisições por hora de
  relógio do início da execução, por chave de orçamento). O teto padrão do inHire em
  `acquisition/service.py` foi de 300 para 1.200: estava abaixo do pico medido (1.089) e
  diferente do valor de `Settings`, que o worker usa. Testes em
  `tests/backend/acquisition/test_pacing_table.py`.
  - **Workday:** não alterado, por decisão. O pico medido é de 2.092 requisições numa
    hora para um tenant, contra o teto de 500; a execução inteira conta na hora em que
    começou, então o número é uma estimativa por cima.
  - **Sem fonte no repositório:** o que o fornecedor pede em `jobposting` e o limite por
    hora de `tavily_search`.
  - **Estado:** critérios de aceite com teste. Os quatro testes que leem `docs/` são
    pulados no contêiner e passaram com `docs/` montado.

### F52-09 — Busca e coleta por script

- **Problema:** os scripts de coleta e busca não leem o nível do perfil.
- **Mudança:** `scripts/collect.py` e a busca por texto passam a relatar, por execução,
  quantas vagas do nível aceito cada fonte trouxe; `eval_search` ganha casos de nível
  (consulta "júnior remoto" não devolve sênior no topo).
- **Aceite:** relatório por fonte com a coluna de nível; casos de nível no conjunto de
  avaliação da busca.
- **Esforço / risco:** P / baixo.
- **Resultado (2026-10-06, PR #56):** `scripts/collect.py` relata por execução quantas
  vagas dos níveis aceitos pelo perfil (sem `UNKNOWN`) cada fonte trouxe; sem perfil
  ativo a coluna diz isso e a execução não falha. `scripts/eval_search.py` ganhou três
  casos de nível ("júnior remoto", "desenvolvedor junior", "pleno remoto") que proíbem
  `SENIOR` ou acima nos dez primeiros. Testes em
  `tests/backend/dashboard/test_collect_level_column.py` e
  `test_eval_search_level_cases.py`.
  - **Aberto:** não existe relatório de busca por fonte, então nenhum recebeu a coluna.
    A contagem só vê item que o normalizador já processou. Os dois scripts não foram
    rodados de ponta a ponta contra a base de dev.

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
- **Fila `REVIEW_REQUIRED` (2026-10-07):** tratada conforme a decisão do dono de 2026-10-06
  (amostrar 50 de cada motivo, resolver em lote só "mesma fonte, `external_id` diferente e
  local ou modo diferente", nenhuma fusão automática). `scripts/resolve_review_queue.py` faz
  a amostra e a resolução; sem `--apply` só conta. Na base de dev a fila tinha 5.607 linhas:
  5.031 `SAME_COMPANY_AND_TITLE_DIFFERENT_IDENTITY`, 552
  `EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED`, 12 `EXACT_VERSIONED_FINGERPRINT`, 8
  `SAME_SOURCE_EXTERNAL_IDENTITY` e 4 `IDENTITY_REFRESHED_SAME_EXTERNAL_ID`. A amostra (124
  linhas: 50 dos dois primeiros motivos e todas as dos outros três) está em
  [fila-review-required-amostra-2026-10-07.json](pesquisas/fila-review-required-amostra-2026-10-07.json).
  O padrão só existe no primeiro motivo: 4.455 linhas em que todos os candidatos estão na
  mesma fonte com outro `external_id` e diferem em local ou modo conhecidos (a mesma vaga
  publicada por cidade). Depois de `pg_dump`
  (`dev-before-review-queue-resolve-2026-10-07.dump`), essas linhas passaram a
  `SUCCEEDED`/`NEW` com o motivo `REVIEW_RESOLVED_DISTINCT_POSTING`; o motivo original fica.
  Nenhuma vaga, ocorrência ou vínculo de duplicata mudou. Ficaram 1.152 linhas na fila: 576
  do primeiro motivo (mesmo local e modo, local desconhecido ou candidato de outra fonte) e
  as 576 dos outros motivos, que pedem decisão caso a caso. O normalizador não mudou: uma
  vaga nova no mesmo padrão volta a entrar na fila, e o script pode ser rodado de novo.
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
