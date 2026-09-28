# Precisão das sugestões de classificação (F20-23)

- **Status:** Medido offline com casos sintéticos/anonimizados; medição real no acervo é
  o próximo passo (worker continua desligado, `worker_suggest_enabled: bool = False`).
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

## Tentativa de amostragem real — bloqueada por interrupção externa (2026-09-28)

O worker da branch `feature/f20-rotulos-2` tentou o passo 1 acima (selecionar ~30 vagas
reais com campo `UNKNOWN`, só leitura, no projeto `opportunity-radar` em medição de 7 dias).
Antes do `SELECT` de amostragem, o Docker Desktop da máquina caiu e voltou sozinho
(interrupção externa relatada pelo coordenador, não uma ação deste worker); ao voltar, os
containers `opportunity-radar-{api,worker,postgres,frontend}-1` estavam todos
`Exited (255)` e nenhum tem `restart` configurado no `compose.yaml` para voltar sozinho. Por
instrução explícita de nunca reiniciar o stack real, este worker não deu `docker compose up`
nem `docker start` — os containers seguiam parados ao fim desta sessão. **Nenhuma linha do
conjunto de 30 foi produzida.**

Comando de amostragem pronto para quando o stack voltar (só `SELECT`, sem PII nas colunas
lidas):

```bash
docker compose -p opportunity-radar exec -T postgres psql -U opportunity_radar -d opportunity_radar -c \
  "SELECT id, canonical_title, company_name, role_family, seniority, work_mode, published_at \
   FROM opportunities.opportunity \
   WHERE role_family = 'UNKNOWN' OR seniority = 'UNKNOWN' OR work_mode = 'UNKNOWN' \
   ORDER BY published_at DESC NULLS LAST LIMIT 30;"
```

Comando exato para a rodada de precisão real do passo 3, assim que a amostra de 30 estiver
rotulada manualmente (fora deste PR, chave real do Groq, nunca no projeto
`opportunity-radar`):

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
