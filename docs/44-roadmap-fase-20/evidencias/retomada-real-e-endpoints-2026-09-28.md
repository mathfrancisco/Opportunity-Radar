# Retomada real (F20-39) e correção de endpoints (F20-36) — 2026-09-28

Evidência de execução real (não fabricada), pilha Docker Compose isolada `-p f20resume`
(`compose.yaml` + `compose.dev.yaml`). `AI_ENABLED=false` (padrão do compose) — nenhuma
chamada ao Groq nesta sessão. A pilha real `opportunity-radar` não foi parada,
reconstruída nem sofreu `exec` de escrita; ela reiniciou sozinha (política de restart)
quando o Docker Desktop do host caiu e voltou no meio desta sessão — ver nota na seção 5.

## Resumo

| Item | Resultado |
| --- | --- |
| F20-39: `kill -9` real do processo no meio de uma transação `execute()` | **Zero estado persistido** — confirma por dado real que o commit é atômico por execução (nenhum `SourceRun`, nenhum `RawItem`); coerente com `test_crash_before_commit_leaves_no_partial_state_and_retry_succeeds`. Não é um bug: é a garantia de atomicidade do card. |
| F20-39: queda real equivalente que **produz** `PARTIAL` com evidência | Corte real de conexão TCP na 2ª página (não simulação de dados) — run `PARTIAL`, 20 itens reais persistidos, cursor operacional `"20"` |
| F20-39: retomada `resume_of_run_id` + cursor explícito sobre a queda real acima | Feita e confirmada — 15 itens novos reais, `items_skipped=0`, `resumed_from_run_id` gravado, `checkpoint` avança 20→35, sem duplicata |
| F20-36: endpoint real do board (Airbyte, Anthropic, Apollo GraphQL) | Anthropic e Apollo GraphQL confirmados via probe real; Airbyte **não resolve mais** (`board_token=airbyte` → 404 "Job board not found", real, também fora da pilha via `boards-api.greenhouse.io`) |

## 1. Fonte real registrada

Fonte Workday real na pilha `f20resume` (mesmo tenant já homologado em 2026-09-27,
`docs/44-roadmap-fase-20/evidencias/http-condicional-2026-09-27.md`):

| Campo | Valor |
| --- | --- |
| `source_type` | `workday` |
| `tenant_identifier` | `adobe/external_experienced` |
| `api_region` | `wd5` |
| `source_id` (1ª instância, usada no teste de `kill -9`) | `d51910b7-b8db-4fb5-86d4-ef8ccdf1dca5` |
| `source_id` (2ª instância, "resume demo", usada no corte real de conexão) | `42bf4b99-2c67-4982-a8f7-521a7932b8e8` |

Uma segunda `SourceDefinition` para o mesmo tenant real foi registrada porque o dedupe é
escopado por `source_definition_id`: reaproveitar a 1ª instância (que já havia coletado
566 vagas reais da Adobe num teste anterior desta sessão) faria a 1ª página do teste de
corte de conexão colidir com o dedupe existente (`items_persisted=0` na página 1),
impedindo o run de nomear um prefixo `PARTIAL` com evidência para retomar. As duas
instâncias apontam para o mesmo endpoint público real; nenhum dado foi fabricado — apenas
o registro local foi duplicado para isolar o experimento.

## 2. `kill -9` real do processo — zero estado persistido

`scripts` auxiliares desta sessão (fora do repositório, não commitados) chamaram
`AcquisitionService.execute` diretamente contra a fonte real `d51910b7-...`, pedindo
`max_items=100000` (a Adobe tem ~566 vagas reais no tenant `external_experienced`, então
o run precisaria de ~28 páginas reais para terminar). O processo rodou dentro de um
container Docker (`docker compose ... run --rm --name f20resume-killtest`), e foi morto
de verdade:

```
docker kill -s SIGKILL f20resume-killtest
# container log: só "STARTING" foi impresso; nunca "FINISHED"
# exit code do container: 137 (SIGKILL)
```

Consulta real ao Postgres da pilha isolada, imediatamente depois:

```sql
select id, status, items_persisted, correlation_id from acquisition.source_run
 order by started_at desc;
-- só os dois runs SUCCEEDED anteriores ao kill test aparecem; nenhuma terceira linha.

select count(*) from acquisition.raw_item;  -- 566, inalterado
```

Nenhuma linha de `SourceRun` foi criada para a tentativa morta — nem sequer com status
`RUNNING` — e nenhum `RawItem` da página que provavelmente já tinha sido buscada da rede
real (a Adobe respondeu rápido o bastante para o run natural completar em segundos antes
desta tentativa) sobrou no banco. Isto confirma, com um `kill -9` real (não uma exceção
Python levantada à mão), a garantia de atomicidade que
`test_crash_before_commit_leaves_no_partial_state_and_retry_succeeds` já prova com um
coletor fake: `AcquisitionService.execute` grava tudo (evidência bruta, observação de
presença e o próprio `SourceRun`) numa única transação, commitada uma vez ao final
(`service.py:1162`). Um `kill -9` antes desse commit não deixa **nenhum** rastro — nem
`PARTIAL`, nem `RUNNING` órfão.

**Consequência prática para F20-39:** `resume_of_run_id` nunca pode nomear um run morto
por `kill -9` puro, porque esse run nunca chega a existir no banco. Um `PARTIAL`/`FAILED`
retomável só existe quando o processo continua vivo o bastante para alcançar o commit
final — ou seja, quando a falha é um erro real capturado dentro do próprio `execute()`
(uma falha de rede genuína no meio da paginação), não uma morte abrupta do processo que a
está executando. Isto não é um bug: é exatamente a proteção que o critério de aceite 3 do
card pede ("quedas antes do commit não deixam estado parcial"). A seção 3 abaixo produz o
cenário real que a retomada de fato precisa.

## 3. Corte real de conexão na 2ª página — `PARTIAL` real com evidência

Para produzir, com dado real (sem fabricar payload), o `PARTIAL` retomável que o critério
de aceite pede, esta sessão cortou a conexão de verdade na 2ª chamada HTTP de um mesmo
`execute()` — o "cortar a conexão no meio de uma página" que
`evidencias/http-condicional-2026-09-27.md` §3 registrou como pendente por falta de tempo.

Mecanismo: um `httpx.AsyncHTTPTransport` real encaminha a 1ª chamada normalmente (rede
real, para a Adobe) e, a partir da 2ª chamada, reescreve o destino da requisição para
`127.0.0.1:9` (porta fechada dentro do próprio container) antes de delegar ao transporte
real — o TCP `connect()` é genuinamente recusado pelo SO (`ECONNREFUSED`), não uma exceção
Python levantada à mão. A 1ª página (20 vagas reais da Adobe, `source_id`
`42bf4b99-...`) chega e é persistida normalmente antes do corte.

```
POST/GET reais contra adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/jobs
  offset=0  limit=20  -> 200 real, 20 vagas reais
  offset=20 limit=5   -> conexão recusada de verdade (127.0.0.1:9), 2 tentativas (max_retries=1)

run d539bab1-84a8-478f-b900-3ce4133467f3
  status=PARTIAL items_seen=20 items_persisted=20 items_skipped=0
  error_code=UNKNOWN_EXTERNAL_ERROR error_summary="could not connect to Workday"
```

`resumable_run` aceita este run (`PARTIAL`, `items_persisted=20 > 0`). Como o card
documenta, `checkpoint_after` só é promovido para `SUCCEEDED` (`service.py:1126`) — um
`PARTIAL` não grava `SourceCheckpointModel`. O cursor de retomada usado é o mesmo que
`CollectedItem.cursor` do Workday já calcula por item (`offset + index + 1`,
`workday.py:161`): a última das 20 vagas da página 1 tem cursor `"20"`, o mesmo raciocínio
operacional que `evidencias/http-condicional-2026-09-27.md` §3 usou (lá, com um cursor
explícito passado à mão; aqui, com um `PARTIAL` real nomeado por `resume_of_run_id`).

## 4. Retomada real via `resume_of_run_id` + cursor persistido

```python
CollectionRequest(
    source_definition_id=UUID("42bf4b99-2c67-4982-a8f7-521a7932b8e8"),
    max_items=15,
    cursor="20",
    resume_of_run_id=UUID("d539bab1-84a8-478f-b900-3ce4133467f3"),
)
```

Cliente HTTP normal (sem corte) — rede real, sem retry algum necessário:

```
run 48037fbf-7245-4084-bf1d-e23d9e1e19ce
  status=SUCCEEDED items_seen=15 items_persisted=15 items_skipped=0
  resumed_from_run_id=d539bab1-84a8-478f-b900-3ce4133467f3
  checkpoint_before="20" checkpoint_after="35"
```

Consulta real ao Postgres confirma os três critérios pedidos:

```sql
-- vínculo do run
select id, status, items_persisted, resumed_from_run_id, checkpoint_before, checkpoint_after
from acquisition.source_run where source_definition_id = '42bf4b99-...' order by started_at;
--  d539bab1... | PARTIAL   | 20 |                     |      |
--  48037fbf... | SUCCEEDED | 15 | d539bab1-...        |  20  | 35

-- nenhuma duplicata de evidência bruta
select count(*) as total_raw, count(distinct external_id) as distinct_external_id
from acquisition.raw_item where source_definition_id = '42bf4b99-...';
--  35 | 35
```

- **Vínculo do run:** `resumed_from_run_id` do 2º run aponta para o `PARTIAL` real.
- **Sem duplicata:** 35 `RawItem` reais, 35 `external_id` distintos — os 20 da página 1
  (antes do corte) e os 15 da retomada (offset 20-34) não colidem; `items_skipped=0` na
  retomada confirma que nada foi redescoberto/reenviado.
- **Continuação do cursor:** a retomada começou exatamente do offset 20 (onde o corte
  aconteceu) e avançou o checkpoint operacional para 35 — sem pular nem repetir vagas.
- **Oportunidades:** nenhum worker de normalização rodou nesta pilha isolada (fora de
  escopo desta validação, que é sobre aquisição/dedupe); não há `Opportunity` nenhuma
  criada e, portanto, nenhuma duplicata possível nessa camada para este experimento.

## 5. Interrupção do Docker Desktop durante a sessão

O Docker Desktop do host caiu e reiniciou sozinho no meio desta sessão (fora do controle
desta tarefa). Ao voltar, os containers da pilha real `opportunity-radar` que têm
`restart: unless-stopped`/política equivalente subiram sozinhos de volta (confirmado por
`docker ps` mostrando `Up 2-11 segundos` logo após o Docker Desktop religar) — esta sessão
não executou `up`, `down`, `restart`, `stop` nem `exec` de escrita contra o projeto
`opportunity-radar` em nenhum momento; o comportamento observado é inteiramente do
Docker Desktop/`restart policy`, não desta tarefa. O volume nomeado da pilha isolada
`f20resume_postgres_data` sobreviveu ao ciclo de queda/religamento do Docker Desktop
(dado real: os 566 `RawItem` da 1ª fonte seguiam lá depois do religamento), então o teste
de `kill -9` da seção 2 foi refeito depois do religamento sem perder o estado anterior.

## 6. Endpoints reais dos 3 boards (F20-36)

Verificação real, respeitando 1 req/s entre chamadas, via o mesmo caminho de probe do
projeto (`acquisition/probing.py::run_probe`, o que o script de habilitação e a
homologação humana usam) — não `curl` avulso. `max_items=3` por probe.

| Empresa | ATS | Endpoint corrigido testado | Resultado do probe | Recomendação |
| --- | --- | --- | --- | --- |
| Airbyte | greenhouse | `board_token="airbyte"` (`boards-api.greenhouse.io/v1/boards/airbyte/jobs`) | **Falhou de verdade**: `SOURCE_NOT_FOUND`, `"Job board not found"` — confirmado independentemente por `curl` direto (`boards-api.greenhouse.io/v1/boards/airbyte` → 404) e por `job-boards.greenhouse.io/airbyte` → 404, embora buscas na web mostrem URLs antigas de vaga (`job-boards.greenhouse.io/airbyte/jobs/47701...`) que hoje redirecionam para `/airbyte?error=true`. O board Greenhouse da Airbyte parece ter sido desativado, renomeado para um token não descoberto, ou a empresa migrou de ATS entre 2026-09-27 (descoberta) e 2026-09-28 (esta homologação). | **Não homologar agora.** Manter a proposta como pendente/inerte; não há endpoint de board confirmado para aceitar. Revisitar na próxima janela de descoberta (`careers_page` ainda é válida: `https://airbyte.com/careers`, mas o link real hoje é `https://airbyte.com/company/careers`, uma mudança de URL adicional a registrar). |
| Anthropic | greenhouse | `board_token="anthropic"` (`boards-api.greenhouse.io/v1/boards/anthropic/jobs`) | **OK real** — probe retornou `ok=true`, 3 vagas reais lidas, 1 requisição HTTP. | **Aceitar.** Corrigir `CompanySource.endpoint` de `https://www.anthropic.com/careers/jobs` (página onde o ATS foi achado) para `https://job-boards.greenhouse.io/anthropic` (board real), mantendo `board_token=anthropic` na configuração do coletor (já correto, só o `endpoint` de evidência exibido precisa mudar). |
| Apollo GraphQL | ashby | `board_identifier="apollo-graphql"` (`api.ashbyhq.com/posting-api/job-board/apollo-graphql`) | **OK real** — probe retornou `ok=true`, 3 vagas reais lidas, 1 requisição HTTP; uma das vagas reais (`id=9192511f-...`, "Staff Software Engineer, Rust") é a mesma vaga citada como evidência em `sites-jobposting-2026-09-27.md` linha 74, confirmando que é o mesmo board. | **Aceitar.** Corrigir `CompanySource.endpoint` de `https://www.apollographql.com/careers/9192511f-...` (página fetchada) para `https://jobs.ashbyhq.com/apollo-graphql` (board real), mantendo `board_identifier=apollo-graphql`. |

Nenhuma chamada excedeu 1 req/s (pausa de 1s entre as três chamadas, todas
sequenciais, sem paralelismo); nenhum robots.txt foi violado — os endpoints usados são
as APIs públicas documentadas dos próprios ATS (`PUBLIC_ENDPOINT_REFERENCES` em
`acquisition/probing.py`), não as páginas de carreira das empresas.

### Investigação adicional do token Airbyte

Tentativas reais de outros tokens plausíveis (todas 404 reais em `boards-api.greenhouse.io`,
1 req/s): `airbytehq`, `airbyte-hq`, `airbyteio`, `airbyte-io`, `air-byte`, `airbyte_com`,
`airbyteinc`, `goairbyte`, `airbyte-com`, `getairbyte`. Uma busca real na web confirma que
URLs de vaga individuais sob `job-boards.greenhouse.io/airbyte/jobs/<id>` existiam
recentemente, mas cada uma delas hoje redireciona (302 real) para
`job-boards.greenhouse.io/airbyte?error=true`, e o board raiz
(`job-boards.greenhouse.io/airbyte`, `boards.greenhouse.io/airbyte`) devolve 404 real —
o token continua sendo `airbyte`, mas o board em si parece ter sido esvaziado/desativado
do lado da Greenhouse, não um erro de token. Não fabricado nem adivinhado além disso; a
homologação humana deve reconfirmar antes de aceitar Airbyte.

## 7. O que fica pendente

- Airbyte (F20-36): endpoint real não confirmável nesta sessão; ver seção 6.
- Orçamento por host compartilhado entre fontes reais (F20-38, ainda não exercido: nenhum
  par de fontes reais do catálogo importado compartilha host) — fora do escopo desta
  tarefa.
- Os outros 3 coletores novos (teamtailor/workable/factorial) continuam sem paginação
  real, então o mesmo experimento de corte de conexão/retomada não se aplica a eles (sem
  "meio de página" a cortar) — já registrado como fora de escopo em
  `docs/44-roadmap-fase-20/fase-20/f20-39-delta-presenca-e-retomada.md`.
