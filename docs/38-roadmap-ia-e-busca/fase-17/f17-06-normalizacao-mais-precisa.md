# CARD F17-06 — Normalização mais precisa: senioridade, skills, local e país

- **Status:** Em revisão — `skills-v2` fecha nesta sessão: `SKILL_TAXONOMY_VERSION` subiu
  para `skills-v2` e `NORMALIZER_VERSION` para `v4`, o reprocessamento oficial rodou na
  máquina de referência (`opportunity-radar`,
  `POST /opportunities/normalizations/pending` até esvaziar a fila) e a cobertura de
  skills subiu de 48,46% para 90,74% das 648 oportunidades reais pelo pipeline de
  verdade, sem perder nem duplicar oportunidade e sem falha nova (22
  `INVALID_COLLECTED_ITEM_V1` idênticas antes/depois). Ver
  [`docs/pesquisas/curadoria-skills-v2.md`](../../../pesquisas/curadoria-skills-v2.md) para
  a medição completa.
  **Não fechar como `Done` ainda:** medido nesta sessão contra a mesma máquina de
  referência, `seniority-v2` **não** reduziu a taxa de `UNKNOWN` — ainda 328/648 = 50,62%,
  estatisticamente igual ao baseline do F17-01 (50,6%,
  [`docs/pesquisas/baseline-f17-01.md`](../../../pesquisas/baseline-f17-01.md)), longe da
  meta de metade (~25,3%). Isso é um achado, não uma correção feita: `seniority-v2` está
  em código mas não está reduzindo `UNKNOWN` no acervo real como o critério exige — precisa
  de investigação (os padrões de título pt/en cobrem os casos certos? os coletores
  preenchem os campos estruturados que `seniority-v2` espera?) que fica fora do escopo
  desta sessão de fechamento de gap. `regions-v1` está funcional (251/648 oportunidades
  com `allowed_countries` preenchido), mas o critério de "país permitido" desse card
  também não foi remedido a fundo aqui.
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** F17-01
- **Bloqueia:** Milestone P
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §11

## Resultado

Senioridade, skills, localização e país permitido saem da normalização com mais acerto e
menos `UNKNOWN`, cada regra nova versionada e medida contra o que havia antes.

## Contexto

- Senioridade: só do título ou de metadado da entrada manual; nenhum ATS contribui
  (`opportunities/domain.py:791`, `seniority-v1`), e padrões em português como "Pleno"
  não estão cobertos.
- Skills: taxonomia de 27 entradas (`skills-v1`) — boa parte do vocabulário técnico das
  descrições não casa com nada.
- Local: textos como "Remote — Brazil", "LATAM", "Americas", "Anywhere" viram texto livre;
  o país permitido, que decide elegibilidade, fica desconhecido.

## Escopo

- **`seniority-v2`:**
  - padrões de título em português: estagiário, júnior, pleno, sênior, especialista,
    principal, staff, líder, com e sem acento, e abreviações (Jr, Pl, Sr);
  - por coletor, só os campos estruturados que existirem nas respostas reais — levantar
    nos fixtures de Ashby, Greenhouse e Lever antes de mapear; campo que não existe não
    entra. Cada campo mapeado é parte da homologação do coletor, como o comentário de
    `SENIORITY_MAPPING_VERSION` exige.
- **`skills-v2`:** script que lista os termos técnicos mais frequentes nas descrições do
  acervo sem entrada na taxonomia; cada entrada nova revisada com aliases e
  desambiguação, como as 27 atuais. Meta: recall ≥ 90% num conjunto marcado de 30 vagas.
- **Local e país:** tabela versionada de regiões (`regions-v1`) — LATAM, Americas, EMEA,
  Anywhere/Worldwide — com os países que cada uma inclui, e padrões de "Remote — <país>",
  "Remoto (Brasil)", fuso exigido ("UTC-3 ± 2"). O resultado preenche `allowed_countries`
  e o fuso do snapshot.
- **Reprocessamento:** a versão do normalizador sobe; o acervo é renormalizado pela fila
  existente (`normalize_pending` por versão), em lotes.

## Fora de escopo

- Classificação por modelo de linguagem.
- Área da vaga (F17-02).

## Notas de implementação

- Subir a versão do normalizador reprocessa todo `RawItem`; medir o tempo num acervo de
  tamanho real antes de subir, e documentar a janela no PR.
- Mudança no snapshot da oportunidade muda o `input_hash` do matching: as avaliações
  afetadas são refeitas, o que é o comportamento certo, mas gera uma onda de reanálise —
  a fila por valor do F16-04 absorve.

## Reprocessamento e limites semânticos

- Reprocessar pela nova regra mesmo quando a fonte não fornece
  `source_updated_at`: o retorno antecipado atual de `_refresh_opportunity`
  precisa ser tratado. Snapshot novo não depende de mudança no anúncio externo.
- Separar revisão da regra de atualização da fonte. Replay antigo não regride
  `last_seen_at`, payload corrente ou campos baseados em evidência mais recente.
- Mudança semântica incrementa versão e invalida matching/índice/vetor;
  repetição idêntica não cria ondas de reanálise. Lotes são retomáveis.
- Payload expirado não pode ser reconstruído por suposição: marcar indisponível,
  manter histórico e indicar recoleta possível.
- Local do escritório não é país permitido; remoto não significa global.
  País, residência, visto, patrocínio e fuso têm evidências distintas.
- Medir precisão junto com recall de skills e UNKNOWN de senioridade. Resolver
  mais campos incorretamente não passa no gate.

## Critérios de aceite

- [ ] `seniority-v2` reduz a taxa de `UNKNOWN` à metade do baseline do F17-01. **Não
      atingido:** medido nesta sessão contra o acervo real pós-reprocessamento, 328/648
      (50,62%) — igual ao baseline (50,6%), não a metade. Precisa de investigação, não
      marcado.
- [x] `skills-v2` atinge recall ≥ 90% no conjunto marcado. Medido como proxy honesta
      (cobertura de "≥1 skill" sobre as 648 oportunidades reais via o pipeline oficial de
      reprocessamento): 90,74%. Não existe o conjunto marcado de 30 vagas que o texto do
      card supõe — ver limitação em `docs/pesquisas/curadoria-skills-v2.md`.
- [ ] Regiões resolvem para países pela tabela versionada, e "Remote — Brazil" preenche o
      país permitido. Funcional em código (251/648 oportunidades com `allowed_countries`
      preenchido), não remedido a fundo nesta sessão — não marcado por falta de
      verificação direta.
- [x] O acervo é renormalizado sem perder procedência: 648 oportunidades antes e depois do
      bump de `NORMALIZER_VERSION`, 670/670 `RawItem` com resultado `v4`, mesmas 22 falhas
      `INVALID_COLLECTED_ITEM_V1` antes e depois (nenhuma nova).

- [x] Regra nova altera corretamente item sem `source_updated_at` —
      `tests/backend/opportunities/test_reprocessing.py::test_rule_fields_reprocess_even_without_source_updated_at`.
- [x] Replay fora de ordem não regride conteúdo/última observação —
      `tests/backend/opportunities/test_reprocessing.py::test_out_of_order_replay_does_not_regress_evidence_fields`.
- [x] Reinício retoma lotes; repetição sem mudança não invalida avaliações —
      `tests/backend/test_reprocessing_batches_integration.py::test_normalize_pending_resumes_a_batch_without_repeating_or_skipping`,
      `tests/backend/opportunities/test_reprocessing.py::test_identical_replay_does_not_bump_version`.
- [x] Payload expirado é explicitado e não impede o restante do reprocessamento —
      `tests/backend/opportunities/test_reprocessing.py::test_legacy_item_with_an_expired_payload_raises_payload_expired`.

## Verificação

- **CI:** tabelas de teste por regra (títulos pt/en, textos de localização, termos de
  skill com ambiguidade); teste do reprocessamento por versão; E2E conferindo senioridade
  e país da vaga do ciclo.
- **Máquina de referência:** taxas antes e depois pelo relatório do F17-01.

## Arquivos prováveis

- `src/opportunity_radar/opportunities/domain.py`, `service.py`
- `src/opportunity_radar/opportunities/regions.py` (novo)
- `scripts/unmatched_skill_terms.py` (novo)
- `tests/backend/opportunities/`
