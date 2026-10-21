# Variáveis e runbooks de hospedagem

Este inventário cobre variáveis lidas ou declaradas no código de hospedagem.
As referências usam `arquivo:linha` da árvore `origin/main`. Valores reais não
entram neste documento. Use `<DOMINIO>`, `<NEON_URL>`, `<CLERK_ISSUER>` e outros
placeholders equivalentes.

`Pública` significa que o valor pode aparecer em configuração de frontend,
DNS, imagem ou log redigido. `Secreta` significa que o valor exige cofre,
secret do GitHub, arquivo `0600` ou console privado. Variáveis com valor
booleano ou URL podem continuar secretas quando o sistema que as administra
exige controle de acesso.

## Backend API

| Nome | Origem (file:line) | Onde configurar | Pública ou secreta | Ambiente | Comando seguro de validação | Autorização externa necessária |
| --- | --- | --- | --- | --- | --- | --- |
| `DATABASE_URL` | `src/opportunity_radar/platform/config.py:14`; `compose.cloud.yaml:8` | Neon console; VM EnvironmentFile `/etc/opportunity-radar/api.env` `0600`; local `.env` only | secreta | produção, VM, local, CI | `test -n "${DATABASE_URL:+x}" && echo set` | Dono Neon aprova banco, usuário e acesso |
| `API_STATEMENT_TIMEOUT_MS` | `src/opportunity_radar/platform/config.py:17`; `compose.yaml:86` | VM EnvironmentFile `/etc/opportunity-radar/api.env` `0600`; local `.env` only | pública | produção, VM, local | `test "${API_STATEMENT_TIMEOUT_MS:-0}" -ge 0` | Dono da aplicação aprova limite |
| `LOG_LEVEL` | `src/opportunity_radar/platform/config.py:18`; `compose.cloud.yaml:7` | VM EnvironmentFile `/etc/opportunity-radar/api.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${LOG_LEVEL:+x}" && echo set` | Dono da aplicação aprova política de logs |
| `FRONTEND_ORIGIN` | `src/opportunity_radar/platform/config.py:19`; `compose.cloud.yaml:9` | VM EnvironmentFile `/etc/opportunity-radar/api.env` `0600`; Cloudflare Workers Builds variables | pública | produção, VM, preview, local | `printf '%s' "$FRONTEND_ORIGIN" | grep -Eq '^https://[^/]+$' && echo valid` | Dono do domínio aprova origem exata |
| `CLERK_ISSUER` | `src/opportunity_radar/platform/config.py:22`; `compose.cloud.yaml:10` | Clerk dashboard; VM EnvironmentFile `/etc/opportunity-radar/api.env` `0600` | pública | produção, VM, preview | `curl -fsS "${CLERK_ISSUER%/}/.well-known/openid-configuration" >/dev/null` | Administrador Clerk aprova instância |
| `CLERK_JWKS_URL` | `src/opportunity_radar/platform/config.py:23`; `compose.cloud.yaml:11` | Clerk dashboard; VM EnvironmentFile `/etc/opportunity-radar/api.env` `0600` | pública | produção, VM, preview | `curl -fsS "$CLERK_JWKS_URL" >/dev/null` | Administrador Clerk aprova endpoint JWKS |
| `CLERK_AUTHORIZED_PARTIES` | `src/opportunity_radar/platform/config.py:24`; `compose.cloud.yaml:12` | Clerk dashboard; VM EnvironmentFile `/etc/opportunity-radar/api.env` `0600` | pública | produção, VM, preview | `test -n "${CLERK_AUTHORIZED_PARTIES:+x}" && echo set` | Dono do domínio aprova origins permitidas |
| `CLERK_OWNER_SUB` | `src/opportunity_radar/platform/config.py:25`; `compose.cloud.yaml:14` | Clerk dashboard; VM EnvironmentFile `/etc/opportunity-radar/api.env` `0600` | secreta | produção, VM, preview | `test -n "${CLERK_OWNER_SUB:+x}" && echo set` | Administrador Clerk confirma usuário dono |
| `CLERK_AUDIENCE` | `src/opportunity_radar/platform/config.py:26`; `compose.cloud.yaml:13` | Clerk dashboard; VM EnvironmentFile `/etc/opportunity-radar/api.env` `0600` | pública | produção, VM, preview | `test -n "${CLERK_AUDIENCE:+x}" && echo set` | Administrador Clerk aprova audience |
| `WORKER_OWNER_SUB` | `src/opportunity_radar/platform/config.py:33`; `compose.cloud.yaml:50` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | secreta | produção, VM, CI | `test -n "${WORKER_OWNER_SUB:+x}" && echo set` | Dono da aplicação confirma subject operacional |
| `OWNER_SUB_BACKFILL` | `compose.cloud.yaml:24`; `compose.yaml:123` | VM EnvironmentFile temporário `/etc/opportunity-radar/migrate.env` `0600` | secreta | produção, VM, CI | `test -n "${OWNER_SUB_BACKFILL:+x}" && echo set` | Dono da aplicação autoriza backfill único |
| `TENANCY_OWNER_API_READY` | `scripts/check_tenancy_release_gate.py:20` | GitHub repository variable; VM EnvironmentFile `/etc/opportunity-radar/api.env` `0600` | pública | CI, produção, VM | `test -n "${TENANCY_OWNER_API_READY:+x}" && echo set` | **Somente o dono**, depois de evidência da API com escopo do dono |

## Worker

| Nome | Origem (file:line) | Onde configurar | Pública ou secreta | Ambiente | Comando seguro de validação | Autorização externa necessária |
| --- | --- | --- | --- | --- | --- | --- |
| `APP_ENV` | `compose.yaml:4`; `compose.cloud.yaml:6` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${APP_ENV:+x}" && echo set` | Dono da aplicação aprova ambiente |
| `COLLECTION_TIMEZONE` | `src/opportunity_radar/platform/config.py:27`; `compose.yaml:44` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${COLLECTION_TIMEZONE:+x}" && echo set` | Dono da operação aprova fuso |
| `WORKER_COLLECT_ENABLED` | `src/opportunity_radar/platform/config.py:28`; `compose.yaml:47` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${WORKER_COLLECT_ENABLED:+x}" && echo set` | Operador autoriza ativação |
| `WORKER_NORMALIZE_ENABLED` | `src/opportunity_radar/platform/config.py:29`; `compose.yaml:48` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${WORKER_NORMALIZE_ENABLED:+x}" && echo set` | Operador autoriza ativação |
| `WORKER_MATCH_ENABLED` | `src/opportunity_radar/platform/config.py:34`; `compose.yaml:49` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${WORKER_MATCH_ENABLED:+x}" && echo set` | Operador autoriza ativação |
| `WORKER_ANALYZE_ENABLED` | `src/opportunity_radar/platform/config.py:35`; `compose.yaml:50` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${WORKER_ANALYZE_ENABLED:+x}" && echo set` | Operador autoriza ativação e custo AI |
| `WORKER_RETENTION_ENABLED` | `src/opportunity_radar/platform/config.py:36`; `compose.yaml:51` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${WORKER_RETENTION_ENABLED:+x}" && echo set` | Dono autoriza exclusão por retenção |
| `WORKER_SUGGEST_ENABLED` | `src/opportunity_radar/platform/config.py:40`; `compose.yaml:53` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${WORKER_SUGGEST_ENABLED:+x}" && echo set` | Dono aprova após medição de precisão |
| `WORKER_SUGGEST_BATCH_SIZE` | `src/opportunity_radar/platform/config.py:41`; `compose.yaml:54` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${WORKER_SUGGEST_BATCH_SIZE:+x}" && echo set` | Dono da operação aprova capacidade |
| `WORKER_EVALUATE_BATCH_SIZE` | `src/opportunity_radar/platform/config.py:50`; `compose.yaml:62` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${WORKER_EVALUATE_BATCH_SIZE:+x}" && echo set` | Dono da operação aprova capacidade |
| `WORKER_ANALYZE_BATCH_SIZE` | `src/opportunity_radar/platform/config.py:54`; `compose.yaml:63` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${WORKER_ANALYZE_BATCH_SIZE:+x}" && echo set` | Dono da operação aprova custo |
| `WORKER_ANALYZE_VERDICTS` | `src/opportunity_radar/platform/config.py:57`; `compose.yaml:64` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${WORKER_ANALYZE_VERDICTS:+x}" && echo set` | Dono da operação aprova fila |
| `WORKER_ANALYZE_AGING_SAMPLE_RATIO` | `src/opportunity_radar/platform/config.py:62`; `compose.yaml:55` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${WORKER_ANALYZE_AGING_SAMPLE_RATIO:+x}" && echo set` | Dono da operação aprova amostra |
| `WORKER_ANALYZE_DAILY_CAP_FRACTION` | `src/opportunity_radar/platform/config.py:66`; `compose.yaml:56` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${WORKER_ANALYZE_DAILY_CAP_FRACTION:+x}" && echo set` | Dono da operação aprova orçamento |
| `ANALYSIS_RETRY_COOLDOWN_SECONDS` | `src/opportunity_radar/platform/config.py:67`; `compose.yaml:65` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${ANALYSIS_RETRY_COOLDOWN_SECONDS:+x}" && echo set` | Dono da operação aprova retry |
| `ANALYSIS_RETRY_ATTEMPT_WINDOW_SECONDS` | `src/opportunity_radar/platform/config.py:68`; `compose.yaml:66` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${ANALYSIS_RETRY_ATTEMPT_WINDOW_SECONDS:+x}" && echo set` | Dono da operação aprova retry |
| `ANALYSIS_RETRY_MAX_ATTEMPTS` | `src/opportunity_radar/platform/config.py:69`; `compose.yaml:67` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${ANALYSIS_RETRY_MAX_ATTEMPTS:+x}" && echo set` | Dono da operação aprova retry |
| `ANALYSIS_CLAIM_LEASE_SECONDS` | `src/opportunity_radar/platform/config.py:70`; `compose.yaml:68` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${ANALYSIS_CLAIM_LEASE_SECONDS:+x}" && echo set` | Dono da operação aprova lease |
| `COLLECTION_TARGET_AREA_FLOOR` | `src/opportunity_radar/platform/config.py:73`; `compose.yaml:80` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${COLLECTION_TARGET_AREA_FLOOR:+x}" && echo set` | Dono da operação aprova filtro |
| `COLLECTION_BACKOFF_BASE_SECONDS` | `src/opportunity_radar/platform/config.py:74`; `compose.yaml:69` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM, CI | `test -n "${COLLECTION_BACKOFF_BASE_SECONDS:+x}" && echo set` | Dono da operação aprova atraso |
| `COLLECTION_BACKOFF_CEILING_SECONDS` | `src/opportunity_radar/platform/config.py:75`; `compose.yaml:70` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM, CI | `test -n "${COLLECTION_BACKOFF_CEILING_SECONDS:+x}" && echo set` | Dono da operação aprova atraso |
| `COLLECTION_SOURCE_DEADLINE_SECONDS` | `src/opportunity_radar/platform/config.py:77` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${COLLECTION_SOURCE_DEADLINE_SECONDS:+x}" && echo set` | Dono autoriza após medir fontes |
| `COLLECTION_PASS_DEADLINE_SECONDS` | `src/opportunity_radar/platform/config.py:78` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${COLLECTION_PASS_DEADLINE_SECONDS:+x}" && echo set` | Dono autoriza após medir pass |
| `COLLECTION_HOST_CONCURRENCY` | `src/opportunity_radar/platform/config.py:82` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${COLLECTION_HOST_CONCURRENCY:+x}" && echo set` | Dono da operação aprova carga |
| `COLLECTION_CLAIM_ENABLED` | `src/opportunity_radar/platform/config.py:86` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${COLLECTION_CLAIM_ENABLED:+x}" && echo set` | Dono da operação aprova fencing |
| `COLLECTION_INVENTORY_CONTRACT_ENABLED` | `src/opportunity_radar/platform/config.py:91` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${COLLECTION_INVENTORY_CONTRACT_ENABLED:+x}" && echo set` | Dono da operação aprova cache |
| `CONTENT_CLASSIFICATION_V4_ENABLED` | `src/opportunity_radar/platform/config.py:45`; `compose.yaml:81` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${CONTENT_CLASSIFICATION_V4_ENABLED:+x}" && echo set` | Dono aprova após medição |
| `CONTENT_CLASSIFICATION_ENABLED_RULES` | `src/opportunity_radar/platform/config.py:49`; `compose.yaml:82` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${CONTENT_CLASSIFICATION_ENABLED_RULES:+x}" && echo set` | Dono aprova regras medidas |
| `GREENHOUSE_BASE_URL` | `src/opportunity_radar/platform/config.py:92`; `compose.yaml:71` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local, CI | `curl -fsS "$GREENHOUSE_BASE_URL" >/dev/null` | Dono da operação aprova fornecedor |
| `SOURCE_ALERT_WEBHOOK_URL` | `src/opportunity_radar/platform/config.py:95`; `compose.yaml:72` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | secreta | produção, VM | `test -n "${SOURCE_ALERT_WEBHOOK_URL:+x}" && echo set` | Dono do canal aprova webhook |
| `SOURCE_ALERT_FAILURE_THRESHOLD` | `src/opportunity_radar/platform/config.py:96`; `compose.yaml:73` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${SOURCE_ALERT_FAILURE_THRESHOLD:+x}" && echo set` | Dono da operação aprova limiar |
| `SOURCE_ALERT_TIMEOUT_SECONDS` | `src/opportunity_radar/platform/config.py:97`; `compose.yaml:74` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${SOURCE_ALERT_TIMEOUT_SECONDS:+x}" && echo set` | Dono da operação aprova timeout |
| `PAYLOAD_RETENTION_DAYS` | `src/opportunity_radar/platform/config.py:98`; `compose.yaml:75` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${PAYLOAD_RETENTION_DAYS:+x}" && echo set` | Dono autoriza retenção |
| `PAYLOAD_RETENTION_BATCH_SIZE` | `src/opportunity_radar/platform/config.py:99`; `compose.yaml:76` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${PAYLOAD_RETENTION_BATCH_SIZE:+x}" && echo set` | Dono da operação aprova capacidade |
| `PAYLOAD_RETENTION_INTERVAL_SECONDS` | `src/opportunity_radar/platform/config.py:100`; `compose.yaml:77` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${PAYLOAD_RETENTION_INTERVAL_SECONDS:+x}" && echo set` | Dono da operação aprova intervalo |
| `WORKER_ASSESSMENT_RETENTION_ENABLED` | `src/opportunity_radar/platform/config.py:103`; `compose.yaml:83` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${WORKER_ASSESSMENT_RETENTION_ENABLED:+x}" && echo set` | Dono autoriza exclusão |
| `ASSESSMENT_RETENTION_DAYS` | `src/opportunity_radar/platform/config.py:104`; `compose.yaml:84` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${ASSESSMENT_RETENTION_DAYS:+x}" && echo set` | Dono autoriza retenção |
| `ASSESSMENT_RETENTION_BATCH_SIZE` | `src/opportunity_radar/platform/config.py:105`; `compose.yaml:85` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${ASSESSMENT_RETENTION_BATCH_SIZE:+x}" && echo set` | Dono da operação aprova capacidade |
| `DOCTOR_JOB_GRACE_SECONDS` | `src/opportunity_radar/platform/config.py:107`; `compose.yaml:78` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${DOCTOR_JOB_GRACE_SECONDS:+x}" && echo set` | Dono da operação aprova alerta |

## AI

| Nome | Origem (file:line) | Onde configurar | Pública ou secreta | Ambiente | Comando seguro de validação | Autorização externa necessária |
| --- | --- | --- | --- | --- | --- | --- |
| `AI_ENABLED` | `src/opportunity_radar/platform/config.py:110`; `compose.cloud.yaml:15` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local, CI | `test -n "${AI_ENABLED:+x}" && echo set` | Dono aprova custo e uso de AI |
| `AI_PROVIDER` | `src/opportunity_radar/platform/config.py:111`; `compose.yaml:10` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${AI_PROVIDER:+x}" && echo set` | Dono aprova fornecedor |
| `GROQ_API_KEY` | `src/opportunity_radar/platform/config.py:112`; `compose.cloud.yaml:16` | GitHub repository secret; VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | secreta | produção, VM, local | `test -n "${GROQ_API_KEY:+x}" && echo set` | Administrador Groq cria chave e dono aprova orçamento |
| `GROQ_BASE_URL` | `src/opportunity_radar/platform/config.py:113`; `compose.yaml:12` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local, CI | `curl -fsS "${GROQ_BASE_URL%/}/models" >/dev/null` | Dono aprova endpoint |
| `GROQ_REASONING_MODEL` | `src/opportunity_radar/platform/config.py:114`; `compose.yaml:13` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${GROQ_REASONING_MODEL:+x}" && echo set` | Dono aprova modelo |
| `GROQ_FAST_MODEL` | `src/opportunity_radar/platform/config.py:115`; `compose.yaml:14` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${GROQ_FAST_MODEL:+x}" && echo set` | Dono aprova modelo |
| `GROQ_ALT_MODEL` | `src/opportunity_radar/platform/config.py:116`; `compose.yaml:15` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${GROQ_ALT_MODEL:+x}" && echo set` | Dono aprova modelo |
| `TOKENHARBOR_API_KEY` | `src/opportunity_radar/platform/config.py:119`; `compose.yaml:16` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | secreta | produção, VM, local | `test -n "${TOKENHARBOR_API_KEY:+x}" && echo set` | Administrador TokenHarbor cria chave e dono aprova uso |
| `TOKENHARBOR_BASE_URL` | `src/opportunity_radar/platform/config.py:120`; `compose.yaml:17` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${TOKENHARBOR_BASE_URL:+x}" && echo set` | Dono aprova endpoint |
| `TOKENHARBOR_MODELS` | `src/opportunity_radar/platform/config.py:121`; `compose.yaml:18` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${TOKENHARBOR_MODELS:+x}" && echo set` | Dono aprova modelos |
| `CEREBRAS_API_KEY` | `src/opportunity_radar/platform/config.py:179`; `compose.yaml:19`; `compose.cloud.yaml:20` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | secreta | produção, VM, local | `test -n "${CEREBRAS_API_KEY:+x}" && echo set` | Administrador Cerebras cria chave e dono aprova uso |
| `CEREBRAS_BASE_URL` | `src/opportunity_radar/platform/config.py:180`; `compose.yaml:20`; `compose.cloud.yaml:21` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${CEREBRAS_BASE_URL:+x}" && echo set` | Dono aprova endpoint |
| `CEREBRAS_MODELS` | `src/opportunity_radar/platform/config.py:181`; `compose.yaml:21`; `compose.cloud.yaml:22` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${CEREBRAS_MODELS:+x}" && echo set` | Dono aprova modelos |
| `ZEN_API_KEY` | `src/opportunity_radar/platform/config.py:182`; `compose.yaml:22`; `compose.cloud.yaml:23` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | secreta | produção, VM, local | `test -n "${ZEN_API_KEY:+x}" && echo set` | Administrador OpenCode Zen cria chave e dono aprova uso |
| `ZEN_BASE_URL` | `src/opportunity_radar/platform/config.py:183`; `compose.yaml:23`; `compose.cloud.yaml:24` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${ZEN_BASE_URL:+x}" && echo set` | Dono aprova endpoint |
| `ZEN_MODELS` | `src/opportunity_radar/platform/config.py:184`; `compose.yaml:24`; `compose.cloud.yaml:25` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${ZEN_MODELS:+x}" && echo set` | Dono aprova modelos |
| `GEMINI_API_KEY` | `src/opportunity_radar/platform/config.py:185`; `compose.yaml:25`; `compose.cloud.yaml:26` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | secreta | produção, VM, local | `test -n "${GEMINI_API_KEY:+x}" && echo set` | Administrador Google AI Studio cria chave e dono aprova uso |
| `GEMINI_BASE_URL` | `src/opportunity_radar/platform/config.py:186`; `compose.yaml:26`; `compose.cloud.yaml:27` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${GEMINI_BASE_URL:+x}" && echo set` | Dono aprova endpoint |
| `GEMINI_MODELS` | `src/opportunity_radar/platform/config.py:187`; `compose.yaml:27`; `compose.cloud.yaml:28` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${GEMINI_MODELS:+x}" && echo set` | Dono aprova modelos |
| `OPENROUTER_API_KEY` | `src/opportunity_radar/platform/config.py:188`; `compose.yaml:28`; `compose.cloud.yaml:29` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | secreta | produção, VM, local | `test -n "${OPENROUTER_API_KEY:+x}" && echo set` | Administrador OpenRouter cria chave e dono aprova uso |
| `OPENROUTER_BASE_URL` | `src/opportunity_radar/platform/config.py:189`; `compose.yaml:29`; `compose.cloud.yaml:30` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${OPENROUTER_BASE_URL:+x}" && echo set` | Dono aprova endpoint |
| `OPENROUTER_MODELS` | `src/opportunity_radar/platform/config.py:190`; `compose.yaml:30`; `compose.cloud.yaml:31` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${OPENROUTER_MODELS:+x}" && echo set` | Dono aprova modelos |
| `MISTRAL_API_KEY` | `src/opportunity_radar/platform/config.py:191`; `compose.yaml:31`; `compose.cloud.yaml:32` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | secreta | produção, VM, local | `test -n "${MISTRAL_API_KEY:+x}" && echo set` | Administrador Mistral cria chave e dono aprova uso |
| `MISTRAL_BASE_URL` | `src/opportunity_radar/platform/config.py:192`; `compose.yaml:32`; `compose.cloud.yaml:33` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${MISTRAL_BASE_URL:+x}" && echo set` | Dono aprova endpoint |
| `MISTRAL_MODELS` | `src/opportunity_radar/platform/config.py:193`; `compose.yaml:33`; `compose.cloud.yaml:34` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${MISTRAL_MODELS:+x}" && echo set` | Dono aprova modelos |
| `NIM_API_KEY` | `src/opportunity_radar/platform/config.py:194`; `compose.yaml:34`; `compose.cloud.yaml:35` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | secreta | produção, VM, local | `test -n "${NIM_API_KEY:+x}" && echo set` | Administrador NVIDIA NIM cria chave e dono aprova uso |
| `NIM_BASE_URL` | `src/opportunity_radar/platform/config.py:195`; `compose.yaml:35`; `compose.cloud.yaml:36` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${NIM_BASE_URL:+x}" && echo set` | Dono aprova endpoint |
| `NIM_MODELS` | `src/opportunity_radar/platform/config.py:196`; `compose.yaml:36`; `compose.cloud.yaml:37` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${NIM_MODELS:+x}" && echo set` | Dono aprova modelos |
| `WORKERSAI_API_KEY` | `src/opportunity_radar/platform/config.py:197`; `compose.yaml:37`; `compose.cloud.yaml:38` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | secreta | produção, VM, local | `test -n "${WORKERSAI_API_KEY:+x}" && echo set` | Administrador Cloudflare Workers AI cria chave e dono aprova uso |
| `WORKERSAI_BASE_URL` | `src/opportunity_radar/platform/config.py:199`; `compose.yaml:38`; `compose.cloud.yaml:39` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${WORKERSAI_BASE_URL:+x}" && echo set` | Dono aprova endpoint |
| `WORKERSAI_MODELS` | `src/opportunity_radar/platform/config.py:200`; `compose.yaml:39`; `compose.cloud.yaml:40` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${WORKERSAI_MODELS:+x}" && echo set` | Dono aprova modelos |
| `CLOUDFLARE_ACCOUNT_ID` | `src/opportunity_radar/platform/config.py:201`; `compose.yaml:40`; `compose.cloud.yaml:41` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${CLOUDFLARE_ACCOUNT_ID:+x}" && echo set` | Dono informa o id da conta Cloudflare |
| `AI_RESERVE_ORDER` | `src/opportunity_radar/platform/config.py:202`; `compose.yaml:41`; `compose.cloud.yaml:42` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${AI_RESERVE_ORDER:+x}" && echo set` | Dono aprova a ordem dos provedores de reserva |
| `AI_PROVIDER_LIMITS` | `src/opportunity_radar/platform/config.py:205`; `compose.yaml:42`; `compose.cloud.yaml:43` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `test -n "${AI_PROVIDER_LIMITS:+x}" && echo set` | Dono aprova limites por provedor |
| `AI_TIMEOUT_SECONDS` | `src/opportunity_radar/platform/config.py:122`; `compose.yaml:19` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_TIMEOUT_SECONDS:+x}" && echo set` | Dono da operação aprova timeout |
| `AI_CONNECT_TIMEOUT_SECONDS` | `src/opportunity_radar/platform/config.py:123`; `compose.yaml:20` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_CONNECT_TIMEOUT_SECONDS:+x}" && echo set` | Dono da operação aprova timeout |
| `AI_MAX_RETRIES` | `src/opportunity_radar/platform/config.py:124`; `compose.yaml:21` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_MAX_RETRIES:+x}" && echo set` | Dono da operação aprova retry |
| `AI_FALLBACK_ENABLED` | `src/opportunity_radar/platform/config.py:125`; `compose.yaml:22` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_FALLBACK_ENABLED:+x}" && echo set` | Dono aprova fallback |
| `AI_REASONING_EFFORT` | `src/opportunity_radar/platform/config.py:126`; `compose.yaml:23` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_REASONING_EFFORT:+x}" && echo set` | Dono aprova qualidade e custo |
| `AI_REASONING_EFFORT_JOB_MATCH` | `src/opportunity_radar/platform/config.py:130`; `compose.yaml:59` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_REASONING_EFFORT_JOB_MATCH:+x}" && echo set` | Dono aprova custo |
| `AI_REASONING_EFFORT_JOB_CLASSIFICATION` | `src/opportunity_radar/platform/config.py:131`; `compose.yaml:60` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_REASONING_EFFORT_JOB_CLASSIFICATION:+x}" && echo set` | Dono aprova custo |
| `AI_REASONING_EFFORT_JOB_EXTRACTION` | `src/opportunity_radar/platform/config.py:132`; `compose.yaml:61` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_REASONING_EFFORT_JOB_EXTRACTION:+x}" && echo set` | Dono aprova custo |
| `AI_ANALYSIS_PROMPT` | `src/opportunity_radar/platform/config.py:133`; `compose.yaml:24` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_ANALYSIS_PROMPT:+x}" && echo set` | Dono aprova prompt |
| `AI_DAILY_REQUESTS_SOFT_LIMIT` | `src/opportunity_radar/platform/config.py:134`; `compose.yaml:25` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_DAILY_REQUESTS_SOFT_LIMIT:+x}" && echo set` | Dono aprova orçamento |
| `AI_DAILY_TOKENS_SOFT_LIMIT` | `src/opportunity_radar/platform/config.py:135`; `compose.yaml:26` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_DAILY_TOKENS_SOFT_LIMIT:+x}" && echo set` | Dono aprova orçamento |
| `AI_INTERACTIVE_RESERVE_REQUESTS` | `src/opportunity_radar/platform/config.py:139`; `compose.yaml:57` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_INTERACTIVE_RESERVE_REQUESTS:+x}" && echo set` | Dono aprova reserva |
| `AI_MINUTE_TOKENS_SOFT_LIMIT` | `src/opportunity_radar/platform/config.py:140`; `compose.yaml:27` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_MINUTE_TOKENS_SOFT_LIMIT:+x}" && echo set` | Dono aprova orçamento |
| `AI_MINUTE_REQUESTS_SOFT_LIMIT` | `src/opportunity_radar/platform/config.py:141`; `compose.yaml:28` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_MINUTE_REQUESTS_SOFT_LIMIT:+x}" && echo set` | Dono aprova orçamento |
| `AI_BREAKER_FAILURES` | `src/opportunity_radar/platform/config.py:142`; `compose.yaml:29` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_BREAKER_FAILURES:+x}" && echo set` | Dono aprova proteção |
| `AI_BREAKER_COOLDOWN_SECONDS` | `src/opportunity_radar/platform/config.py:143`; `compose.yaml:30` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_BREAKER_COOLDOWN_SECONDS:+x}" && echo set` | Dono aprova proteção |
| `AI_CALL_RECORD_RETENTION_DAYS` | `src/opportunity_radar/platform/config.py:146`; `compose.yaml:58` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${AI_CALL_RECORD_RETENTION_DAYS:+x}" && echo set` | Dono aprova retenção |
| `TAVILY_API_KEY` | `src/opportunity_radar/platform/config.py:150`; `compose.cloud.yaml:17` | GitHub repository secret; VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | secreta | produção, VM, local | `test -n "${TAVILY_API_KEY:+x}" && echo set` | Administrador Tavily cria chave e dono aprova créditos |
| `TAVILY_BASE_URL` | `src/opportunity_radar/platform/config.py:151`; `compose.yaml:34` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600`; local `.env` only | pública | produção, VM, local | `curl -fsS "$TAVILY_BASE_URL" >/dev/null` | Dono aprova endpoint |
| `TAVILY_SEARCH_DEPTH` | `src/opportunity_radar/platform/config.py:155`; `compose.yaml:35` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${TAVILY_SEARCH_DEPTH:+x}" && echo set` | Dono aprova custo |
| `TAVILY_EXTRACT_DEPTH` | `src/opportunity_radar/platform/config.py:156`; `compose.yaml:36` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${TAVILY_EXTRACT_DEPTH:+x}" && echo set` | Dono aprova custo |
| `TAVILY_EXTRACT_FORMAT` | `src/opportunity_radar/platform/config.py:157`; `compose.yaml:37` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${TAVILY_EXTRACT_FORMAT:+x}" && echo set` | Dono aprova formato |
| `TAVILY_EXTRACT_CACHE_TTL_SECONDS` | `src/opportunity_radar/platform/config.py:161`; `compose.yaml:39` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${TAVILY_EXTRACT_CACHE_TTL_SECONDS:+x}" && echo set` | Dono aprova cache |
| `TAVILY_CREDIT_BUDGET_PER_RUN` | `src/opportunity_radar/platform/config.py:166`; `compose.yaml:38` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${TAVILY_CREDIT_BUDGET_PER_RUN:+x}" && echo set` | Dono aprova orçamento |
| `EXTRACTION_SKIP_SOURCE_TYPES` | `src/opportunity_radar/platform/config.py:169`; `compose.yaml:40` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${EXTRACTION_SKIP_SOURCE_TYPES:+x}" && echo set` | Dono aprova fontes |
| `TAVILY_EXTRACT_HOST_FAILURE_THRESHOLD` | `src/opportunity_radar/platform/config.py:171`; `compose.yaml:41` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${TAVILY_EXTRACT_HOST_FAILURE_THRESHOLD:+x}" && echo set` | Dono aprova proteção |
| `HOST_REQUEST_CEILINGS` | `src/opportunity_radar/platform/config.py:174`; `compose.yaml:42` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test -n "${HOST_REQUEST_CEILINGS:+x}" && echo set` | Dono aprova limites |

## Proxy/TLS

| Nome | Origem (file:line) | Onde configurar | Pública ou secreta | Ambiente | Comando seguro de validação | Autorização externa necessária |
| --- | --- | --- | --- | --- | --- | --- |
| `PUBLIC_HOSTNAME` | `compose.cloud.yaml:61`; `docker/proxy/nginx.conf.template:12` | VM EnvironmentFile `/etc/opportunity-radar/proxy.env` `0600` | pública | produção, VM | `test -n "${PUBLIC_HOSTNAME:+x}" && echo set` | Dono do domínio aprova hostname |
| `TLS_FULLCHAIN_PATH` | `compose.cloud.yaml:74` | VM EnvironmentFile `/etc/opportunity-radar/proxy.env` `0600` | secreta | produção, VM | `test -r "$TLS_FULLCHAIN_PATH" && echo readable` | Dono do domínio aprova certificado |
| `TLS_PRIVATE_KEY_PATH` | `compose.cloud.yaml:78` | VM EnvironmentFile `/etc/opportunity-radar/proxy.env` `0600` | secreta | produção, VM | `test -r "$TLS_PRIVATE_KEY_PATH" && echo readable` | Dono do domínio controla chave privada |

## Frontend/Cloudflare

| Nome | Origem (file:line) | Onde configurar | Pública ou secreta | Ambiente | Comando seguro de validação | Autorização externa necessária |
| --- | --- | --- | --- | --- | --- | --- |
| `VITE_CLERK_PUBLISHABLE_KEY` | `apps/web/src/main.tsx:8` | Cloudflare Workers Builds variables; local `.env` only | pública | produção, preview, local | `test "${VITE_CLERK_PUBLISHABLE_KEY#pk_live_}" != "$VITE_CLERK_PUBLISHABLE_KEY" && echo valid` | Administrador Clerk cria aplicação e aprova chave |
| `VITE_API_BASE_URL` | `apps/web/src/lib/api.ts:1` | Cloudflare Workers Builds variables; local `.env` only | pública | produção, preview, local | `test -n "${VITE_API_BASE_URL:+x}" && echo set` | Dono do domínio aprova API |
| `VITE_API_PROXY_TARGET` | `apps/web/vite.config.ts:14` | Cloudflare Workers Builds variables; local `.env` only | pública | preview, local | `test -n "${VITE_API_PROXY_TARGET:+x}" && echo set` | Dono da aplicação aprova proxy |

## CI/GitHub

| Nome | Origem (file:line) | Onde configurar | Pública ou secreta | Ambiente | Comando seguro de validação | Autorização externa necessária |
| --- | --- | --- | --- | --- | --- | --- |
| `PYTHON_VERSION` | `.github/workflows/pipeline.yml:29` | GitHub repository variable | pública | CI | `gh variable list | grep -c '^PYTHON_VERSION'` | Maintainer aprova runtime |
| `NODE_VERSION` | `.github/workflows/pipeline.yml:30` | GitHub repository variable | pública | CI | `gh variable list | grep -c '^NODE_VERSION'` | Maintainer aprova runtime |
| `CI_UID` | `.github/workflows/pipeline.yml:210`; `compose.ci.yaml:62` | GitHub workflow `env` | pública | CI | `test -n "${CI_UID:+x}" && echo set` | Runner fornece valor |
| `CI_GID` | `.github/workflows/pipeline.yml:211`; `compose.ci.yaml:62` | GitHub workflow `env` | pública | CI | `test -n "${CI_GID:+x}" && echo set` | Runner fornece valor |
| `NODE_EXTRA_CA_CERTS` | `.github/workflows/pipeline.yml:212` | GitHub workflow `env` | secreta | CI | `test -r "$NODE_EXTRA_CA_CERTS" && echo readable` | Runner cria CA efêmera |

## Imagens

| Nome | Origem (file:line) | Onde configurar | Pública ou secreta | Ambiente | Comando seguro de validação | Autorização externa necessária |
| --- | --- | --- | --- | --- | --- | --- |
| `API_IMAGE` | `compose.cloud.yaml:21` | GitHub repository variable; VM EnvironmentFile `/etc/opportunity-radar/images.env` `0600` | pública | CI, produção, VM | `docker compose -f compose.cloud.yaml config --quiet` | Maintainer aprova digest ARM64 |
| `WORKER_IMAGE` | `compose.cloud.yaml:47` | GitHub repository variable; VM EnvironmentFile `/etc/opportunity-radar/images.env` `0600` | pública | CI, produção, VM | `docker compose -f compose.cloud.yaml config --quiet` | Maintainer aprova digest ARM64 |
| `PROXY_IMAGE` | `compose.cloud.yaml:59` | GitHub repository variable; VM EnvironmentFile `/etc/opportunity-radar/images.env` `0600` | pública | CI, produção, VM | `docker compose -f compose.cloud.yaml config --quiet` | Maintainer aprova digest ARM64 |
| `POSTGRES_DB` | `compose.yaml:101`; `compose.ci.yaml:10` | local `.env` only; CI workflow | pública | local, CI | `test -n "${POSTGRES_DB:+x}" && echo set` | Maintainer aprova banco de teste |
| `POSTGRES_USER` | `compose.yaml:102`; `compose.ci.yaml:11` | local `.env` only; CI workflow | pública | local, CI | `test -n "${POSTGRES_USER:+x}" && echo set` | Maintainer aprova usuário de teste |
| `POSTGRES_PASSWORD` | `compose.yaml:103`; `compose.ci.yaml:12` | local `.env` only; CI workflow secret | secreta | local, CI | `test -n "${POSTGRES_PASSWORD:+x}" && echo set` | Maintainer aprova credencial efêmera |

## Pipeline finito

| Nome | Origem (file:line) | Onde configurar | Pública ou secreta | Ambiente | Comando seguro de validação | Autorização externa necessária |
| --- | --- | --- | --- | --- | --- | --- |
| `PIPELINE_DEADLINE_SECONDS` | `compose.cloud.yaml:51`; `infra/systemd/run-opportunity-radar-window:28` | VM EnvironmentFile `/etc/opportunity-radar/worker.env` `0600` | pública | produção, VM | `test "${PIPELINE_DEADLINE_SECONDS:-0}" -gt 0` | Dono da operação aprova janela |
| `PIPELINE_WINDOW_SECONDS` | `infra/systemd/run-opportunity-radar-window:5` | VM EnvironmentFile `/etc/opportunity-radar/pipeline.env` `0600` | pública | produção, VM | `test "${PIPELINE_WINDOW_SECONDS:-0}" -gt 0` | Dono da operação aprova janela |
| `DEFAULT_WINDOW_SECONDS` | `infra/systemd/run-opportunity-radar-window:4` | Constante interna do wrapper; não configurar externamente | pública | produção, VM | `test "900" -gt 0` | Maintainer aprova janela padrão |
| `PIPELINE_COMPOSE_BIN` | `infra/systemd/run-opportunity-radar-window:31` | VM EnvironmentFile `/etc/opportunity-radar/pipeline.env` `0600`; somente wrapper aprovado | pública | produção, VM, teste | `test -n "${PIPELINE_COMPOSE_BIN:+x}" && echo set` | Dono da operação aprova wrapper |
| `PIPELINE_APP_DIR` | `infra/systemd/run-opportunity-radar-window:32` | VM EnvironmentFile `/etc/opportunity-radar/pipeline.env` `0600` | pública | produção, VM | `test -d "${PIPELINE_APP_DIR:-/opt/opportunity-radar}"` | Dono da operação aprova diretório |
| `RUN_ID` | `infra/systemd/run-opportunity-radar-window:25` | Gerada pelo wrapper; não configurar externamente | pública | produção, VM | `test -n "${RUN_ID:+x}" && echo set` | Dono da operação aprova correlação |
| `DEADLINE_UTC` | `infra/systemd/run-opportunity-radar-window:26` | Gerada pelo wrapper; não configurar externamente | pública | produção, VM | `test -n "${DEADLINE_UTC:+x}" && echo set` | Dono da operação aprova janela |

## Backup

O backup usa `DATABASE_URL` e deriva overrides para libpq. Senhas nunca entram
diretamente em variável de processo: `pgpassfile_for_url` cria um passfile
temporário com permissão `0600` (`src/opportunity_radar/platform/backup.py:153-156,
196`).

| Nome | Origem (file:line) | Onde configurar | Pública ou secreta | Ambiente | Comando seguro de validação | Autorização externa necessária |
| --- | --- | --- | --- | --- | --- | --- |
| `BACKUP_RETENTION_DAYS` | `scripts/backup.py:140` | VM EnvironmentFile `/etc/opportunity-radar/backup.env` `0600` | pública | produção, VM | `test -n "${BACKUP_RETENTION_DAYS:+x}" && echo set` | Dono aprova retenção |
| `PGHOST` | `src/opportunity_radar/platform/backup.py:118`; `scripts/restore_check.py:56` | **Somente** passfile temporário `0600` ou ambiente limpo de validação | secreta | produção, VM, CI | `test -z "${PGHOST:-}" && echo unset` | Dono Neon aprova destino |
| `PGHOSTADDR` | `src/opportunity_radar/platform/backup.py:119`; `scripts/restore_check.py:57` | **Somente** passfile temporário `0600` ou ambiente limpo de validação | secreta | produção, VM, CI | `test -z "${PGHOSTADDR:-}" && echo unset` | Dono Neon aprova destino |
| `PGPORT` | `src/opportunity_radar/platform/backup.py:120`; `scripts/restore_check.py:58` | **Somente** passfile temporário `0600` ou ambiente limpo de validação | pública | produção, VM, CI | `test -z "${PGPORT:-}" && echo unset` | Dono Neon aprova destino |
| `PGDATABASE` | `src/opportunity_radar/platform/backup.py:121`; `scripts/restore_check.py:59` | **Somente** passfile temporário `0600` ou ambiente limpo de validação | pública | produção, VM, CI | `test -z "${PGDATABASE:-}" && echo unset` | Dono Neon aprova destino |
| `PGUSER` | `src/opportunity_radar/platform/backup.py:122`; `scripts/restore_check.py:60` | **Somente** passfile temporário `0600` ou ambiente limpo de validação | secreta | produção, VM, CI | `test -z "${PGUSER:-}" && echo unset` | Dono Neon aprova usuário |
| `PGPASSWORD` | `src/opportunity_radar/platform/backup.py:123` | **Nunca configurar**; usar passfile temporário `0600` | secreta | produção, VM, CI | `test -z "${PGPASSWORD:-}" && echo unset` | Dono Neon aprova credencial |
| `PGPASSFILE` | `src/opportunity_radar/platform/backup.py:124`; `src/opportunity_radar/platform/backup.py:197` | Passfile temporário `0600`, criado pelo script | secreta | produção, VM, CI | `test -z "${PGPASSFILE:-}" || test "$(stat -c '%a' "$PGPASSFILE" 2>/dev/null)" = 600` | Dono Neon aprova credencial |
| `PGSERVICE` | `src/opportunity_radar/platform/backup.py:125`; `scripts/restore_check.py:61` | Ambiente limpo; não configurar no restore | pública | produção, VM, CI | `test -z "${PGSERVICE:-}" && echo unset` | Dono Neon aprova destino |
| `PGSERVICEFILE` | `src/opportunity_radar/platform/backup.py:126`; `scripts/restore_check.py:62` | Ambiente limpo; não configurar no restore | secreta | produção, VM, CI | `test -z "${PGSERVICEFILE:-}" && echo unset` | Dono Neon aprova destino |
| `PGSYSCONFDIR` | `scripts/restore_check.py:63` | Ambiente limpo; não configurar no restore | secreta | produção, VM, CI | `test -z "${PGSYSCONFDIR:-}" && echo unset` | Dono Neon aprova destino |
| `PGOPTIONS` | `src/opportunity_radar/platform/backup.py:127` | Ambiente limpo; não configurar no restore | secreta | produção, VM, CI | `test -z "${PGOPTIONS:-}" && echo unset` | Dono Neon aprova destino |
| `PGSSLMODE` | `src/opportunity_radar/platform/backup.py:128` | VM EnvironmentFile `/etc/opportunity-radar/backup.env` `0600` | pública | produção, VM | `test -n "${PGSSLMODE:+x}" && echo set` | Dono Neon aprova TLS |
| `PGREQUIRESSL` | `src/opportunity_radar/platform/backup.py:129` | Ambiente limpo; não configurar no restore | pública | produção, VM, CI | `test -z "${PGREQUIRESSL:-}" && echo unset` | Dono Neon aprova TLS |
| `PGSSLCOMPRESSION` | `src/opportunity_radar/platform/backup.py:130` | Ambiente limpo; não configurar no restore | pública | produção, VM, CI | `test -z "${PGSSLCOMPRESSION:-}" && echo unset` | Dono Neon aprova TLS |
| `PGSSLCERT` | `src/opportunity_radar/platform/backup.py:131` | Ambiente limpo; não configurar no restore | secreta | produção, VM, CI | `test -z "${PGSSLCERT:-}" && echo unset` | Dono Neon aprova certificado |
| `PGSSLKEY` | `src/opportunity_radar/platform/backup.py:132` | Ambiente limpo; não configurar no restore | secreta | produção, VM, CI | `test -z "${PGSSLKEY:-}" && echo unset` | Dono Neon aprova chave |
| `PGSSLROOTCERT` | `src/opportunity_radar/platform/backup.py:133`; `src/opportunity_radar/platform/backup.py:169` | VM EnvironmentFile `/etc/opportunity-radar/backup.env` `0600` | secreta | produção, VM | `test -r "$PGSSLROOTCERT" && echo readable` | Dono Neon aprova CA |
| `PGSSLCRL` | `src/opportunity_radar/platform/backup.py:134` | Ambiente limpo; não configurar no restore | secreta | produção, VM, CI | `test -z "${PGSSLCRL:-}" && echo unset` | Dono Neon aprova revogação |
| `PGSSLCRLDIR` | `src/opportunity_radar/platform/backup.py:135` | Ambiente limpo; não configurar no restore | secreta | produção, VM, CI | `test -z "${PGSSLCRLDIR:-}" && echo unset` | Dono Neon aprova revogação |
| `PGCHANNELBINDING` | `src/opportunity_radar/platform/backup.py:136` | Ambiente limpo; não configurar no restore | pública | produção, VM, CI | `test -z "${PGCHANNELBINDING:-}" && echo unset` | Dono Neon aprova TLS |
| `PGTARGETSESSIONATTRS` | `src/opportunity_radar/platform/backup.py:137` | Ambiente limpo; não configurar no restore | pública | produção, VM, CI | `test -z "${PGTARGETSESSIONATTRS:-}" && echo unset` | Dono Neon aprova destino |
| `PGLOADBALANCEHOSTS` | `src/opportunity_radar/platform/backup.py:138` | Ambiente limpo; não configurar no restore | pública | produção, VM, CI | `test -z "${PGLOADBALANCEHOSTS:-}" && echo unset` | Dono Neon aprova destino |
| `PGCONNECT_TIMEOUT` | `src/opportunity_radar/platform/backup.py:139` | VM EnvironmentFile `/etc/opportunity-radar/backup.env` `0600` | pública | produção, VM | `test -n "${PGCONNECT_TIMEOUT:+x}" && echo set` | Dono Neon aprova timeout |

## Testes

| Nome | Origem (file:line) | Onde configurar | Pública ou secreta | Ambiente | Comando seguro de validação | Autorização externa necessária |
| --- | --- | --- | --- | --- | --- | --- |
| `RUN_DATABASE_INTEGRATION` | `.github/workflows/pipeline.yml:67`; `scripts/restore_check.py:82` | GitHub workflow `env` | pública | CI/test only | `test "${RUN_DATABASE_INTEGRATION:-}" = 1 && echo enabled` | Maintainer autoriza banco isolado |
| `DATABASE_INTEGRATION_ISOLATED` | `.github/workflows/pipeline.yml:68`; `scripts/restore_check.py:84` | GitHub workflow `env` | pública | CI/test only | `test "${DATABASE_INTEGRATION_ISOLATED:-}" = 1 && echo enabled` | Maintainer confirma banco `_test` |
| `CI_AUTH_DIR` | `compose.ci.yaml:66`; `.github/workflows/pipeline.yml:209` | GitHub workflow `env` | secreta | CI | `test -d "$CI_AUTH_DIR" && echo directory` | Runner cria diretório efêmero |
| `SSL_CERT_FILE` | `compose.ci.yaml:115` | GitHub workflow `env` | pública | CI | `test -r "$SSL_CERT_FILE" && echo readable` | Maintainer aprova CA efêmera |

## Terraform/OCI

Estes nomes são variáveis Terraform, não variáveis de processo. Configure-os
como variáveis mascaradas do Resource Manager. Nunca salve valores reais em
`terraform.tfvars` versionado.

| Nome | Origem (file:line) | Onde configurar | Pública ou secreta | Ambiente | Comando seguro de validação | Autorização externa necessária |
| --- | --- | --- | --- | --- | --- | --- |
| `region` | `infra/terraform/oci/variables.tf:1` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Dono OCI aprova região |
| `compartment_id` | `infra/terraform/oci/variables.tf:11` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Dono OCI aprova compartment |
| `availability_domain` | `infra/terraform/oci/variables.tf:21` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Dono OCI confirma capacidade |
| `arm_image_id` | `infra/terraform/oci/variables.tf:31` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Dono OCI aprova imagem |
| `ssh_public_key` | `infra/terraform/oci/variables.tf:41` | Resource Manager stack variables mascarada | secreta | produção, VM | `terraform validate` | Administrador OCI aprova acesso SSH |
| `vcn_cidr` | `infra/terraform/oci/variables.tf:52` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Dono OCI aprova rede |
| `public_subnet_cidr` | `infra/terraform/oci/variables.tf:63` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Dono OCI aprova rede |
| `admin_cidr` | `infra/terraform/oci/variables.tf:74` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Administrador aprova rede SSH |
| `instance_shape` | `infra/terraform/oci/variables.tf:84` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Dono OCI aprova Always Free |
| `shape_ocpus` | `infra/terraform/oci/variables.tf:95` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Dono OCI aprova quota |
| `shape_memory_in_gbs` | `infra/terraform/oci/variables.tf:106` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Dono OCI aprova quota |
| `boot_volume_size_gbs` | `infra/terraform/oci/variables.tf:117` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Dono OCI aprova custo |
| `backup_bucket_name` | `infra/terraform/oci/variables.tf:128` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Dono OCI aprova bucket privado |
| `backup_storage_limit_gbs` | `infra/terraform/oci/variables.tf:138` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Dono OCI aprova limite |
| `backup_monthly_request_limit` | `infra/terraform/oci/variables.tf:149` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Dono OCI aprova limite |
| `resource_prefix` | `infra/terraform/oci/variables.tf:160` | Resource Manager stack variables | pública | produção, VM | `terraform validate` | Dono OCI aprova naming |

## Checklist manual final

Marque cada item somente após executar validação sem imprimir valor. Use
placeholders como `<DOMINIO>`. A variável `TENANCY_OWNER_API_READY` só pode ser
definida pelo dono depois de guardar evidência de chamadas com escopo do dono;
existência de token, login ou endpoint público não é evidência suficiente.

1. **GitHub**
   - [ ] Criar variáveis `API_IMAGE`, `WORKER_IMAGE` e `PROXY_IMAGE` com digests
     ARM64 aprovados. Validar com `gh variable list | grep -c '^API_IMAGE'` e
     repetir para cada imagem. Isso libera o compose cloud com imagens imutáveis.
   - [ ] Criar secrets `GROQ_API_KEY` e `TAVILY_API_KEY` somente quando o dono
     aprovar custo. Validar com `gh secret list | grep -c '^GROQ_API_KEY'`.
     Isso libera AI no CI ou no fluxo autorizado.
   - [ ] Definir `TENANCY_OWNER_API_READY` somente após evidência owner-scoped.
     Validar com `gh variable list | grep -c '^TENANCY_OWNER_API_READY'`.
     Isso libera o gate de tenancy; sem evidência, mantenha ausente.
   - [ ] Confirmar `RUN_DATABASE_INTEGRATION=1` e
     `DATABASE_INTEGRATION_ISOLATED=1` no workflow. Validar com
     `grep -c 'RUN_DATABASE_INTEGRATION: "1"' .github/workflows/pipeline.yml`.
     Isso libera testes de banco isolados.
2. **Cloudflare**
   - [ ] Configurar `VITE_CLERK_PUBLISHABLE_KEY` e `VITE_API_BASE_URL` em
     Workers Builds variables. Validar com
     `test -n "${VITE_API_BASE_URL:+x}" && echo set` no build.
     Isso libera frontend apontando para `<DOMINIO>`.
   - [ ] Configurar `<DOMINIO>` e origem exata em `FRONTEND_ORIGIN` e
     `CLERK_AUTHORIZED_PARTIES`. Validar com
     `curl -fsS https://<DOMINIO>/ >/dev/null`. Isso libera CORS e tráfego
     browser para a API.
3. **Clerk**
   - [ ] Criar aplicação, domínio e usuário dono. Registrar
     `CLERK_ISSUER`, `CLERK_JWKS_URL`, `CLERK_OWNER_SUB` e, após merge da PR
     #80, `CLERK_AUDIENCE`. Validar JWKS com
     `curl -fsS "${CLERK_JWKS_URL}" >/dev/null`. Isso libera validação JWT.
   - [ ] Confirmar que subject usado em `CLERK_OWNER_SUB` é o usuário dono e
     não um usuário de teste. Validar com
     `test -n "${CLERK_OWNER_SUB:+x}" && echo set`. Isso libera autorização
     owner-scoped.
4. **Neon**
   - [ ] Criar banco de produção e configurar `DATABASE_URL` somente na VM.
     Validar com `test -n "${DATABASE_URL:+x}" && echo set`. Isso libera
     migração contra banco gerenciado.
   - [ ] Confirmar endpoint JWKS e acesso de rede a partir da VM. Validar com
     `curl -fsS "${CLERK_JWKS_URL}" >/dev/null`. Isso libera API autenticada.
5. **OCI VM**
   - [ ] Criar stack Resource Manager, preencher variáveis OCI e executar
     somente Plan aprovado. Validar com `terraform validate`. Isso libera
     Apply separado e autorizado.
   - [ ] Criar `/etc/opportunity-radar/api.env`, `worker.env`, `proxy.env` e
     `backup.env` com modo `0600`. Validar com
     `stat -c '%a' /etc/opportunity-radar/api.env`. Isso libera leitura de
     configuração sem expor segredos.
   - [ ] Configurar imagens, Clerk, Neon, owner subjects e `PUBLIC_HOSTNAME`.
     Validar com `docker compose -f compose.cloud.yaml config --quiet`. Isso
     libera migração, API, worker e proxy.
   - [ ] Instalar certificado fullchain e chave privada fora do Git; configurar
     `TLS_FULLCHAIN_PATH` e `TLS_PRIVATE_KEY_PATH`. Validar com
     `test -r "$TLS_FULLCHAIN_PATH" && test -r "$TLS_PRIVATE_KEY_PATH" && echo readable`.
     Isso libera HTTPS público.
    - [ ] Configurar wrapper systemd e `PIPELINE_WINDOW_SECONDS` no arquivo
      `/etc/opportunity-radar/pipeline.env`. Validar com
      `test "${PIPELINE_WINDOW_SECONDS:-0}" -gt 0`. Isso libera janela finita
      do pipeline.
   - [ ] Criar passfile temporário `0600` para backup e restore. Validar com
     `test -z "${PGPASSWORD:-}" && echo unset`. Isso libera backup sem senha em
     variável de processo.

## Runbooks

- [Plano F53 de hospedagem](../53-plano-hospedagem-cloudflare-oracle-neon-clerk.md)
- [F53-01 — inventário e baseline](cards/f53-01-inventario-orcamento-baseline.md)
- [F53-02 — contas, domínio e DNS](cards/f53-02-contas-dominio-dns.md)
- [F53-04 — Terraform, rede e VM](cards/f53-04-terraform-rede-vm.md)
- [F53-07 — Clerk e autorização da API](cards/f53-07-clerk-autorizacao-api.md)
- [F53-09 — TLS, CORS e rede](cards/f53-09-tls-cors-rede.md)
- [F53-10 — pipeline finito](cards/f53-10-pipeline-finito.md)
- [F53-14 — backup e restore](cards/f53-14-backup-restore.md)
- [Backup consistente e restauração F18-08](../40-roadmap-varredura-produtiva/fase-18/f18-08-backup-consistente-e-restauracao.md)
- [Backup consistente e restauração F20-41](../44-roadmap-fase-20/fase-20/f20-41-backup-consistente-e-restauracao.md)
- `infra/systemd/README.md` — contrato versionado; instalação em VM ainda
  externa (`infra/systemd/README.md:5`)

## Runbook — `project_neon_budget.py`

Script offline para projetar consumo Neon CU-h e armazenamento sem acesso
a rede, banco de dados ou ambiente externo.

### Flags

| Flag | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `--active-hours-per-run DEC` | Decimal ≥ 0 | sim | Horas ativas por execução do pipeline |
| `--runs-per-month INT` | int ≥ 0 | sim | Execuções por mês; zero é válido |
| `--cu DEC` | Decimal > 0 | sim | Tamanho do Compute Unit (ex.: 0.25) |
| `--additional-cu-hours DEC` | Decimal ≥ 0 | não | CU-h adicionais fora das janelas (padrão 0) |
| `--current-storage-bytes INT` | int ≥ 0 | par | Bytes atuais de storage; requer `--monthly-growth-bytes` |
| `--monthly-growth-bytes INT` | int ≥ 0 | par | Crescimento mensal em bytes; requer `--current-storage-bytes` |
| `--output PATH` | Path | não | Grava JSON em arquivo em vez de stdout |

### Unidades e suposições

- `active_hours_per_run` deve incluir os tails de startup e suspend — não
  adicionar padding separadamente.
- A janela contada (scheduled) é: `active_hours_per_run × runs_per_month × cu`.
- `additional_cu_hours` cobre demanda incremental fora das janelas (ex.: cold
  start extra, admin queries), padrão zero.
- Limite de compute: `total_cu_hours <= 80` CU-h/mês (reserva abaixo da quota
  nominal de 100 CU-h; headroom é margem operacional).
- Limite de storage: `projected_bytes < 1 000 000 000` bytes (1 GB decimal).
- Par de storage ausente → `storage_status: "not_projected"`,
  `storage_projected_bytes: null`; nunca fabricado como "pass".

### Códigos de saída

| Código | Significado |
| --- | --- |
| 0 | Sem violação de orçamento |
| 1 | Ao menos uma violação (compute ou storage) |
| 2 | Argumentos inválidos ou falha ao escrever `--output` |

### Exemplos

Projeção de 2 execuções/dia durante 31 dias (baixo consumo):

```bash
python scripts/project_neon_budget.py \
    --active-hours-per-run 2 \
    --runs-per-month 31 \
    --cu 0.25
# total_cu_hours: 15.50, compute_status: "pass", exit 0
```

Horizonte de 744 h (24 h/dia × 31 dias × 0,25 CU = 186 CU-h → inaceitável):

```bash
python scripts/project_neon_budget.py \
    --active-hours-per-run 24 \
    --runs-per-month 31 \
    --cu 0.25
# total_cu_hours: 186.00, compute_status: "fail", exit 1
```

Com projeção de storage:

```bash
python scripts/project_neon_budget.py \
    --active-hours-per-run 2 \
    --runs-per-month 31 \
    --cu 0.25 \
    --current-storage-bytes 900000000 \
    --monthly-growth-bytes 50000000
# storage_projected_bytes: 950000000, storage_status: "pass"
```
