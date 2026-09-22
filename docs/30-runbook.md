# Runbook operacional

Este documento é para operar o Opportunity Radar localmente, não para explicá-lo. A
arquitetura está nos docs 02 e 03; as decisões de domínio nos docs 08, 09, 11, 20 e 21.

Todo comando abaixo pressupõe o repositório clonado e Docker disponível.

---

## 1. Subir do zero

```bash
make bootstrap    # cria .env a partir de .env.example e valida o compose
make up           # sobe postgres, ollama, migrate, api, worker e frontend
make doctor       # diz o que está quebrado, e o que fazer a respeito
```

Depois disso:

| Endereço | O quê |
|---|---|
| `http://localhost:3000` | dashboard |
| `http://localhost:8000/health` | estado das dependências |
| `http://localhost:8000/docs` | contrato da API |

`make doctor` sai com código 1 quando algo está quebrado, e 0 quando o ambiente está
utilizável. Aviso não derruba o código de saída: Ollama fora do ar é degradação
esperada, não falha de ambiente.

---

## 2. Popular o catálogo

```bash
make import-companies                     # importa os dois arquivos da pesquisa
make import-companies DRY_RUN=1           # só relata, não grava
make import-companies REPORT=out/rel.md   # grava o relatório
```

A importação é idempotente: reexecutar não duplica empresa.

---

## 3. Rodar o ciclo

1. Importe as definições pesquisadas com `make import-companies`.
2. Revise os termos das fontes públicas e execute
   `make enable-sources TERMS_REVIEWED=1`. O comando faz um probe de um item por
   fonte e habilita somente os coletores cujo endpoint e schema respondem
   corretamente. Use `DRY_RUN=1` para listar os candidatos sem alterar o banco.
3. Execute `make collect` para coletar todas as fontes habilitadas. O comando
   continua nas fontes seguintes quando uma falha e imprime um resumo JSON. Use
   `SOURCE_TYPE=ashby,lever` ou `MAX_ITEMS=100` para limitar a execução.
4. Execute a fonte pela própria tela, ou por `POST /api/sources/{id}/runs`, quando
   precisar de uma coleta individual.
5. O worker normaliza os itens pendentes a cada 60 segundos; para forçar,
   `POST /api/opportunities/normalizations/pending`.
6. Avalie em `/inbox` ou por `POST /api/matches/evaluate`.
7. Analise com Ollama pelo detalhe da oportunidade.
8. Registre a candidatura e acompanhe-a em `/applications`.

---

## 4. Logs

Todo processo emite JSON em stdout, um objeto por linha.

```bash
make logs                                    # tudo
docker compose logs api | jq 'select(.level=="ERROR")'
docker compose logs api | jq 'select(.correlation_id=="<id>")'
```

Toda requisição HTTP responde com `X-Correlation-ID`. Enviar esse cabeçalho na
requisição propaga o id escolhido; não enviar faz a API gerar um. Cada passada de
normalização do worker abre o próprio id, então um lote inteiro é rastreável.

Campos presentes em toda linha: `timestamp`, `level`, `logger`, `message`. Requisições
trazem `method`, `path`, `status_code` e `duration_ms`. Falhas trazem `error` com o
traceback.

---

## 5. Backup e restauração

Criar dump não satisfaz o critério da Fase 9 — a restauração precisa ser verificada.

```bash
make backup                          # data/backups/<stamp>.dump + .manifest.json
make backup LABEL=antes-da-migracao  # nome fixo em vez de timestamp
make restore-check                   # restaura o dump mais recente num banco descartável
make restore-check DUMP=data/backups/antes-da-migracao.dump
```

O manifesto guarda a revisão do Alembic e a contagem de cada tabela do fluxo vertical.
`restore-check` cria um banco novo, restaura nele, roda as mesmas contagens e compara
com o manifesto. Divergência sai com código 1 listando qual tabela divergiu. O banco de
trabalho não é tocado em nenhum momento, e o descartável é removido ao final — use
`--keep` se quiser inspecioná-lo.

`BACKUP_RETENTION_DAYS` no `.env` controla a poda de dumps antigos.

---

## 6. Operação contínua

### Jobs do worker

Cinco jobs funcionais rodam pelo relógio. Cada um grava o que fez em
`platform.worker_job_state`: última tentativa, último sucesso, última falha, duração,
próxima execução prevista e o `correlation_id` da passada.

| Job | Intervalo | Kill switch |
|---|---|---|
| `collect_enabled_sources` | 60 s | `WORKER_COLLECT_ENABLED` |
| `normalize_opportunities` | 60 s | `WORKER_NORMALIZE_ENABLED` |
| `evaluate_pending` | 60 s | `WORKER_MATCH_ENABLED` |
| `analyze_pending` | 120 s | `WORKER_ANALYZE_ENABLED` |
| `expire_raw_payloads` | `PAYLOAD_RETENTION_INTERVAL_SECONDS` (6 h) | `WORKER_RETENTION_ENABLED` |

Desligar um job é editar o `.env` e `make restart`. O log `worker jobs configured` na
subida diz quais jobs o scheduler realmente registrou — ele é lido do scheduler, não das
variáveis, então um job desligado nunca aparece como ativo.

Para forçar uma passada sem esperar o relógio:

```bash
curl -X POST http://localhost:3000/api/sources/<id>/runs                  # coleta
curl -X POST http://localhost:3000/api/opportunities/normalizations/pending
curl -X POST http://localhost:3000/api/matches/evaluate -d '{"opportunity_id":"<id>"}'
docker compose exec -T api python -c "from opportunity_radar.platform.config import get_settings; from opportunity_radar.platform.database import create_database_engine; from opportunity_radar.worker import expire_raw_payloads; s=get_settings(); expire_raw_payloads(create_database_engine(s.database_url), retention_days=s.payload_retention_days)"
```

`make doctor` classifica cada job habilitado como saudável, atrasado, falho ou ausente,
a partir do estado persistido — um scheduler no ar não prova que um job executou.
`DOCTOR_JOB_GRACE_SECONDS` define quanto atraso é tolerado antes de um job ser reportado
como atrasado.

### Alertas e recuperação de fonte

Três falhas consecutivas de uma fonte abrem um incidente e enviam um webhook. Enquanto o
incidente estiver aberto, novas falhas da mesma fonte não reenviam nada. O primeiro
sucesso posterior fecha o incidente e envia o recovery.

```bash
SOURCE_ALERT_WEBHOOK_URL=https://exemplo/hook   # vazio desliga o envio, não o registro
SOURCE_ALERT_FAILURE_THRESHOLD=3
SOURCE_ALERT_TIMEOUT_SECONDS=5
```

Sem webhook configurado — ou com o canal fora do ar — o incidente continua sendo gravado
em `acquisition.source_alert_incident`, o caso aparece em log estruturado e `make doctor`
o reporta no check `source incidents`. Falha do canal nunca altera o resultado da coleta.

### Métricas por fonte

`GET /api/source-metrics` responde as janelas de 24 horas e sete dias com cobertura,
volume, taxa de erro por código, taxa de dedupe, latência p95 e distribuição de
senioridade com `UNKNOWN` e a versão do mapeamento. A Overview mostra as duas janelas.

Uma taxa vem como `null` quando a janela não tem execução: fonte não medida e fonte
perfeita não podem ser lidas do mesmo jeito. A cobertura separa `NOT_ENABLED`,
`CONFIGURATION_BLOCKED`, `NOT_SCHEDULED`, `NOT_RUN`, `SUCCEEDED_ZERO`, `SUCCEEDED`,
`PARTIAL` e `FAILED` — sucesso sem vagas não é falha, e falta de execução não é ausência
de vagas.

### Retenção do conteúdo bruto

`RawItem` guarda o envelope imutável — fonte, run, identidade, hash e ocorrência — e
`acquisition.raw_item_payload` guarda o conteúdo. Só o conteúdo expira, após
`PAYLOAD_RETENTION_DAYS` (padrão 365) e somente para item com normalização terminal.
Cada expiração grava uma linha append-only em `acquisition.payload_retention_event` com
`raw_item_id`, data, versão da política e hash. Reexecutar a retenção não duplica
histórico.

A API e a tela da oportunidade marcam a ocorrência cujo conteúdo expirou: a procedência
continua, o reprocessamento não.

### Gate de 72 horas

```bash
make soak                 # 72 horas simuladas contra relógio controlado
make soak HOURS=6         # janela curta, para checar o ambiente
make soak JSON=1          # saída machine-readable
```

O gate roteiriza uma queda de fonte de três passadas e a recuperação seguinte, e falha
com código 1 se algum job ficar silenciosamente falho, se o alerta duplicar, se o
recovery não sair ou se a retenção perder envelope ou hash. Ele roda no CI a cada
alteração de código.

---

## 7. Quando algo quebra

### API não sobe

```bash
make doctor
docker compose logs api --tail=100
```

Causa mais comum: migração fora do head. `make migrate` resolve.

### `/health` responde `degraded` em `ollama`

Esperado quando o Ollama não está no ar ou o modelo não foi baixado. O fluxo
determinístico continua inteiro; só a camada semântica degrada. Para baixar o modelo:

```bash
docker compose exec ollama ollama pull llama3.2:3b
```

Para desligar a camada semântica de vez, `OLLAMA_ANALYSIS_ENABLED=false`.

### Uma fonte falha

`/sources` mostra o último run com status, duração, contadores e erro. O histórico por
fonte fica na mesma tela. Falha de uma fonte não derruba as outras nem o sistema: o run
é registrado como `FAILED` com código de erro estável.

### Oportunidade não aparece depois da coleta

O item bruto é preservado antes da normalização. Verifique em `/api/overview` o campo
`pending_normalizations`; se estiver acima de zero, force a passada:

```bash
curl -X POST http://localhost:3000/api/opportunities/normalizations/pending
```

Se continuar pendente, o resultado da normalização explica o motivo em
`/api/opportunities/{id}` (bloco `normalization_results`).

### Perfil recusa a edição com 409

Alguém — ou outra aba — alterou o perfil no meio do caminho. Recarregue a tela: o lock
da versão ativa mudou, e o conflito existe para não sobrescrever a alteração alheia.

---

## 8. Reiniciar preservando dados

```bash
make restart
```

O volume do PostgreSQL sobrevive. Para apagar tudo de propósito:

```bash
docker compose down --volumes
```

---

## 9. Validação

Por decisão de projeto, validação roda no CI e não localmente por padrão. Quando for
necessário rodar à mão:

```bash
make test               # testes unitários
make test-integration   # testes que exigem PostgreSQL
make check              # lint e tipos, backend e frontend
make soak               # gate de 72 horas contra relógio controlado
```
