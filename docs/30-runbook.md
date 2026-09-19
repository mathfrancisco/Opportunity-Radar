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

1. Habilitar uma fonte em `/sources` (só depois de revisar termos e homologar o
   collector — o gate é da Fase 2 e continua valendo).
2. Executar a fonte pela própria tela, ou por `POST /api/sources/{id}/runs`.
3. O worker normaliza os itens pendentes a cada 60 segundos; para forçar,
   `POST /api/opportunities/normalizations/pending`.
4. Avaliar em `/inbox` ou por `POST /api/matches/evaluate`.
5. Analisar com Ollama pelo detalhe da oportunidade.
6. Registrar a candidatura e acompanhá-la em `/applications`.

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

## 6. Quando algo quebra

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

## 7. Reiniciar preservando dados

```bash
make restart
```

O volume do PostgreSQL sobrevive. Para apagar tudo de propósito:

```bash
docker compose down --volumes
```

---

## 8. Validação

Por decisão de projeto, validação roda no CI e não localmente por padrão. Quando for
necessário rodar à mão:

```bash
make test               # testes unitários
make test-integration   # testes que exigem PostgreSQL
make check              # lint e tipos, backend e frontend
```
