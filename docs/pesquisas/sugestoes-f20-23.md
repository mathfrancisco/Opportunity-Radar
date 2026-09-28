# Precisão das sugestões de classificação (F20-23)

- **Status:** Medido offline com casos sintéticos/anonimizados. Amostra real de 30 vagas
  `UNKNOWN` com gabarito rotulado em 2026-09-28 (`docs/44-roadmap-fase-20/rotulagem/
  f20-23-amostra-unknown.md`); falta só a rodada real do Groq contra esse gabarito, fora do
  escopo deste worker (worker continua desligado, `worker_suggest_enabled: bool = False`).
- **Card:** [F20-23](../44-roadmap-fase-20/fase-20/f20-23-classificacao-assistida.md)
- **SPEC:** [43-spec-llm-cloud-e-consolidacao.md](../43-spec-llm-cloud-e-consolidacao.md), §6, §6.1
- **Contexto:** baseline real do acervo (`opportunity-radar`, medição de 7 dias em
  andamento, não tocado por este card) tem `seniority = UNKNOWN` em 328 das 648
  oportunidades (50,62%); o alvo do card/F17-06 é reduzir isso a metade. Este card não
  toca o projeto `opportunity-radar` nem chama o Groq — a implementação usa
  `httpx`/`AIRouter` com um provedor fake em todos os testes.

## Por que a medição aqui é offline

O card exige medir precisão **antes** de ligar o job por padrão (critério de aceite:
"Precisão medida registrada antes de ligar por padrão"). Este worker não pode chamar o
Groq real (regra do PR) nem tocar o acervo do projeto `opportunity-radar` em execução.
A medição abaixo usa 12 vagas sintéticas, com texto e evidência inventados (nenhum dado
do acervo real), rodadas contra o `AIRouter` com um provedor fake que responde um script
fixo — a mesma técnica usada em `tests/backend/opportunities/test_suggestions.py`. Ela
prova a lógica de gatilho, o descarte por evidência e a idempotência; **não** é uma
medição de precisão do modelo real, porque um provedor fake não erra do jeito que o
`fast` model erraria.

## Medição sintética (gatilho, descarte, idempotência)

| Caso | Campo pendente | Resposta simulada | Resultado esperado |
| --- | --- | --- | --- |
| 1–3 | `seniority` | valor + evidência literal no texto | sugestão `PENDING` criada |
| 4–6 | `work_mode` | valor + evidência que não aparece no texto | descartada (sem sugestão) |
| 7–9 | `role_family` | valor `null` (modelo inseguro) | nenhuma sugestão criada |
| 10 | campo já resolvido pela regra | modelo responde mesmo assim | resposta ignorada, sem sugestão |
| 11–12 | mesma oportunidade, mesma versão, 2 chamadas | 2ª chamada não deveria acontecer | 2ª chamada não ocorre (idempotência) |

Todos os 12 casos passam com o comportamento esperado
(`tests/backend/opportunities/test_suggestions.py`, executado com
`RUN_DATABASE_INTEGRATION=1` contra o Postgres isolado do projeto `f20cls`).

## Passo restante (fora do escopo deste PR)

1. Selecionar, no acervo real (projeto `opportunity-radar`, sem interromper a medição de
   7 dias), uma amostra de ~30 vagas com `seniority`, `role_family` ou `work_mode`
   `UNKNOWN` (dentro das 328/648 atuais).
2. Rotular manualmente o valor correto de cada campo ambíguo.
3. Rodar `suggest_fields_pending` uma vez, isolado (projeto docker compose separado do
   `opportunity-radar`, ou um script pontual chamando `opportunity_radar.opportunities
   .suggestions.suggest_fields` linha a linha) com `AI_ENABLED=true` e a chave real do
   Groq, **fora** deste PR.
4. Comparar a sugestão do modelo com o rótulo manual: registrar precisão (sugestões
   aceitáveis / sugestões com evidência válida) e taxa de descarte por evidência.
5. Só então decidir `worker_suggest_enabled=true` em produção, e atualizar este arquivo
   com o número medido.

## Passo 1/2 concluídos com o acervo real (2026-09-28)

A primeira tentativa (mesmo dia) foi interrompida por uma queda externa do Docker Desktop
antes do `SELECT` de amostragem — o worker da branch `feature/f20-rotulos-2` não deu nenhum
comando de escrita, parada ou reinicialização no stack real, por instrução explícita. Assim
que o stack voltou saudável (`2026-09-28T11:45Z`, dentro da janela de sete dias reiniciada),
o mesmo worker completou os passos 1 e 2: uma amostra real de 30 vagas com `role_family`,
`seniority` ou `work_mode` `UNKNOWN` (39 instâncias de campo no total), cada uma com o valor
recomendado e a evidência literal da `description` que o sustenta — ou "manter `UNKNOWN`"
quando nenhuma evidência textual convincente foi encontrada (30/39 corrigidos, 9/39
mantidos). Ver `docs/44-roadmap-fase-20/rotulagem/f20-23-amostra-unknown.md` e o dataset
`f20-23-amostra-unknown.json` — nenhum nome de pessoa, e-mail ou telefone aparece nas
evidências usadas.

Comando de amostragem usado (só `SELECT`, sem PII nas colunas lidas):

```bash
docker compose -p opportunity-radar exec -T postgres psql -U opportunity_radar -d opportunity_radar -c \
  "SELECT id, canonical_title, company_name, role_family, seniority, work_mode, published_at \
   FROM opportunities.opportunity \
   WHERE role_family = 'UNKNOWN' OR seniority = 'UNKNOWN' OR work_mode = 'UNKNOWN' \
   ORDER BY published_at DESC NULLS LAST LIMIT 30;"
```

Comando exato para a rodada de precisão real do passo 3, contra o gabarito acima (fora
deste PR, chave real do Groq, nunca no projeto `opportunity-radar`):

```bash
docker compose -p f20cls-precisao -f compose.yaml -f compose.dev.yaml run --rm \
  -e AI_ENABLED=true -e AI_PROVIDER=groq -e GROQ_API_KEY=<chave real> \
  api python -c "
import asyncio
from sqlalchemy.orm import Session
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.opportunities.suggestions import suggest_fields
from opportunity_radar.opportunities.models import OpportunityModel
import os

engine = create_database_engine(os.environ['DATABASE_URL'])
router = AIRouter()  # config real via env
with Session(engine) as session:
    ids = [...]  # os 30 ids rotulados manualmente
    for opportunity_id in ids:
        opportunity = session.get(OpportunityModel, opportunity_id)
        outcome = asyncio.run(suggest_fields(session, router, opportunity))
        print(opportunity_id, outcome.created, outcome.discarded_fields)
"
```

(o script pontual acima é ilustrativo — a forma exata pode variar, mas deve sempre rodar
num projeto docker compose isolado do `opportunity-radar`, nunca escrever no valor
canônico sem confirmação humana, e nunca usar a chave real do Groq em teste automatizado.)

## Achado no gabarito: bug determinístico de `work_mode`, corrigido sem LLM (branch `feature/f20-work-mode`)

Ao rotular o gabarito acima, os 13 casos de campo `work_mode` `UNKNOWN` (de 39 no total)
revelaram que a regra determinística (`infer_work_mode`,
`src/opportunity_radar/opportunities/domain.py`) nunca recebia a `description` como
evidência — só título, `location_text` e metadados estruturados. Vários empregadores reais
da amostra (Nubank, via Greenhouse) declaram o modo de trabalho só numa seção padronizada
da descrição ("Work Model for this Role" / "WORK MODEL FOR THIS ROLE"), então esses 11
casos ficavam `UNKNOWN` mesmo com evidência textual inequívoca. Corrigido diretamente na
regra determinística (não via sugestão assistida por LLM), de forma restrita: reconhece a
seção rotulada, a frase "<modo> model" (com ou sem parênteses), "fully on-site" e "on-site
N days a week" — nunca um scan genérico de `\bremote\b`/`\bhybrid\b`/`\bonsite\b` na
descrição inteira, para não confundir o status remoto de um colega ou boilerplate genérico
de "empresa remote-friendly" com o modo desta vaga.

**Medição offline contra os 13 casos rotulados** (`docs/44-roadmap-fase-20/rotulagem/
f20-23-amostra-unknown.json`, regressão em
`tests/backend/opportunities/test_domain.py::test_infers_work_mode_from_the_standardized_description_section`):

| Antes (regra atual, sem `description`) | Depois (regra corrigida) |
| --- | --- |
| 13/13 `UNKNOWN` | 11/13 corrigidos para o valor certo (`HYBRID`×8, `ONSITE`×2, mais 2 já
corretos via título "(Hybrid)"); 2/13 mantidos `UNKNOWN` de propósito |

Os 2 casos mantidos `UNKNOWN` (Trigger.dev, "If you're remote, we'll arrange..." e "Home
office ... Async working") têm evidência indireta demais para extrair com segurança sem
risco de falso positivo em outras vagas fora da amostra — mantidos `UNKNOWN` por decisão
consciente, não por limitação técnica. Zero casos resolvidos incorretamente; casos
negativos de guarda (status remoto de colega, boilerplate genérico, conflito
título-vs-seção) confirmados como `UNKNOWN` em teste.

`NORMALIZER_VERSION` subiu de `"v5"` para `"v6"` (`src/opportunity_radar/opportunities/
service.py`); único literal `v5` fora do símbolo encontrado foi a coluna
`normalizer_version` da fixture sintética `tests/backend/fixtures/pre_f20_dump.sql` (20
linhas), atualizada para `v6` junto. Suíte completa (`pytest`, `RUN_DATABASE_INTEGRATION=1`)
e `ruff`/`mypy` verdes após a mudança. Reprocessamento oficial do acervo real
(`opportunity-radar`) fica para depois da janela de sete dias em andamento, fora do escopo
deste branch.
