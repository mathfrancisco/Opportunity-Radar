# F50-01 — Linha de base da classificação por descrição

- **Data:** 2026-10-05
- **Card:** F50-01 da [SPEC 50](../50-spec-motor-de-busca.md)
- **Base:** banco da stack `spec46full`, lido só com `SELECT`, com o código da branch
  `f50-motor-de-busca`. O worker estava coletando durante a leitura.
- **Status:** cobertura medida. **Precisão não medida**: falta o gold set rotulado (§3).

## 1. O que foi medido

As regras `seniority-v4`, `work-mode-v7` e `allowed-countries-v2` foram aplicadas a todas as
14.593 vagas com descrição. Cobertura é a parcela de vagas em que a regra emite um valor
diferente de `UNKNOWN`. As regras continuam desligadas em produção
(`content_classification_v4_enabled = False`); nada foi gravado.

Workday não aparece: as vagas dessa fonte chegam sem descrição (P3 da spec).

A medição cobre todas as vagas com descrição, não só as das áreas-alvo. As metas do §1 da
spec são sobre as áreas-alvo; o recorte por área fica para a medição da fase 2.

## 2. Cobertura por tipo de fonte

| Fonte | Vagas com descrição | `seniority` | `work_mode` | `allowed_countries` |
|---|---|---|---|---|
| greenhouse | 7.189 | 71,4% | 29,5% | 7,4% |
| lever | 2.932 | 48,8% | 58,7% | 16,2% |
| ashby | 2.769 | 62,4% | 42,3% | 22,3% |
| workable | 803 | 60,7% | 14,3% | 1,6% |
| teamtailor | 438 | 23,7% | 49,5% | 0,2% |
| hacker_news | 297 | 34,7% | 81,5% | 8,4% |
| factorial | 147 | 57,1% | 97,3% | 0,0% |
| remotive | 18 | 61,1% | 5,6% | 66,7% |
| **Total** | **14.593** | **62,2%** | **39,3%** | **11,5%** |

Emissões por regra, no total:

| Regra | Emissões |
|---|---|
| `seniority:title` | 6.497 |
| `seniority:description_years_min` | 2.301 |
| `seniority:description_years_range` | 263 |
| `seniority:description_entry_phrase` | 16 |
| `work_mode:title_location_metadata` | 4.303 |
| `work_mode:description_phrase` | 1.426 |
| `allowed_countries:location` | 1.412 |
| `allowed_countries:description` | 264 |

## 3. Precisão: bloqueada pelo gold set

O gold versionado (`docs/50-roadmap-motor-de-busca/rotulagem/f50-01-gold.json`) tem 39 casos
herdados do F20-23, sem tipo de fonte e sem nenhum caso de `allowed_countries`. O portão de
ativação exige 200 vagas rotuladas por uma pessoa, e o card pede 50 por tipo de fonte com
descrição. Com o gold atual, `gate.rules_passing` sai vazio.

Foi exportada uma amostra estratificada sem rótulo: 368 vagas (50 por fonte; 18 em
`remotive`, que é tudo o que há), 1.104 entradas, três campos por vaga. Ela não está no
repositório porque comentários do Hacker News podem trazer contato pessoal. Comando para
regerar:

```
python scripts/measure_content_classification.py \
  --sample-out f50-01-amostra-para-rotular.json --per-source-type 50 --seed 50
```

Depois de rotular (`valor_recomendado` e `evidencia` em cada entrada), as entradas entram no
gold versionado e o portão roda com `--gold <arquivo> --gold-text --check-gate`.

## 4. O que a linha de base diz sobre as metas do §1

- **`seniority` ≥ 70%:** alcançável. Com descrição, a regra já cobre 62%, e Greenhouse passa
  de 71%.
- **`work_mode` ≥ 70%:** incerta. A cobertura é 39% no total e 29% em Greenhouse, que é a
  maior fonte com descrição.
- **`allowed_countries` ≥ 60%:** fora de alcance com as regras atuais. A cobertura é 11,5%
  mesmo com a regra de descrição ligada, e ela só responde por 264 emissões. A meta precisa
  cair, ou a regra precisa de frases novas antes do F50-02. Isso também limita o aceite do
  F50-06 (elegibilidade decidida em ≥ 50%), que depende do país.

Essas três leituras são sobre cobertura. Nenhuma delas diz que a regra acerta: isso só o
gold rotulado responde.
