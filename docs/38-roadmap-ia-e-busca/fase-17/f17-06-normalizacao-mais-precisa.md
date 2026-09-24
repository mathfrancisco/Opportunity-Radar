# CARD F17-06 — Normalização mais precisa: senioridade, skills, local e país

- **Status:** Backlog
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

## Critérios de aceite

- [ ] `seniority-v2` reduz a taxa de `UNKNOWN` à metade do baseline do F17-01.
- [ ] `skills-v2` atinge recall ≥ 90% no conjunto marcado.
- [ ] Regiões resolvem para países pela tabela versionada, e "Remote — Brazil" preenche o
      país permitido.
- [ ] O acervo é renormalizado sem perder procedência.

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
