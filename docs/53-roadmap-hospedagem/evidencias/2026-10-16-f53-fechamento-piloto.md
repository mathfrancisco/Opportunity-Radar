# F53 — fechamento do piloto em 16/10 (chaves, F53-11, restore, rollback, consumo, E2E)

Ambiente: Worker `https://opportunity-radar.math-francisco2.workers.dev`, API
`https://radar-api.163-176-11-135.sslip.io` (VM OCI E5 Free Trial, sa-saopaulo-1),
Neon `summer-mud-80771409` (branch `production`), Clerk de desenvolvimento.
Imagens em execução: os digests de `0a64b5d` (api `9b2f970a…`, worker
`9f9e1758…`, proxy `a4160ecb…`). Horários em UTC. Nenhum valor de segredo, DSN,
subject Clerk ou chave aparece neste arquivo.

## 1. Chaves de API e IA

O gerador local de envs (ignorado, fora do git) passou a propagar
`GROQ_API_KEY` e `TAVILY_API_KEY` presentes na `.env` da raiz para `api.env` e
`worker.env`, e define `AI_ENABLED=true` quando a chave Groq existe. A API usa as
duas (saúde da IA, IA interativa, execução manual de fonte); o worker usa as duas
(análise e aquisição Tavily). `migrate.env` não recebe chaves e não foi
reenviado.

Saída literal do gerador: `propagated_keys=GROQ_API_KEY,TAVILY_API_KEY ai_enabled=true`.
Transferência: `transfer_status=completed files=6 permissions=root:root_0600`
(cinco envs de runtime; a contagem fixa do script não foi atualizada).

Depois do `remote-deploy.sh`: `api running healthy`; dentro do container,
`ai True groq True tavily True` (booleanos de presença); `/health/live` externo
`200`. Varredura de segredos no `journalctl` do dia e no `docker logs` da API:
`gsk_`, `tvly-`, `postgresql`, `sk_test`, `sk_live` com 0 ocorrências cada.

A Visão geral passou de "Desligada (AI_ENABLED=false)" para "Nenhuma chamada nas
últimas 24 h", o texto do estado `enabled`. Observação: enquanto
`/analysis-metrics` carrega (5,2 s com Neon frio), o cartão mostra "Desligada"
por um instante; é um defeito menor de UI, não de configuração.

Limites de IA configurados (defaults de `Settings`, sem override no piloto):
850 requisições/dia e 170 000 tokens/dia (soft), 25 requisições/min e 7 000
tokens/min, reserva interativa de 100 requisições, análise em lote limitada a
80% do teto diário, lote de 10, breaker após 5 falhas com 120 s de pausa,
retenção de `ai_call_record` de 30 dias. Os tetos ficam abaixo do plano
gratuito da Groq para os modelos configurados.

## 2. F53-11 (jobs e timers) na VM

| AC | Prova |
| --- | --- |
| AC01 janela completa | 13:07:28 `pipeline_window_start` com `run_id` e `deadline_utc`; 13:07:46 resumo `outcome=success exit_code=0` com as três etapas `completed`; unit `Deactivated successfully`. |
| AC02 reboot sem catch-up | Timer antes: próximo `Sat 2026-10-17 06:00:54 UTC`. Reboot 13:15:53. Depois: `journalctl -b -u opportunity-radar-pipeline.service` = `-- No entries --`; próximo `Sat 2026-10-17 06:03:26 UTC`; API `healthy`; `/health/live` 200. `Persistent=false` confirmado na unit. |
| AC03 timeout | `systemd-run` com `PIPELINE_WINDOW_SECONDS=3`: `outcome=deadline_reached`, `exit_code=10`, coleta `stopped` com `reason=deadline`, etapas seguintes `skipped`; unit `Failed with result 'exit-code'`. |
| AC04 Neon ocioso | Com API no ar e dois redeploys depois, o compute `ep-curly-resonance-b55hmfyd` ficou `idle`, `suspended_at=2026-10-16T13:20:47Z`, `last_active=13:13:27Z`. O healthcheck de container usa `/health/live`, que não abre conexão ao banco. |
| AC05 alerta de janela perdida | **sem prova.** Não existe mecanismo de alerta para janela perdida (nenhum `OnFailure=` nem alarme). O e-mail do tópico OCI foi removido a pedido do dono. |

Endurecimento opcional aplicado: `NoNewPrivileges=yes` na unit do pipeline
(repositório e VM). `systemd-analyze verify` sem erro para a unit; `systemctl show`
retorna `NoNewPrivileges=yes`; `tests/backend/test_systemd_units.py` em Linux:
`8 passed, 1 skipped`.

`CLERK_AUDIENCE` continua vazio: o token de sessão do Clerk de desenvolvimento
não traz `aud` sem um template de JWT; definir a variável hoje recusaria todos
os tokens.

## 3. Restore a partir da cópia do bucket (F53-14)

Mudança de IAM aprovada pelo dono: a policy `opportunity-radar-backup-upload`
ganhou uma segunda instrução, só leitura de objeto e só no bucket de backup:

```text
Allow dynamic-group 'Default'/'opportunity-radar-api-instance' to read objects in compartment opportunity-radar-pilot where all {target.bucket.name = 'opportunity-radar-backups-mathfrancisco-20261015', request.permission = 'OBJECT_READ'}
```

Download na VM com `ghcr.io/oracle/oci-cli` e `--auth instance_principal` de
`f53-14/pilot-20261016T022522Z.orbk` (174114 bytes) e do `.sha256`; hash do
ciphertext igual ao sidecar (prefixo `559273d97422fd7e`). O ciphertext foi copiado
para a máquina do dono e apagado da VM. A chave nunca saiu da máquina do dono.

Decifrado em diretório temporário do runner `opportunity-radar-backup-pg18:local`
e restaurado em PostgreSQL 18 + pgvector isolado (banco `restore_test`,
`RUN_DATABASE_INTEGRATION=1`, `DATABASE_INTEGRATION_ISOLATED=1`):
`restore check passed`, extensões `plpgsql, unaccent, vector`.

## 4. Ensaio de rollback

`images.env` trocado para os digests publicados por `main` `d37355f` (run
38903494499: api `6fa42655…`, worker `2fca7ba5…`, proxy `205bdea5…`) e
`remote-deploy.sh` às 13:25:14: `api running healthy`, `/health/live` 200. Volta
aos digests de `0a64b5d` às 13:25:52, concluída às 13:26:05 (13 s):
`api running healthy`, imagens confirmadas por `docker inspect`, `/health/live` 200.
Não há migração entre as duas versões. O arquivo de backup temporário de
`images.env` foi removido.

## 5. Consumo e limites gratuitos

- Neon (período desde 08/10): `compute_time_seconds=516`, `active_time_seconds=1944`,
  `logical_size=34709504` bytes, plano `free_v3`, autoscaling 0,25–2 CU.
- Projeção (`scripts/project_neon_budget.py --active-hours-per-run 1.0833
  --runs-per-month 31 --cu 0.25 --additional-cu-hours 10
  --current-storage-bytes 34709504 --monthly-growth-bytes 50000000`):
  `total_cu_hours=18.395575` de 80, `storage_projected_bytes=84709504` de
  1000000000, `has_budget_breach=false`, exit 0.
- VM: 762 MiB usados de 7931 MiB; disco 5,2 GiB de 48 GiB; API 80 MiB, proxy
  3 MiB. A VM é `VM.Standard.E5.Flex` (Free Trial), **não** Always Free: ao fim
  do trial, a migração para A1 continua pendente.
- Cloudflare: **sem prova** de consumo medido; o Worker só serve assets estáticos.

## 6. Drift de rede

A variável `admin_cidr` da stack `opportunity-radar-pilot` no Resource Manager foi
atualizada para o `/32` atual do dono (o mesmo já aplicado no NSG). Job de plan
`plan-job-20261016102933`: `Succeeded`, `No changes. Your infrastructure matches
the configuration.` Nenhum apply foi necessário.

## 7. Notificações da Oracle

| Origem | Estado encontrado | Ação |
| --- | --- | --- |
| Notifications (root) | nenhum tópico | — |
| Notifications (opportunity-radar-pilot) | tópico `opportunity-radar-pilot-alerts` com assinatura e-mail ativa para o Gmail do dono | assinatura excluída (aprovado pelo dono); tópico mantido sem assinaturas |
| Monitoring alarms | `opportunity-radar-pilot-memory`, "TESTE CONTROLADO temporario", limite 5,9% de memória, estado `Firing` | alarme desabilitado (estado `Disabled`, 13:09) |
| Budgets | nenhum | — |
| Events rules (root e pilot) | nenhuma | — |
| Identity Domain Default > Notifications | notificações opcionais ligadas | **não alterado** nesta sessão; fica para o dono |
| Announcements | opt-out feito pelo dono em 16/10 | **sem prova** nesta sessão (a página de preferências não carregou) |

A Oracle não permite desligar e-mails de cobrança, de segurança obrigatória da
conta (redefinição de senha, bloqueio, MFA) nem os avisos de fim do Free Trial.
O e-mail da conta e o contato de cobrança não foram alterados.

## 8. E2E no navegador como owner

Imagens após as correções de coleta (run 38920561681, `1663d40`): api
`2bd72817…`, worker `e10f9cb5…`, proxy `35198bda…`; banco no Neon de São Paulo.

| Passo | Resultado |
| --- | --- |
| 1. Login e menu admin | Sessão Clerk ativa; menu mostra Fontes, Homologação, Empresas e Status. |
| 2. Perfil | Versão 1 criada com dados genéricos aprovados pelo dono (skills python/fastapi/postgresql, Engenharia de software, Júnior e Pleno, REMOTE, FULL_TIME, BR): "Versão 1 ativa". |
| 3. Fonte | Greenhouse board `gitlab` criada desabilitada, collector testado ("Confirmado (1 item)"), termos revisados em 16/10/2026, habilitada ("1 habilitada nesta sessão"). |
| 4. Coleta e janela | Primeira coleta (Neon em us-east-2, código antigo): morreu aos 183 s com `FENCE_REJECTED`. Depois das correções e da mudança de região: `source_run` `SUCCEEDED`, `items_seen=225`, `items_persisted=159`, `items_skipped=66`, `items_invalid=0`, 0,9 s. Janela `systemctl start`: `success`, normalize 94 de 100 (6 ignoradas), evaluate 42 de 42. A coleta da janela pulou a fonte porque o agendamento é manual. |
| 5. Inbox e IA | "23 oportunidades encontradas". Ao abrir "Backend Engineer, Create: Repository Management" e clicar em "Analisar com IA", a análise semântica apareceu. `platform.ai_call_record`: `job_match`, `openai/gpt-oss-120b`, `success=true`, HTTP 200, 1724 ms, 1099+469 tokens. `ai_quota_usage` do dia: 1 requisição, 999 restantes. |
| 6. Candidatura | "Registrar interesse" e depois "Encerrada"; após recarregar, Pipeline mostra "Encerradas (1)". |
| 7. Status | **sem prova** de métricas por fonte nesta tela: `/status` mostra só a prontidão, com o texto "Ambiente local" (defeito de cópia). A última execução da fonte aparece em `/sources` e em `source_run`. |
| 8. Console, CORS e logs | Preflight CORS atual: `HTTP/1.1 200 OK` com `access-control-allow-origin` do Worker. O console guardava erros de CORS de `/sources/{id}/runs`, `/source-health` e `/source-coverage`, de quando a requisição de 183 s falhou e dos reinícios de deploy; **sem prova** de console limpo isolado depois disso. Varredura de segredos em `journalctl` e `docker logs` (api e proxy): `gsk_`, `tvly-`, `postgresql`, `npg_`, `sk_test`, `sk_live` com 0 ocorrências; `user_` só em mensagens do kernel. |

Segundo usuário Clerk: **sem prova** (nenhum foi criado).

Defeitos encontrados, sem correção nesta entrega:
- A janela finita não tem etapa de análise por IA; a análise só ocorre sob demanda.
- A normalização processa 100 itens por janela.
- A descrição Greenhouse aparece com HTML escapado, e a IA não extraiu skills nem senioridade dela.
- "Intermediate" não é mapeado para senioridade.
- `COUNTRY_ALLOWED` fica `NOT_APPLICABLE` em vagas com país explícito diferente do perfil.
- `homologation_audit` aparece como `[object Object]`.
- O cartão de IA mostra "Desligada" enquanto as métricas carregam.

## 9. Neon movido para São Paulo

Motivo: a coleta manual da fonte GitLab levou cerca de 2,6 s por vaga. A latência
entre a VM (sa-saopaulo-1) e o Neon (`aws-us-east-2`) era de 160 ms por query. A
execução morreu aos 183 s com `FencedWriteRejected`, porque o lease de 3 min não
era renovado durante o loop síncrono. A correção de código está registrada à parte.

Decisão do dono: mover o banco. Novo projeto Neon `tiny-dust-53844381`
(`aws-sa-east-1`, PostgreSQL 18, 0,25–2 CU, plano gratuito). `pg_dump -Fc
--no-owner --no-acl` do projeto antigo gerou 409161 bytes, restaurado com
`pg_restore --exit-on-error` (`restore_ok`). Comparação antigo × novo: alembic
`20261008_0069` nos dois, extensões `plpgsql,unaccent,vector`, 52 tabelas, 228
linhas, hash md5 idêntico da contagem por tabela.

As envs foram regeneradas apontando para o novo endpoint (`verify-full`) e
transferidas. Depois do `remote-deploy.sh`: `api running healthy`, região
`sa-east-1`, RTT `6.2 ms` (antes `159.5 ms`), `/health/live` 200. Na UI, o perfil
e a fonte habilitada continuam visíveis. A escrita não foi congelada: o
classificador de permissões negou parar a API. Não havia coleta ativa nem timer
previsto até 17/10 06:00. O projeto antigo `summer-mud-80771409` foi mantido para
rollback e só será removido com confirmação do dono.
