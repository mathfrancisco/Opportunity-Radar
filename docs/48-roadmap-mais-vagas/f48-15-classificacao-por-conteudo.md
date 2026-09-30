# F48-15 — Classificação por conteúdo (V08)

**Status:** código pronto e testado, **desligado** (`CONTENT_CLASSIFICATION_V4_ENABLED=false`).
Ativar exige o gabarito humano ampliado (passo abaixo); nenhum reprocessamento ocorreu.

## Resultado

- `opportunities/content_classification.py`: `seniority-v4` e `work-mode-v7`. Regions:
  `regions.py::resolve_allowed_countries_v2` (`allowed-countries-v2`).
- Ordem de evidência: campo estruturado do coletor > título/localização > descrição. Todo
  valor sai com `rule` e `evidence` (trecho literal); sem evidência ou com regras em
  desacordo o valor fica `UNKNOWN` (nunca se grava sem evidência).
- Registro: com a chave ligada, `normalization_result.reasons` recebe
  `SENIORITY_CLASSIFICATION` (v4, mesmas chaves de antes + `rule`/`evidence`),
  `WORK_MODE_CLASSIFICATION` e `ALLOWED_COUNTRIES_CLASSIFICATION`, e
  `allowed_countries_version` grava `allowed-countries-v2`. Desligada, o caminho é o de
  sempre (`seniority-v3`, `work-mode` v6, `regions-v1`) e nada muda.

### Regras de senioridade pela descrição

| Regra | Efeito |
| --- | --- |
| `description_years_range` (`N-M years`/`N a M anos` de experiência) | JUNIOR 0-2, MID 3-5, SENIOR se o piso for >= 5 |
| `description_years_min` (`N+ years`, `at least N`, `mínimo de N anos`, `pelo menos N`) | JUNIOR 0-2, MID 3-4, SENIOR >= 5 |
| `description_entry_phrase` (entry-level position, no experience required, sem experiência prévia, nível júnior, procuramos um júnior) | JUNIOR |
| `description_intern_phrase` (this is an internship, vaga/programa de estágio) | INTERN |

**Sobreposição, explícita.** O 5 pertence a SENIOR quando é piso (`5+`, `5-7`, `5 years`) e a
MID só como teto de faixa que começa em 3 ou 4 (`3-5`). Faixa que atravessa dois baldes
(`1-3`, `2-4`, `3-6`) é ambígua: `UNKNOWN`. Várias evidências na mesma descrição só valem se
apontarem o mesmo nível; discordância (`entry-level` com `5+ years`) vira `UNKNOWN`. Anos
falando da empresa ("our 15 years of experience", "temos 10 anos") são ignorados.

Escolha conservadora (precisão antes de cobertura): a descrição que lista "5 anos no total,
2 anos de Kubernetes" fica `UNKNOWN`. Reavaliar com o gabarito ampliado se a meta de 30 %
(decisão 7) não for atingida.

`work-mode-v7` estende os padrões estreitos da v6 com frases PT/EN (`100% remota`, `regime
híbrido`, `vaga presencial`, `this is a fully remote position`...); título/localização/
metadado vencem, conflito com a descrição vira `UNKNOWN`. `allowed-countries-v2`: localização
(tabela v1) primeiro; senão frases de permissão na descrição (`must be located in`, `remote
within`, `authorized to work in`, `remoto no`, `residentes no`); nome de país solto nunca vale;
dois países diferentes viram `UNKNOWN`.

## Medição de precisão (somente leitura)

`scripts/measure_content_classification.py` só faz `SELECT` (o `--dry-run` é aceito por
clareza). Reporta precisão por regra, taxa `UNKNOWN` antes/depois (gabarito e, com
`--acervo-limit N`, o acervo com descrição) e o portão:

```
DATABASE_URL=... python scripts/measure_content_classification.py --check-gate
python scripts/measure_content_classification.py --evidence-as-text   # sem banco (proxy fraco)
```

Portão (`content_classification.gate_passes`): cada regra >= 90 % **e** gabarito com >= 200
vagas distintas; regra sem nenhuma emissão ou relatório vazio falham (fail closed). Sai com
código 1 quando `--check-gate` e o portão não passa.

**Gabarito atual (F20-23):** `docs/44-roadmap-fase-20/rotulagem/f20-23-amostra-unknown.json`,
30 vagas / 37 campos (24 senioridade, 13 modo de trabalho; `role_family` ignorado). Ele guarda
só o trecho de evidência, não a descrição inteira, então a medição real precisa do banco.
Sem banco, `--evidence-as-text` usa o trecho como texto: resultado circular (o trecho foi
escolhido para sustentar o rótulo) e n=37, portanto **não vale como precisão** e o portão
falha pelo tamanho (< 200).

## Rotulagem humana (pendente, não automatizável)

1. Gerar a amostra sem rótulos: `DATABASE_URL=... python scripts/measure_content_classification.py
   --sample-out rotulagem/f48-15-amostra.json --sample-size 200 --seed 1` (uma entrada por
   vaga e campo, com trecho da descrição; a proposta da regra **não** aparece).
2. O operador preenche `valor_recomendado` (enum), `recomendacao` (`corrigir` ou
   `manter_unknown_evidencia_insuficiente`) e `evidencia` em cada entrada, no mesmo formato do
   gabarito F20-23. Ninguém mais preenche rótulos.
3. Juntar ao gabarito (`casos`) e rodar `--check-gate --gold <arquivo>` com o banco.
4. Se passar: backup verificado (`scripts/backup.py`, restore-check), ligar
   `CONTENT_CLASSIFICATION_V4_ENABLED=true`, subir `NORMALIZER_VERSION` para `v7` (reprocessa as
   vagas) e medir `seniority_unknown_rate` (meta <= 30 % nas vagas com descrição).

## Fora do escopo / riscos

- Reprocessar não roda aqui. `work_mode` entra no fingerprint da vaga: `UNKNOWN` virar
  `REMOTE`/`HYBRID` muda o fingerprint; a identidade também usa `external_id` e URL, mas
  convém conferir duplicatas após o reprocessamento (F48-09).
- Sugestões por IA seguem só para o resíduo, com aceite humano (F20-76).
- Ampliar `role_family` não faz parte deste card.
