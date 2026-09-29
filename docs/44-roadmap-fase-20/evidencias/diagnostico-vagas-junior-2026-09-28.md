# Diagnóstico — por que a busca traz tão poucas vagas junior/estágio (2026-09-28)

- **Pergunta original:** por que as buscas trazem tão poucas vagas de junior/estágio?
- **Bases usadas:**
  - `f20manual-postgres-1` (banco `f20manual`, cópia dos dados reais + fontes novas,
    67 fontes habilitadas em `acquisition.source_definition`) — base principal desta
    análise, 2288 oportunidades.
  - `opportunity-radar-postgres-1` (stack real de produção pessoal) — usado só para
    confirmar que o mesmo padrão aparece com o catálogo menor (17 fontes habilitadas,
    678 oportunidades); não sofreu nenhuma escrita, só `SELECT`.
- **Método:** consultas somente leitura (contagens agregadas, sem exportar texto
  integral de vaga) + leitura do normalizador em
  `src/opportunity_radar/opportunities/domain.py` + teste de regex isolado com o
  interpretador Python do host (nenhuma alteração de código nesta sessão).

## 1. Distribuição de senioridade (base `f20manual`, 2288 oportunidades)

| Senioridade | Contagem | % |
| --- | --- | --- |
| UNKNOWN | 1221 | 53,4% |
| MANAGER | 337 | 14,7% |
| SENIOR | 318 | 13,9% |
| STAFF | 162 | 7,1% |
| LEAD | 134 | 5,9% |
| DIRECTOR | 66 | 2,9% |
| MID | 32 | 1,4% |
| INTERN | 13 | 0,6% |
| JUNIOR | 5 | 0,2% |

**JUNIOR + INTERN = 18 de 2288 = 0,79%.** UNKNOWN confirma o débito já registrado em
F17-06/F20-02 (~50%, aqui 53,4%) — card F20-02 já registra que `seniority-v2` "não
atinge o critério no acervo real"; este diagnóstico não reabre F20-02, só quantifica o
efeito sobre junior/estágio especificamente.

Na stack real (678 oportunidades, 17 fontes) o padrão é o mesmo: UNKNOWN 335 (49,4%),
JUNIOR 3, INTERN 2 (0,74% juntos).

## 2. As 18 vagas junior/estágio vêm de 5 empresas, nunca de Ashby/Greenhouse

Cruzando `opportunity` → `source_occurrence` → `source_definition` (o coletor real
que trouxe cada vaga, não o tipo de `company_source`, que estava com muitos vínculos
nulos para Adobe/Factorial):

| Coletor | Oportunidades | Fontes habilitadas | JUNIOR | INTERN | UNKNOWN | % UNKNOWN |
| --- | --- | --- | --- | --- | --- | --- |
| Greenhouse | 709 | 24 | 1 | 0 | 399 | 56,3% |
| Ashby | 583 | 28 | 0 | 0 | 353 | 60,5% |
| Workday | 546 | 4 | 0 | 7 | 289 | 52,9% |
| Lever | 291 | 3 | 3 | 2 | 104 | 35,7% |
| Factorial | 134 | 2 | 1 | 4 | 87 | 64,9% |
| Teamtailor | 21 | 2 | 0 | 0 | 9 | 42,9% |
| Workable | 4 | 1 | 0 | 0 | 2 | — |

**Ashby (o maior conjunto: 583 vagas em 28 fontes) não trouxe nenhuma vaga JUNIOR ou
INTERN — 0 de 583.** Greenhouse (709 vagas em 24 fontes) trouxe 1. Juntos, Ashby +
Greenhouse são 56,5% de todo o catálogo (1292 de 2288 vagas) e contribuem com **1 vaga
junior/estágio em 1292 (0,08%)**.

As 18 vagas junior/estágio reais vêm de apenas 5 empresas:

| Empresa | Coletor | Vagas junior/estágio | Exemplos |
| --- | --- | --- | --- |
| Adobe | Workday | 7 INTERN | "2027 Intern - Machine Learning Engineer", "...Software Engineer" |
| CI&T | Lever | 3 JUNIOR | "[Job-31845] Desenvolvedor(a) ServiceNow Junior — APP ENGINE, Brazil" |
| Factorial | Factorial (autocoleta) | 1 JUNIOR + 4 INTERN | "BDR Jr.", "Strategy Analyst Internship" |
| Lokalise | Greenhouse | 1 JUNIOR | "Junior IT Operations Specialist (1-Year Fixed-Term Contract)" |
| Spotify | Lever | 2 INTERN | "CoLM 2026 — Intern", "RecSys 2026 — Intern" |

A UNKNOWN não escondia um segundo bolso de vagas junior/estágio: nenhum título em
todo o acervo (2288 vagas) contém `estagi`, `trainee`, `jovem`, `aprendiz`, `graduate`
ou `entry` fora dos 5 casos acima — e um teste com limite de palavra correto
(`\m…\M` no `psql`, para não capturar substrings como "intern" dentro de "international")
achou só 9 vagas UNKNOWN com "junior" na descrição, todas linguagem de diversidade/
inclusão tipo "welcome candidates from junior to senior", nenhuma vaga real de nível
junior. Zero UNKNOWN tinha `estágio`/`trainee`/`intern` na descrição. **Conclusão: o
problema não é UNKNOWN escondendo junior/estágio — é o catálogo simplesmente não
coletar vagas desse nível.**

## 3. Viés de catálogo é a causa dominante (ranking de impacto)

### #1 — Viés de catálogo: Ashby/Greenhouse trazem quase zero junior/estágio (maior impacto, ~99% do problema)

67 fontes habilitadas, majoritariamente Ashby/Greenhouse de empresas de tecnologia
internacionais (startups late-stage, scale-ups). Essas empresas publicam
majoritariamente vagas pleno+ no board principal; vagas de estágio/trainee/university,
quando existem, ficam em boards separados que o catálogo não coleta (ver #4).

### #2 — Nenhum board de "early careers"/universidade coletado separadamente (mesma causa raiz, ângulo de cobertura)

Verificado para as 3 empresas citadas na tarefa:

- **Nubank** (`company_source`/`source_definition`, Ashby): só um board configurado,
  `board_identifier: "nubank"` — o board principal. Nubank tem programa de trainee/
  estágio conhecido no Brasil, historicamente via Gupy (fechado por ToS, F20-32) ou
  página própria; nenhum board Ashby separado de "university"/"early careers" foi
  identificado ou configurado. 119 vagas coletadas da Nubank, 0 JUNIOR/INTERN.
- **Stripe**: 2 vagas coletadas, ambas UNKNOWN — volume baixo demais para avaliar;
  não há fonte separada de early-careers configurada.
- **Datadog**: 3 vagas coletadas, todas UNKNOWN — mesmo caso.

Não há, em nenhuma das 67 fontes, um `source_definition.configuration` com
`department`/`board_token` distinto de "early careers" ou "university" — cada empresa
tem exatamente um board configurado.

### #3 — Normalizador de senioridade tem lacunas de palavra-chave (baixo impacto atual, alto impacto futuro/latente)

`src/opportunity_radar/opportunities/domain.py:845-877` (`infer_seniority`,
`SENIORITY_MAPPING_VERSION = "seniority-v2"` — a tarefa citava "v6", não existe essa
versão no código; a versão real é v2, a mesma que F20-02 já sinalizou como
insuficiente para UNKNOWN).

Testado com o interpretador Python do host (sem alterar código):

| Título de teste | Capturado por `infer_seniority`? |
| --- | --- |
| "Software Engineer Intern" | Sim → INTERN |
| "Junior Software Engineer" / "Jr Developer" | Sim → JUNIOR |
| "Estágio em Dados" | Sim → INTERN |
| **"Estagiário de Engenharia de Software"** | **Não → UNKNOWN** |
| **"Vaga para Estagiário"** | **Não → UNKNOWN** |
| **"Trainee Program 2026" / "Programa Trainee 2026"** | **Não → UNKNOWN** |
| **"Entry Level Software Engineer"** | **Não → UNKNOWN** |
| **"New Grad Software Engineer"** | **Não → UNKNOWN** |
| **"Graduate Software Engineer"** | **Não → UNKNOWN** |
| **"Early Career Software Engineer"** | **Não → UNKNOWN** |
| **"Apprentice Developer" / "Aprendiz de TI"** | **Não → UNKNOWN** |

Causa técnica: o padrão de INTERN é `r"\best[aá]gi[oa]\b"` — casa só "estágio"/"estágia"
(a forma substantivo), não a forma adjetiva/pessoa "estagiário"/"estagiária", que é a
forma mais comum em título de vaga brasileira ("Vaga de Estagiário de X"). Além disso
`trainee`, `entry level`, `new grad`, `graduate`, `early career`, `apprentice` e
`aprendiz` não têm nenhum padrão — essas vagas caem em UNKNOWN mesmo com o termo
explícito no título.

**Impacto atual medido: zero.** Nenhum título no acervo real (2288 vagas) contém esses
termos hoje — é um bug latente, não a causa da escassez atual. Mas trava o card F20-60
(Nubank, CI&T e outras empresas brasileiras do mapa de carreira) no momento em que
essas fontes de fato trouxerem "Estagiário"/"Trainee" — a vaga vai continuar caindo em
UNKNOWN mesmo depois de coletada.

### #4 — `infer_seniority` só olha o título (nunca a descrição) — risco de design, sem evidência de impacto atual no acervo real

`infer_seniority`/`seniority_classification` (domain.py:845-937) usa só `title` +
metadados estruturados (`HOMOLOGATED_SENIORITY_FIELDS` está vazio para
ashby/greenhouse/lever — nenhum desses ATS expõe campo estruturado de nível nos
fixtures reais, comentário no próprio código confirma). Nunca olha `description`.
Compare com `infer_work_mode` (domain.py:801-842), que tem fallback explícito de
descrição via `_work_mode_from_description` com padrões de seção estreitos, e um
comentário explicando por quê (evitar falso positivo de "colega remoto" no meio do
texto).

Testei estender uma busca ingênua de palavra-chave à descrição contra as 1221 vagas
UNKNOWN reais: sem limite de palavra, "intern" capturou "international"/"internal" em
massa (falso positivo). Com limite de palavra correto, recuperei zero
estágio/trainee real e 9 menções de "junior" que eram boilerplate de diversidade, não
vaga junior de verdade. **Conclusão prática: estender para descrição com um scan
simples não teria adicionado nenhuma vaga junior/estágio real nesta base — o problema
não está em não olhar a descrição, está em não haver vaga desse nível coletada.** Mas
o gap de design existe e pode importar em outros ATS/formatos onde o nível só aparece
no corpo (ex.: seção "Early Career Program" da Greenhouse), então listo como card de
baixo risco/baixo esforço, não como causa comprovada.

### #5 — Filtro de senioridade do matching pode esconder JUNIOR/INTERN adicionalmente (dependente do perfil do usuário, não é bug de coleta)

`src/opportunity_radar/matching/domain.py:423-435` (`_seniority_filter`): se
`opportunity.seniority` é UNKNOWN, o filtro retorna UNKNOWN (não bloqueia). Se a vaga
tem JUNIOR/INTERN e o perfil não inclui essas senioridades em
`profile.accepted_seniorities`, a vaga é marcada `INELIGIBLE` e desaparece da tela de
matches (não da API de busca geral, que não filtra por padrão —
`dashboard/search_filters.py:41-42` só filtra por senioridade se o usuário pedir
explicitamente). Isso é comportamento esperado, dirigido pelo perfil, não um bug — mas
combinado com #1-#2 (tão poucas vagas junior/estágio para começar), qualquer perfil que
não tenha JUNIOR/INTERN marcado explicitamente as esconde ainda mais na tela de
matches. Não é causa raiz isolada; listo como fator agravante dependente de
configuração do perfil, sem número de impacto próprio (não avaliei perfis de usuário
reais nesta sessão).

## 4. Interação com a regra de recência de 14 dias (card em elaboração por outro worker)

Não encontrei nenhum card ou trecho de código já mergeado com essa regra nesta sessão
(branch `feature/f20-junior-diagnostico`, a partir de `ddc0484` — busquei em
`docs/44-roadmap-fase-20/` e no histórico de todas as branches locais, nada com "14
dias"/"recência" além de menções genéricas de recência em outros cards de dedupe). Não
posso avaliar a implementação real; registro só a interação esperada, para quem
escrever esse card considerar:

- Vagas de estágio/trainee/"programa" costumam ficar publicadas por mais tempo (ciclo
  anual, ex.: "2027 Intern" da Adobe, "CoLM 2026 — Intern" do Spotify) do que vagas
  individuais de tech pleno/senior, que tendem a fechar ou ser republicadas em ciclos
  mais curtos. Uma regra de recência de 14 dias sem exceção para "programas" penalizaria
  desproporcionalmente o subconjunto de vagas junior/estágio que já é minúsculo (18 de
  2288), reduzindo ainda mais o que aparece na busca.
- A tarefa já cita "exceção para programas" como algo a ser considerado — concordo com
  a necessidade, com base nos exemplos reais acima (Adobe/Spotify), mas não tenho
  visibilidade do card real para validar se essa exceção já está no escopo dele.

## 5. Ranking de causas por impacto

1. **Viés de catálogo (Ashby/Greenhouse dominam e não trazem junior/estágio; nenhum
   board de early-careers/university coletado)** — explica ~99% da escassez observada
   (18 de 2288 vagas, concentradas em 5 empresas de 67 fontes).
2. **Normalizador de senioridade com lacunas de palavra-chave (`estagiário`, `trainee`,
   `entry level`, `new grad`, `graduate`, `early career`, `apprentice`/`aprendiz`)** —
   impacto atual medido zero (nenhum título do acervo usa esses termos hoje), mas bug
   latente que vai comer parte do ganho de qualquer card que traga fontes brasileiras
   de estágio/trainee (F20-60 e além).
3. **`infer_seniority` não olha `description`** — gap de design real, mas sem evidência
   de que teria capturado vagas junior/estágio reais nesta base; baixo risco.
4. **Filtro de senioridade do matching dependente do perfil** — agravante potencial na
   tela de matches, não na busca geral; sem número de impacto medido.
5. **Regra de recência de 14 dias sem exceção para programas (card de outro worker)** —
   risco futuro de agravar o problema #1, não avaliável em código nesta sessão.

## 6. Incertezas e limites

- A base `f20manual` é descrita como "cópia dos dados reais + fontes novas"; não
  confirmei se as 67 fontes habilitadas nela são exatamente as 67 fontes habilitadas
  na stack de produção real no momento — usei os números da própria base indicada pela
  tarefa.
- Não tive acesso ao card real da regra de recência de 14 dias (ainda não commitado
  por outro worker); a seção 4 é só a interação esperada, não uma avaliação do código.
- Não avaliei perfis de usuário reais (`profile.accepted_seniorities`) — a seção 5 do
  ranking (#4) é qualitativa, sem contagem de quantos perfis excluem JUNIOR/INTERN.
- Os testes de regex do normalizador foram feitos isolando os padrões exatos do
  código-fonte no interpretador Python do host, não executando a suíte de testes do
  projeto (nenhum teste automatizado foi rodado ou alterado nesta sessão, por
  instrução: só diagnóstico + docs).
