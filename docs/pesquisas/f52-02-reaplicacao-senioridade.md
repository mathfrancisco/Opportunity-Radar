# F52-02 — Reaplicação do `seniority-v5` no catálogo

- **Data:** 2026-10-06
- **Card:** F52-02 da [SPEC 52](../52-spec-aderencia-ao-nivel.md)
- **Base:** cópia da base `opportunity-radar-dev` (`pg_dump` de 2026-10-06, 16h44 UTC),
  restaurada num projeto Compose descartável. Nada foi gravado: os números abaixo são de
  `scripts/retag_seniority.py` em dry-run.
- **Status:** dry-run feito. Precisão **não medida**: depende dos rótulos do F52-01.

## 1. Como reproduzir

```
python scripts/retag_seniority.py            # dry-run: não grava
python scripts/retag_seniority.py --apply    # grava, 500 vagas por transação
```

O script relê, para cada vaga, a evidência da ocorrência vista por último e recalcula só a
senioridade, com as regras de conteúdo ligadas no ambiente (hoje, nenhuma). Vaga cujo nível
muda recebe o nível novo e `version + 1`, uma vez; o worker a reavalia. A evidência
(`SENIORITY_CLASSIFICATION` em `reasons`) é reescrita sempre que difere, para a versão gravada
ser a que produziu o valor; isso sozinho não sobe `version`. Uma segunda execução relata
zero mudanças. O dry-run levou 12 minutos para 31.218 vagas.

## 2. Catálogo inteiro

31.218 vagas lidas, nenhuma pulada. **4.732 mudam de nível** (4.732 incrementos de
`version`). As 31.218 evidências são reescritas, porque todas citavam `seniority-v3`.

| Senioridade | Antes | Depois |
|---|---:|---:|
| `UNKNOWN` | 17.966 | 13.575 |
| `SENIOR` | 4.751 | 5.914 |
| `MANAGER` | 3.906 | 5.448 |
| `DIRECTOR` | 854 | 1.301 |
| `STAFF` | 1.184 | 1.244 |
| `JUNIOR` | 213 | 1.128 |
| `LEAD` | 1.037 | 1.125 |
| `INTERN` | 889 | 808 |
| `MID` | 418 | 675 |

Transições:

| De → para | Vagas | O que é |
|---|---:|---|
| `UNKNOWN` → `MANAGER` | 1.543 | dois níveis (`Senior Manager`, `Staff Product Manager`) |
| `UNKNOWN` → `SENIOR` | 1.181 | acento, `Architect`, `III`, `Senior/Staff` como faixa |
| `UNKNOWN` → `JUNIOR` | 831 | `Associate`, numeral `I`, `Júnior` |
| `UNKNOWN` → `DIRECTOR` | 443 | `Head of`, `Senior Director` |
| `UNKNOWN` → `MID` | 318 | numeral `II`, `Pleno` com acento ou faixa |
| `UNKNOWN` → `STAFF` | 98 | `Senior Staff`, `Senior Principal` |
| `UNKNOWN` → `LEAD` | 88 | `Senior ... Lead` |
| `INTERN` → `JUNIOR` | 84 | `Entry Level`, `New Grad` (Q3) |
| `MID` → `UNKNOWN` | 77 | `Mid-Market`, `Middle East`, `PL/SQL`: falso sinal do v3 |
| `STAFF` → `UNKNOWN` | 37 | `Member of Technical Staff` |
| `SENIOR` → `MID` | 21 | `Semi Senior` |
| Outras 7 | 11 | `Head of ... Middle East`, faixas, `UNKNOWN` → `INTERN` |

## 3. Áreas-alvo

8.484 vagas em `SOFTWARE_ENGINEERING` e `DATA`; 1.120 mudam.

| Métrica | Antes | Depois | Meta |
|---|---:|---:|---:|
| Senioridade conhecida | 50,5% | **62,7%** | 60% só com o título |
| Vagas `JUNIOR` ou `MID` | 177 | **408** | 600 (F52-06) |

A meta de cobertura do F52-02 (60%) é atingida no dry-run. O teto medido no F52-01 era 65,3%.

## 4. O que conferir antes de confiar no número

O dry-run mostra o que muda, não se está certo. Pontos vistos na amostra de transições:

- **`Manager` como cargo, não nível.** `Product Manager`, `Account Manager`, `Program
  Manager`, `Community Manager` viram `MANAGER`. Já era assim no v3 com a palavra sozinha; o v5
  estende a títulos com dois níveis (`Senior Product Manager` era `UNKNOWN`, vira `MANAGER`).
  Na proposta de rótulos, 5 das 14 discordâncias são desse tipo.
- **`Associate` como cargo.** `Finance Associate`, `Data Labeling Associate` viram `JUNIOR`.
- **`Director` como cargo.** `Art Director`, `Account Director` viram `DIRECTOR`. Fora das
  áreas-alvo.
- **Numeral arábico.** `Software Engineer 3` continua `UNKNOWN`.
- **`Liderança Técnica`, `Intermediate`.** Continuam `UNKNOWN`.

Corrigido durante o dry-run: `Associate Intern` e `Graduate Trainee` saíam `JUNIOR` (o nível
mais alto); passam a `INTERN`.

Ensaio, **não medição**: se o dono confirmasse as 300 sugestões da proposta sem alterar
nenhuma, a precisão seria 95,3% (142 de 149 emissões), com `MANAGER` em 79,3% e `JUNIOR` em
87,5%. O número só vale depois da revisão, em
`docs/pesquisas/f52-01-amostra-senioridade-proposta.json`:

```
python scripts/measure_seniority_titles.py --sample docs/pesquisas/f52-01-amostra-senioridade-proposta.json
```

## 5. Efeito no matching

4.732 vagas mudam de `version` e são reavaliadas pelo worker (cerca de 3.000 por hora). Com o
`matching-v4`, vaga que passa de `UNKNOWN` a `SENIOR` ou acima deixa o topo do perfil ativo;
vaga que passa a `JUNIOR` ou `MID` continua elegível.
