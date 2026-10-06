# `skills-v5` — termos das vagas sem skill (2026-10-06)

Pendência sem card registrada na [SPEC 52, §5](../52-spec-aderencia-ao-nivel.md) e no
[STATUS da SPEC 50](../50-roadmap-motor-de-busca/STATUS.md): vagas das áreas-alvo com
descrição e nenhuma skill depois do `skills-v4`.

## Regra do dono

Termo que é tecnologia inequívoca e aparece em 10 vagas ou mais entra na taxonomia como
`skills-v5`. Termo ambíguo fica numa lista, sem entrar.

## Medição

Base `opportunity-radar-dev`, 2026-10-06, somente leitura. Conjunto: vagas com
`role_family` em `SOFTWARE_ENGINEERING` ou `DATA`, descrição não vazia e nenhuma linha em
`opportunity_skill`. São **1.043** vagas (708 e 335).

`scripts/unmatched_skill_terms.py` conta cada termo uma vez por vaga. Sobre esse conjunto, a
lista bruta é dominada por palavras comuns (`be`, `looking`, `high`), porque a maior parte
dessas descrições não cita tecnologia: é texto institucional, ou a vaga não é técnica e
caiu numa área-alvo. Para achar tecnologia, a contagem foi repetida de duas formas: tokens
com forma de nome técnico (sigla, dígito, `+`, `#`, `.` ou maiúscula no meio) e uma lista de
cerca de 190 tecnologias conhecidas, casadas com o mesmo padrão de fronteira que a
taxonomia usa (`_skill_pattern`), no título e na descrição.

### Entraram na taxonomia

| Id | Alias | Vagas (de 1.043) | Onde aparece |
|---|---|---:|---|
| `linux` | `linux` | 25 | Canonical (14), Realm (5), outras |
| `etl` | `etl` | 11 | Artefact, Databricks, Pantheon, BRQ |
| `c++` | `c++` | 10 | Spotify, DoorDash, Weekday, ClickHouse |

As três juntas alcançam 42 das 1.043 vagas (4,0%). O ganho é pequeno: o `skills-v5` não
resolve a pendência das vagas sem skill, só fecha o que a regra permite.

### Ambíguos: não entraram

| Termo | Vagas | Motivo |
|---|---:|---|
| `excel` | 92 | Verbo em inglês ("everyone can excel"); 45 vêm do rodapé da Databricks |
| `analytics` | 89 | Área, não tecnologia |
| `api`, `apis` | 46, 76 | Conceito genérico; casa texto institucional |
| `embedded` | 54 | Adjetivo comum ("embedded in the team") |
| `databricks` | 50 | 45 são vagas da própria Databricks: nome da empresa |
| `localization`, `translation`, `labeling`, `annotation` | 49, 25, 41, 34 | Atividade, não tecnologia |
| `unity` | 45 | Todas são "Unity Catalog" no rodapé da Databricks |
| `robotics`, `networking`, `firmware` | 29, 24, 10 | Domínio, não tecnologia |
| `cursor` | 25 | Palavra comum e nome de produto |
| `salesforce` | 23 | Empresa e ferramenta de vendas; aparece em vagas não técnicas |
| `gpt`, `claude` | 19, 18 | Nome de produto do empregador (Anthropic) e uso genérico |
| `agile` | 19 | Método, e adjetivo comum |
| `spark` | 11 | "Spark Capital" (investidor) nas amostras lidas; palavra comum |
| `rails` | 11 | "payment rails" e URL `rails/active_storage` nas amostras lidas |

Abaixo de 10 vagas, sem decisão: `git` (9), `devops` (9), `oracle` (8), `android` (8),
`swift` (7), `ios` (7), `figma` (6), `tableau` (5), `power bi` (5), `looker` (5), `jira` (5),
`github` (5).

## Reaplicação

`scripts/retag_skills.py`, dry-run numa cópia da base de dev (projeto descartável
`or-skillsv5`, banco `opportunity_radar_skillsv5_copy`, restaurado do `pg_dump` das 18h20
UTC):

| | Sem `--include-untagged` | Com `--include-untagged` |
|---|---:|---:|
| Vagas lidas | 12.025 | 31.249 |
| Vagas alteradas | 12.025 | 12.507 |
| Vagas sem skill ao final | 0 | 18.742 |
| Linhas de skill antes (`skills-v4`) | 36.901 | 36.901 |
| Linhas de skill depois (`skills-v5`) | 38.433 | 38.954 |

O `retag_skills.py` só lia vagas que já tinham skill, porque a versão da taxonomia mora na
linha da skill. Uma vaga sem skill nunca seria relida, e as entradas novas não chegariam
justamente ao conjunto que motivou a mudança. A opção `--include-untagged` lê também essas
vagas. Com ela, 482 vagas que não tinham skill passam a ter (no catálogo inteiro, todas as
áreas, contando o título): de 19.224 sem skill para 18.742.

Uma vaga sem skill não guarda versão, então é relida a cada execução com a opção; só muda
na primeira.
