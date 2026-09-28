# CARD F20-73 — Garantir exceção de "programa" na regra de recência de 14 dias para não agravar a escassez de junior/estágio

- **Status:** Backlog.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** o card da regra de recência de 14 dias (em elaboração por outro
  worker no momento deste diagnóstico; não localizado em nenhuma branch local nem em
  `docs/44-roadmap-fase-20/` — atualizar este "Depende de" com o número real do card
  assim que ele existir).
- **Origem:** diagnóstico "por que a busca traz tão poucas vagas junior/estágio",
  registrado em
  [`docs/44-roadmap-fase-20/evidencias/diagnostico-vagas-junior-2026-09-28.md`](../evidencias/diagnostico-vagas-junior-2026-09-28.md)
  (2026-09-28), seção 4.

## Contexto

O diagnóstico de origem mediu que só 18 de 2288 vagas do acervo real (0,79%) são
JUNIOR/INTERN, concentradas em 5 empresas: Adobe (7 INTERN via Workday, título
"2027 Intern - ..."), Spotify (2 INTERN via Lever, "CoLM 2026 — Intern"/
"RecSys 2026 — Intern"), CI&T (3 JUNIOR via Lever), Factorial (1 JUNIOR + 4 INTERN,
autocoleta), Lokalise (1 JUNIOR via Greenhouse).

Vagas de estágio/trainee/"programa" (ciclo anual, ex.: os exemplos da Adobe e do
Spotify acima) tendem a ficar publicadas por mais tempo do que vagas individuais de
tech pleno/senior, que fecham ou são republicadas em ciclos mais curtos. Uma regra de
recência de 14 dias sem tratamento diferenciado para esse padrão penalizaria
desproporcionalmente o subconjunto de vagas junior/estágio que já é minúsculo,
reduzindo ainda mais o que aparece na busca — mesmo que a vaga continue ativa e
aceitando candidaturas.

Este card **não implementa a regra de recência** (não é o escopo deste diagnóstico) —
existe só para garantir que a exceção de "programa" seja considerada quando o card real
da regra for escrito/revisado, com os números acima como evidência do porquê.

## Escopo

1. Quando o card real da regra de recência de 14 dias for identificado, confirmar se
   ele já inclui uma exceção para vagas classificadas como INTERN (e, se aplicável,
   JUNIOR com sinal de "programa"/"trainee" no título) que não conte os 14 dias da
   mesma forma que vagas de outros níveis — por exemplo, usar `published_at` do ciclo
   anual do programa em vez de tempo desde a última observação (`last_seen_at`), ou
   simplesmente isentar INTERN da regra.
2. Se a exceção já existir no card real, fechar este card apontando para lá, sem
   duplicar trabalho.
3. Se não existir, propor o ajuste mínimo (parâmetro de exceção por senioridade ou por
   contrato — `ContractType.INTERNSHIP` já existe no domínio, ver
   `src/opportunity_radar/opportunities/domain.py:963`) e implementá-lo dentro do
   escopo do card real, não deste.

## Fora de escopo

- Implementar a regra de recência de 14 dias do zero — pertence ao card real, não a
  este.
- Qualquer mudança em `infer_seniority`/`infer_contract_type` — ver F20-70 para isso.

## Critérios de aceite

- [ ] Card real da regra de recência de 14 dias localizado e referenciado no campo
      "Depende de" deste card.
- [ ] Confirmado (com link de evidência) se a exceção de programa/INTERN já existe lá
      ou foi adicionada como consequência deste card.
- [ ] Se a exceção foi adicionada, teste de regressão cobrindo pelo menos um caso real
      do acervo (ex.: "2027 Intern - Software Engineer" da Adobe) confirmando que não é
      removido da busca só por recência quando ainda está ativo.

## Não fazer

- Não isentar toda a categoria INTERN/JUNIOR de qualquer verificação de recência —
  vaga de programa que realmente fechou (evidência de closure) ainda deve ser tratada
  como fechada; a exceção é sobre o cálculo de "há quanto tempo apareceu", não sobre
  ignorar sinal de encerramento real.

## Verificação

- **CI:** suíte de testes do card real da regra de recência, estendida com o caso de
  programa/INTERN.

## Pronto quando

O card real da regra de recência de 14 dias tiver, com evidência, uma exceção
considerada e decidida (aceita ou explicitamente rejeitada com justificativa) para
vagas de programa/INTERN, usando os números deste diagnóstico como contexto.
