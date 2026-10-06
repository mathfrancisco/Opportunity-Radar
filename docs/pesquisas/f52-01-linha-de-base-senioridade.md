# F52-01 — Linha de base do classificador de senioridade

- **Data:** 2026-10-06
- **Card:** F52-01 da [SPEC 52](../52-spec-aderencia-ao-nivel.md)
- **Base:** banco da stack `opportunity-radar-dev`, lido só com `SELECT`, com o worker
  coletando durante a leitura. Classificador `seniority-v3` (só o título).
- **Status:** contagem por padrão medida. **Precisão não medida**: a amostra do §4 ainda não
  foi rotulada.

## 1. Como reproduzir

```
python scripts/measure_seniority_titles.py
python scripts/measure_seniority_titles.py --sample-out amostra.json --seed 52
python scripts/measure_seniority_titles.py --sample docs/pesquisas/f52-01-amostra-senioridade.json
```

O primeiro comando lê os títulos das áreas-alvo (`SOFTWARE_ENGINEERING` e `DATA`, todos os
estados de ciclo de vida) e imprime o relatório. O terceiro não usa banco e roda no CI.

## 2. Níveis nas áreas-alvo

8.348 vagas. O valor gravado em `opportunity.seniority` é igual ao que o classificador devolve
para o título em todas elas.

| Senioridade | Vagas | % |
|---|---:|---:|
| `UNKNOWN` | 4.121 | 49,4 |
| `SENIOR` | 2.200 | 26,4 |
| `MANAGER` | 686 | 8,2 |
| `STAFF` | 592 | 7,1 |
| `INTERN` | 268 | 3,2 |
| `LEAD` | 213 | 2,6 |
| `MID` | 125 | 1,5 |
| `DIRECTOR` | 96 | 1,1 |
| `JUNIOR` | 47 | 0,6 |

Cobertura (nível conhecido): **50,6%**.

## 3. Os `UNKNOWN` por padrão

Cada título entra no primeiro padrão que se aplica, nesta ordem.

| Padrão | Vagas | % dos `UNKNOWN` | Exemplo |
|---|---:|---:|---|
| Acento | 138 | 3,3 | `Desenvolvedor(a) Backend Sênior - Node.js` |
| Dois níveis | 375 | 9,1 | `Senior Staff Machine Learning Engineer` |
| Numeral | 136 | 3,3 | `Software Development Quality Engineer II` |
| Palavra não coberta | 577 | 14,0 | `Data Architect` |
| Sem sinal | 2.895 | 70,2 | `Data Engineer - Finance` |

Definições:

- **Acento:** o título é classificado quando os acentos são removidos.
- **Dois níveis:** o título cita palavras de dois ou mais níveis.
- **Numeral:** `II`, `III` ou `IV` em qualquer posição, ou `I`, `V` e 1 a 5 logo depois de um
  cargo. Um número solto não conta: quase sempre é o código da requisição.
- **Palavra não coberta:** o título tem uma palavra de nível que o classificador não lê.
- **Sem sinal:** nenhum dos anteriores.

Combinações em "dois níveis":

| Combinação | Vagas |
|---|---:|
| `SENIOR` + `MANAGER` | 167 |
| `SENIOR` + `STAFF` | 99 |
| `SENIOR` + `LEAD` | 22 |
| `LEAD` + `MANAGER` | 17 |
| `MID` + `SENIOR` | 15 |
| `SENIOR` + `DIRECTOR` | 13 |
| `STAFF` + `MANAGER` | 13 |
| Outras 12 combinações | 29 |

Em 29 das 375, a combinação inclui `JUNIOR` ou `MID`. Em 27 delas é uma faixa (`Pl/Sr`,
`Junior, Pleno e Sênior`), assunto da pergunta Q1 da spec; nas outras 2, `MID` vem de
`Middle East`, um falso sinal que o F52-02 precisa evitar.

Palavras em "palavra não coberta":

| Palavra | Vagas |
|---|---:|
| `architect` / `arquiteto` | 329 |
| `specialist` | 59 |
| `associate` | 41 |
| `founding` | 39 |
| `head of` | 27 |
| `analista` | 22 |
| `expert` | 19 |
| `new college grad` | 11 |
| `phd` | 10 |
| Demais (`distinguished`, `supervisor`, `university`, `coordenador`, `vp`, `cto`, `campus`, `student`) | 20 |

`specialist`, `founding`, `analista` e `expert` não dizem um nível por si; estão na lista
para ficarem visíveis, não como proposta de regra.

## 4. Amostra para rotular

`docs/pesquisas/f52-01-amostra-senioridade.json`: 300 títulos distintos, 200 `UNKNOWN` e 100
classificados, sorteados com `--seed 52`. A ordem é embaralhada e a resposta do classificador
não aparece, para o rótulo não ser guiado por ela.

Preencher `nivel_rotulado` em cada entrada com um destes valores:

- um nível: `INTERN`, `JUNIOR`, `MID`, `SENIOR`, `STAFF`, `LEAD`, `MANAGER`, `DIRECTOR`;
- `UNKNOWN`, quando o título não diz o nível;
- uma lista, quando o título diz uma faixa: `["MID", "SENIOR"]`.

`observacao` é livre. Com a amostra rotulada, o terceiro comando do §1 devolve a precisão por
nível e, para os `UNKNOWN`, quantos de cada padrão tinham nível no título.

## 5. Metas do §1 da spec

| Métrica (áreas-alvo) | Spec (2026-10-05) | Medido (2026-10-06) | Meta | Situação da meta |
|---|---:|---:|---:|---|
| Vagas com senioridade conhecida | 50,8% | 50,6% | 80% | Mantida; depende do F52-03 |
| Vagas `JUNIOR` ou `MID` | 147 | 172 | 600 | Mantida |
| Topo com nível acima do aceito | 164 de 1.515 | 78 de 847 | 0 | Mantida; ver nota |
| Topo com senioridade `UNKNOWN` | 76% | 81,5% (690 de 847) | menos de 30% | Mantida |

As duas linhas de "topo" contam avaliações `RECOMMENDED` ou `HIGH_PRIORITY` do perfil ativo
(`b0ad7958`). Os números da spec somavam todas as versões do perfil. Em 2026-10-06 a
reavaliação em `matching-v4` estava em andamento; as 78 avaliações acima do nível são todas
de `matching-v2` ou `matching-v3`.

**Teto da cobertura só com o título: 65,3%.** Se todo título com algum sinal fosse
classificado, sobrariam os 2.895 sem sinal. A meta do F52-02 (65% só com o título) fica no
limite: exige resolver praticamente todos os outros 1.226, inclusive palavras que não dizem
nível. Proposta: baixar a meta do F52-02 para 60% e manter os 80% do §1 para o F52-03, que
lê a descrição. A decisão é do dono.

## 6. O que não foi medido

- Precisão por nível: depende dos rótulos do §4.
- Quantos títulos "sem sinal" têm nível na descrição: é a medição do F52-03.
