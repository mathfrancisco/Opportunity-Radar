# Plano de implantação econômica: opções gratuitas e AWS com Terraform

> **Para agentes executores:** o coordenador permanece somente leitura e cada
> mutação pertence a um único executor delimitado. Execute as tarefas com
> checklist (`- [ ]`), uma por vez. Não use `superpowers:subagent-driven-development`
> por padrão; o executor escolhido usa `superpowers:executing-plans`.

**Objetivo:** começar com um piloto gratuito, sem prometer execução contínua,
e manter AWS pessoal 24x7 como fallback apenas se o piloto não atingir os gates
de durabilidade, agendamento, custo e recuperação.

**Leitura do plano:** a rota preferida está em **Piloto gratuito**; as decisões
de AWS, Terraform, RAM, storage, testes e saída ficam nas seções específicas.
Nada abaixo autoriza criar conta, recurso, credencial, imagem ou deploy.

## Sumário

1. [Decisão, escopo e estado](#resumo-de-decisão-e-limites).
2. [Piloto gratuito e elegibilidade de provedores](#piloto-gratuito-arquitetura-recomendada-e-limites-reais).
3. [AWS como fallback 24x7](#referências-de-preço-e-produto).
4. [Fases, arquivos e critérios mensuráveis](#fases-e-critérios-de-interrupção).
5. [Tarefas, testes, rollback e saída](#tarefa-1-registrar-pré-requisitos-e-orçamento-antes-da-infraestrutura).

- Para Lightsail, declarar portas públicas com `ipv6_cidrs = []` explicitamente;
  CIDRs IPv4 não fecham regras IPv6. Após `apply` futuro, consultar estado de
  portas no console ou `get-instance-port-states` e bloquear promoção se houver
  qualquer regra IPv6 aberta ou SSH IPv4 diferente do `/32` aprovado. A regra vem
  da [documentação de firewall Lightsail](https://docs.aws.amazon.com/lightsail/latest/userguide/understanding-firewall-and-port-mappings-in-amazon-lightsail.html).

## Requisitos transversais antes de qualquer implementação

- **Somente alternativa Render:** a API atual tem CMD runtime `uvicorn opportunity_radar.presentation.http.app:create_app
  --factory --host 0.0.0.0 --port 8000`. Para Render, o comando futuro precisa
  expandir a porta dinamicamente por shell, por exemplo `sh -c 'exec uvicorn
  opportunity_radar.presentation.http.app:create_app --factory --host 0.0.0.0
  --port "$PORT"'`, ou usar porta 8000 somente após confirmar autodetecção do
  Render. JSON-form `CMD` não expande `$PORT` sozinho.
- Antes de promover API pública, testar DNS/TLS, versão Python, `psycopg` e demais
  dependências nativas no runtime final, migrations isoladas e health/readiness.
- **Somente fallback AWS:** o principal IAM do backend Terraform é distinto do principal de backup. Para
  state, conceder `ListBucket` no prefixo e `GetObject`/`PutObject` para state e
  `GetObject`/`PutObject`/`DeleteObject` no objeto exato `<key>.tflock` usado por
  `use_lockfile`; não reutilizar a política backup sem delete para esse lock.
- Testar `init`, `plan`, lock concorrente e desbloqueio controlado com state de
  ensaio. A política de backup continua sem `DeleteObject` e limitada ao prefixo
  de dados. Ver [permissões do backend S3](https://developer.hashicorp.com/terraform/language/backend/s3#s3-bucket-permissions).


## Rota preferida futura: Pages, Oracle, Neon e Clerk

Esta é uma decisão futura, não uma instrução para criar contas. A configuração,
os gates, o rollback e os arquivos da rota selecionada estão no
[plano Cloudflare/Oracle/Neon/Clerk](../../53-plano-hospedagem-cloudflare-oracle-neon-clerk.md).
Cloudflare Pages entrega a SPA, Oracle Always Free hospeda API e jobs finitos,
Neon armazena PostgreSQL e Clerk emite identidade. AWS Lightsail permanece o
fallback pago 24x7; Render é uma alternativa de catálogo, não o caminho ativo.

Antes de expor a rota: fixar commit e domínio próprio; construir `apps/web` com
`npm ci` e `npm run build`; configurar somente a URL pública da API em
`VITE_API_BASE_URL` e a chave pública `VITE_CLERK_PUBLISHABLE_KEY`; manter
segredos no servidor; validar JWT Clerk por issuer, audience quando configurada,
`azp`, expiração e allowlist de `sub` owner; e testar Alembic, SSL, `pgvector`, `unaccent`, backup e
restore isolados no Neon. A API deve rejeitar toda rota privada sem token mesmo
pela URL direta. Jobs devem ser finitos, com claim/checkpoint, sem daemon ou
keepalive.


## Critérios transversais de seleção e validação

### Limites de custo e compatibilidade

- Cloudflare Workers pode executar FastAPI como ASGI Python. É uma adaptação
  experimental, não um container Docker nem daemon: Free limita a 100 mil
  requests/dia, 10 ms CPU, 128 MB e seis requests externos. Exigir POC de
  Pyodide, `psycopg` e dependências nativas antes de tratá-lo como API candidata.
- GCE e2-micro não é VM estritamente zero com IPv4 público: o endereço custa
  US$0,005/h depois de uma hora/mês, aproximadamente US$3,65 em 730 h. Sem IP,
  NAT/proxy para saída pode também cobrar. Não recomendar GCE como zero estrito.
- Koyeb exige checagem prévia de adesão: a FAQ descreve autorização de US$29 que
  pode permanecer 7--21 dias, plano Pro padrão e cobrança pro-rata imediata;
  Starter/PAYG precisa confirmação antes do cadastro e não há spending limit.
- Supabase Free entra apenas como banco alternativo: 500 MB, 500 MB RAM, 5 GB de
  egress, sem backup automático e pausa por baixa atividade. Testar endpoint,
  pool, extensões e restauração antes de adotá-lo.
- Railway tem trial de US$5 por 30 dias e depois crédito Free de US$1/mês; não é
  arquitetura full-stack always-on gratuita.
- Netlify Free usa créditos compartilhados de produção/deploy, egress, requests
  e compute. Não usar número de builds para estimar essa modalidade, nem assumir
  Netlify Postgres gratuito independente após o período exibido na documentação.

### Métricas por tipo de armazenamento

- Banco gerenciado: comparar somente dados de banco, índices, WAL/provider e
  storage reportado contra a quota do banco. Não somar imagens Docker, dumps do
  host e exports locais a uma quota gerenciada de 1 GB ou 500 MB.
- Host/VM: medir separadamente `df`, volumes PostgreSQL, WAL, dumps, exports,
  imagens e logs. Esses componentes compõem o disco físico da VM e precisam de
  alertas 70%/80%.
- Backup externo: registrar bytes de objeto, versões não correntes e multipart
  incompleto. A soma depende do lifecycle e não equivale a tamanho do banco.
- Memória: tratar 103/118/6/963 MB como baseline de baixa atividade; dimensionar
  com pico medido de PostgreSQL, API, worker, Nginx e SO, nunca com média isolada.

### Matriz mínima de testes antes da escolha

| Objetivo | Procedimento futuro | Resultado/gate | Evidência | Rollback |
| --- | --- | --- | --- | --- |
| Web estática | build e abrir deep link | SPA faz fallback; assets carregam | URL, commit e captura sanitizada | artefato anterior |
| API pública | URL direta sem/com token e preflight | privado nega sem token; CORS não vira auth | status/latência sem segredo | retirar exposição |
| Cold start | primeira chamada após sleep e série warm | p95 cold e warm separados | horário, amostra e release | manter CLI/local |
| Banco | Alembic, extensões, CRUD e SSL em projeto isolado | schema/restauração passam | versão, schema e contagens | descartar projeto teste |
| Batch | deadline, interrupção e rerun | claim/checkpoint; sem fechamento parcial | `SourceRun`, quota e fim | desabilitar schedule |
| Backup | dump, SHA, destino externo e restore `_test` | manifesto e RTO medido | hash, tempo e contagens | não promover |
| VM | reboot e carga medida | sem OOM, disco/memória dentro gates | host/Docker/PG metrics | manter arquitetura anterior |

Antes de teste que escreva banco, usar URL e banco `_test` exclusivos, dados
descartáveis, volumes isolados e flags efetivamente entregues ao container.

### Retenção de backup e RPO mensurável

- Com backup diário, o gate inicial é idade do último dump bom de no máximo 24 h,
  mais alerta de falha. Isso é alvo operacional, não garantia de RPO inferior a
  24 h: duração, falha e janela de corte precisam ser medidos.
- Se o requisito virar RPO estritamente menor que 24 h, comparar intervalo de 12 h
  e o custo/volume adicional antes de mudar timer e retenção.
- Promover explicitamente uma cópia semanal dentre os dumps válidos; não inferir
  semanal apenas pela idade. Reter sete diários e quatro semanais, documentando
  prefixos e etiquetas no manifesto.
- Lifecycle precisa expirar versões não correntes, abortar multipart incompleto e
  nunca expirar a cópia atual protegida que foi restaurada com sucesso. Medir
  versões antes de aceitar TTL de 45 dias, para não crescer indefinidamente.


**Arquitetura AWS (fallback):** criar uma Lightsail em `us-east-1` por padrão, com valor de
região variável, IP estático anexado, Docker Compose e serviços locais. O
Terraform cria a infraestrutura e o `userdata` prepara somente Docker, Compose,
agente de backups e timers idempotentes; lançamento da aplicação usa imagens
fixadas em etapa separada.

**Tecnologias AWS (fallback):** Terraform >= 1.10, provider AWS fixado no lockfile, AWS CLI,
Ubuntu Linux, Lightsail, S3, IAM mínimo, Docker Compose, PostgreSQL 17 Alpine
com pgvector, Nginx, systemd e GitHub Container Registry.

**Especificação:** solicitação de implantação econômica de 6 de outubro de
2026; preservar as garantias operacionais em
[README do roadmap de coleta](../../51-roadmap-coleta-confiavel/README.md) e
as instruções deste plano.

## Sequência de decisões

| Decisão | Entrada obrigatória | Saída que permite avançar | Saída que encerra a opção |
| --- | --- | --- | --- |
| Escolher piloto | política de uso, autenticação, custo e recuperação | arquitetura pública com gates mensuráveis | serviço só trial, cobrança automática ou incompatibilidade PG |
| Escolher banco | teste Alembic isolado, extensões, SSL, quota e restore | schema e restore comprovados | extensão/privilégio indisponível ou quota insuficiente |
| Escolher batch | duração, frequência, quota e idempotência | job finito com checkpoint/claim | daemon, keepalive ou sobreposição |
| Aceitar produção | backup externo, smoke, cold/warm e observação | 24 h sem gate violado | dados sem restauração, job perdido ou acesso não autenticado |
| Escolher AWS | Billing, Free Plan, preço/região e plano Terraform | `plan` revisado e recuperação provada | crédito/custo não aprovado ou plano destrutivo |

Cada linha é futura. Uma aprovação de opção não cria conta, recurso, imagem,
configuração, credencial nem deploy.

## Resumo de decisão e limites

- A decisão preferida é um piloto público separado: Cloudflare Pages para React
  estático, Oracle Always Free para API e jobs finitos, Neon Free para PostgreSQL
  e Clerk para identidade. Render Free permanece alternativa de API; GitHub
  Actions agendado só entra após validar política, consumo e idempotência.
- Nenhum provedor gratuito gerenciado deste desenho promete worker permanente.
  Não colocar APScheduler em serviço web que dorme, nem usar keepalive para
  burlar suspensão ou limites do provedor.
- A AWS Lightsail descrita abaixo é fallback explícito para operação 24x7,
  Compose em um host e worker contínuo; não é pré-requisito para o piloto.
- O destino AWS é uso pessoal 24x7, não serviço público multiusuário.
- A instância candidata é Lightsail Linux Ubuntu, 2 GiB RAM, 2 vCPU, 60 GB SSD,
  IPv4, plano anunciado a US$12/mês em `us-east-1`; confirmar preço e região
  no console antes de `apply`.
- Anexar o Static IP à instância. O IP desanexado pode cobrar; confirmar a regra
  vigente no console, sem supor gratuidade fora da associação.
- A hipótese inicial considera somente o saldo remanescente dos US$100 de
  crédito inicial informado pelo usuário, confirmado no Billing. Qualquer até
  US$100 adicional para atividades elegíveis é opcional, não é capacidade-base
  e fica fora do orçamento deste plano.
- A estimativa de US$13–15/mês e US$78–90 em seis meses exclui impostos,
  tráfego excedente, snapshots, e Groq, Tavily ou qualquer serviço externo.
  É estimativa, não garantia de cobrança.
- O plano Free Plan encerra no primeiro evento entre seis meses desde a criação
  da conta/plano e o esgotamento dos créditos. Conferir saldo, data e serviços
  elegíveis em **Billing** antes de cada marco; não inferir uma data aqui.
- Parar a Lightsail não encerra sua cobrança. Só remover depois de backup
  validado; remoção também precisa verificar IP, snapshots, versões S3 e itens
  remanescentes.
- O plano está somente revisado, não aplicado. Nenhuma credencial, estado,
  `tfvars`, `userdata`, saída, arquivo de plano ou log com segredo entra no Git.

## Estado observado e incertezas a resolver

- O Compose atual expõe API em `127.0.0.1:8000` e frontend em
  `127.0.0.1:3000`; PostgreSQL fica apenas na rede Docker. Ele ainda cria a API
  com alvo `test`, portanto produção precisa de override explícito.
- A imagem PostgreSQL local já parte de Alpine e compila pgvector. Não trocar
  cegamente para a imagem oficial Debian: collation sob volume existente pode
  invalidar índices.
- O pipeline publica imagens `api`, `worker` e `frontend` em matriz; ele não
  publica hoje uma imagem PostgreSQL customizada. A tarefa de infraestrutura
  precisa preservar Alpine, versão e extensões na nova imagem antes da migração.
- Medições de baixa atividade registradas: worker 103 MB, API 118 MB, frontend
  6 MB e PostgreSQL 963 MB, total aproximado 1,2 GiB. Não são pico, nem prova de
  dimensionamento para 2 GiB.
- `create_engine` usa pools padrão e não expõe parâmetros de pool por ambiente.
  O plano propõe teste de `pool_size=2`, `max_overflow=1` ou orçamento de até 30
  conexões PostgreSQL, sem alterar isso até haver medição concorrente.
- `PAYLOAD_RETENTION_DAYS=365` remove somente payload terminal normalizado.
  `WORKER_ASSESSMENT_RETENTION_ENABLED=false`; o padrão de sete dias só vale se
  houver opt-in. `AI_CALL_RECORD_RETENTION_DAYS=30` já é purgado em rotina diária
  do worker, devendo ter execução comprovada.
- `TAVILY_EXTRACT_CACHE_TTL_SECONDS=2592000` torna cache expirado um miss, mas
  a inspeção não encontrou limpeza física das linhas expiradas. Reduzir TTL
  isoladamente não libera disco e pode aumentar custo da API.
- A migração 0024 usa tabela pgvector e índice HNSW. Backup e migração mantêm
  extensão e índices; remoção de pgvector só pode ser considerada após perfil e
  testes, pois a migração a requer mesmo que matching em runtime não a consulte.

## Restrições do fallback AWS

- Trabalhar inicialmente em `us-east-1`, mas declarar `aws_region` variável e
  bloquear `apply` quando preço, disponibilidade ou elegibilidade divergir.
- Usar perfil AWS por ambiente. Rodar `aws sts get-caller-identity` apenas para
  evidência local de identidade e nunca registrar credenciais no resultado.
- Proteger conta root com MFA. Criar usuário ou papel IAM mínimo para operação;
  não usar root, AWS Organizations, Control Tower, IAM Identity Center via
  Organizations, nem migração automática para plano pago.
- Validar ao vivo saldo, data de expiração e serviços permitidos no Free Plan,
  versões de AWS CLI, Terraform e Docker antes de `apply`.
- Criar dois buckets privados: um de estado Terraform e outro de dados de backup.
  Usar SSE-S3, versionamento e bloqueio de acesso público; evitar KMS gerenciado
  pelo cliente por custo adicional.
- Usar backend S3 com `use_lockfile = true`; requer Terraform >= 1.10. Não
  introduzir DynamoDB para lock.
- Não pôr lifecycle que expire a versão atual do estado. O state contém dados
  sensíveis mesmo se a saída Terraform estiver marcada `sensitive`.
- Aplicar `prevent_destroy` na instância e nos buckets de dados e estado. Uma
  substituição, delete ou `-replace` exige recuperação ensaiada e aprovação de
  mudança; arquivos de plano são sensíveis e ficam ignorados.
- Lightsail não deve ser tratada como instância EC2 com instance profile sem
  prova de suporte. Para S3, iniciar com IAM de backup de escopo mínimo.
- Criar a access key de backup fora do Terraform e fora do state, com modo 0600
  no host, fora do diretório da aplicação e com rotação registrada. Se uma opção
  short-lived for comprovadamente suportada, substituí-la em mudança posterior.
- A política de backup permite apenas `s3:PutObject`, `s3:GetObject` e
  `s3:ListBucket` no bucket/prefixo necessário. Omitir `DeleteObject`; retenção
  é aplicada pelo lifecycle do bucket.
- Não expor PostgreSQL, API ou frontend diretamente. Liberar SSH apenas do CIDR
  administrativo `/32`; manter IPv6 fechado até teste explícito.
- O acesso inicial usa `ssh -N -L 3000:127.0.0.1:3000 usuario@host`, onde
  `usuario` é o usuário Ubuntu provisionado. Nginx pode servir frontend e
  encaminhar `/api` localmente, sem publicar a API ao exterior.
- A variante AWS privada usa tunnel SSH inicialmente. No piloto público,
  autenticação de backend e TLS API–banco são pré-requisitos antes do deploy;
  TLS/autenticação pública para a variante AWS continua fase separada e aprovada.
- Construir imagens fora da VM, em CI ou máquina local isolada, por digest ou
  hash imutável. Não instalar `npm`, dependências de teste ou cadeia de build na
  VM de 2 GiB.

## Piloto gratuito: arquitetura recomendada e limites reais

O piloto separa web, API, banco e jobs para reduzir custo inicial. A separação
não substitui os gates de backup, autenticação e recuperação deste plano.

| Componente | Proposta inicial | Limite que muda o desenho | Gate antes de aceitar |
| --- | --- | --- | --- |
| Frontend | Cloudflare Pages | SPA estática; Functions não hospedam o FastAPI/worker atual | build, fallback SPA e API pública autenticada |
| API e jobs | Oracle Always Free ARM | capacidade regional incerta; 2 OCPU/12 GB como referência da franquia | Compose, backup externo, worker e reboot medidos |
| Banco | Neon Free | 1 GB e 100 CU-h por projeto/mês | schema/extensões, disco, conexões e dashboard confirmados |
| Identidade | Clerk | plano, limites e contrato JWT precisam ser confirmados | API valida issuer/audience e rotas privadas |
| Jobs alternativos | CLI local finito | computador local precisa estar disponível | execução, claims e backup observados |
| Jobs opcionais | GitHub Actions finito | agenda pode atrasar/perder; não é worker contínuo | política, minutos e reexecução idempotente |
| Fallback 24x7 | AWS Lightsail | custo estimado, crédito e expiração variam | tarefas AWS e Billing aprovados |

- Render Free tem disco efêmero, 750 horas compartilhadas por workspace/mês e
  não oferece tipo Free para worker ou cron. Ele suspende após 15 minutos de
  inatividade e pode precisar de aproximadamente um minuto para acordar. Conferir
  também egress/banda no dashboard: excedente impede promessa de custo zero.
- Render PostgreSQL Free é de 1 GB, expira após 30 dias e apaga depois de 14
  dias de graça. Portanto não é banco permanente recomendado para este caso.
- Cloudflare Pages Free tem 500 builds/mês, 20.000 arquivos e 25 MiB por arquivo;
  o React estático cabe conceitualmente, mas Functions não substituem o container
  FastAPI ou o worker existente.
- Neon anunciou em 2 de outubro de 2026 100 projetos, cada um com 100 CU-h/mês,
  1 GB, dez branches e seis horas de instant restore. Confirmar egress, limites
  atuais e ativação no dashboard antes de provisionar; object storage de 5 GB no
  mesmo projeto não substitui backup independente da falha do projeto.
- Exemplo de orçamento de compute, não mínimo garantido: 0,25 CU por 24 h/dia
  por 31 dias equivale a 186 CU-h, acima de 100 CU-h. Isso explica por que banco
  sempre ativo requer medição/hibernação, não uma promessa de gratuidade.
- Cloudflare R2 pode ser avaliado mais tarde para backup: franquia Standard de
  10 GB-mês, 1 milhão de operações classe A, 10 milhões classe B e sem cobrança
  de egress. Overages cobram e requisitos de cartão/ativação variam; a linha
  zero-custo começa com backup criptografado local/offline do proprietário.

### Segurança e conectividade do piloto público

- Definir `VITE_API_BASE_URL` no build estático para a URL HTTPS da API Oracle.
  O arquivo existente `apps/web/src/lib/api.ts` já consome a variável; o backend
  atual atende rotas na raiz, não sob proxy `/api` do Pages.
- Atualizar o Dockerfile do frontend, ou construir diretamente `apps/web` no
  Pages, para receber a variável no build. Usar `npm ci` e `npm run build` na
  raiz do app web e configurar fallback SPA para deep links.
- Nunca colocar token, segredo de banco ou chave de serviço em `VITE_*`.
- Exigir autenticação no backend em toda rota privada. CORS, URL oculta, frontend
  Pages e Cloudflare Access não protegem uma API Oracle cujo URL direto esteja
  acessível.
- Usar TLS na conexão API–PostgreSQL. Testar pooling, opções de sessão e migração
  contra o endpoint real, não só contra Docker local.
- Supabase é alternativa de banco, não escolha padrão deste piloto: Free declara
  500 MB banco, 500 MB RAM, 5 GB egress, 1 GB file storage, dois projetos ativos
  e sem backup automático; projeto de baixa atividade pausa após sete dias.
- Se Supabase for avaliado, o endpoint direto Free é IPv6-only; para IPv4 há
  session pooler na porta 5432. Não trocar cegamente pelo transaction pooler 6543
  porque a aplicação pode exigir estado/opções de sessão.
- Backup/restauração Supabase deve ensaiar o endpoint escolhido. CLI suporta dump
  pelo session pooler por padrão em IPv4, mas consistência de export com múltiplas
  conexões requer validação do script e snapshot real.

### Agendamento finito, não daemon disfarçado

- Hoje somente `scripts/collect.py` é CLI de produção finita: aceita
  `--source-id`, `--source-type`, `--keywords`, `--mode`, `--max-items` e
  `--concurrency` padrão 1. `make collect` adiciona `--build` e não serve como
  batch gratuito.
- Normalização, avaliação e análise vivem em funções/agendador de `worker.py`.
  `scripts/eval_analysis.py` é benchmark e não substitui pipeline produtivo.
- Criar, antes de usar Actions, `scripts/run_pipeline_once.py`: um processo sem
  daemon, com passes limitados, deadline, quotas, logs sanitizados e saída clara.
- O entrypoint precisa encadear coleta, normalização, avaliação, análise e
  retenção de forma finita; ele deve preservar claims, idempotência, backoff e a
  regra de que execução parcial nunca fecha ausências de fonte.
- Não manter daemon paralelo ao job finito Oracle nem usar keepalive; cada execução
  deve terminar, registrar `SourceRun` e respeitar deadline/quota.
- A máquina local executa inicialmente o CLI com cron/Task Scheduler local e
  registra início, fim, fonte, contagens, quota e último sucesso.
- GitHub Actions pode virar alternativa condicional com duas execuções diárias:
  60 execuções × no máximo 10 minutos = 600 minutos/mês, antes de CI, builds,
  retries, restore drills e backups. Medir, não reservar como cota garantida.
- GitHub declara para repositórios privados Free 2.000 minutos/mês e 500 MB de
  artefatos compartilhados; não tornar repositório privado público para obter
  quota. Agendas podem atrasar/perder em horário ocupado, não têm SLA e podem
  ser desativadas após 60 dias de inatividade em repositório público.
- Se Actions for permitido pela política e uso do projeto, usar `concurrency`,
  deadline e reexecução segura. Isso não substitui claims no banco, pois reruns
  e falhas podem ocorrer.

### Aceitação de banco hospedado e migração

- Antes de migrar, executar em projeto/banco isolado a cadeia Alembic completa,
  incluindo schemas `profile`, `company_radar`, `acquisition`, `opportunities`,
  `matching`, `crm` e `platform`, e migrations 0024 pgvector e 0028 unaccent.
- Confirmar que o provedor habilita extensões, schema, privilégio e conexão SSL
  necessários. Não supor que um PostgreSQL hospedado permita `CREATE EXTENSION`.
- Testar crescimento de fontes e dados: sinalizar em 70% e bloquear decisão em
  80% da quota real (Neon 1 GB, Supabase 500 MB). Só transformar isso em bloqueio
  de ingestão com budget guard novo, testado e aprovado; nunca fechar ausências
  de fonte por execução parcial.
- O guard atual exige banco com sufixo `_test`, mas um banco hospedado pode não
  permitir criar scratch database. Adaptar o ensaio para clone local `_test` ou
  projeto separado suportado pelo provedor; nunca contornar o guard em produção.
- `backup.py` usa `pg_dump` custom com `--no-owner --no-privileges`, apropriado
  à portabilidade. `restore_check.py` conecta ao banco de manutenção e tenta
  DROP/CREATE do scratch; não prometer que funciona em provedor hospedado.
- Restaurar sempre em ambiente isolado, medir tempo, comparar manifesto/SHA,
  Alembic, extensões e contagens, e só então aceitar o banco como origem.

### Gate pós-deploy específico do piloto gratuito

- [ ] Rejeitar `GET` e escrita sem credencial Clerk válida na URL direta Oracle para toda rota
  privada; verificar que CORS aceita a origem Pages e preflight, sem tratá-lo como
  mecanismo de autenticação.
- [ ] Abrir deep link da SPA e confirmar fallback Pages; chamar readiness e health
  pela API Oracle no domínio próprio, com TLS válido.
- [ ] Medir p95 de API e reconexão Neon após reinício controlado; registrar uso de
  CPU/RAM/disco Oracle e não aplicar limites Lightsail sem medição.
- [ ] Conferir no painel CPU/RAM/disco Oracle e storage/compute Neon; bloquear a
  decisão de ampliar jobs ao atingir 80 CU-h Neon no mês, até reavaliar quota,
  custo e frequência reais.
- [ ] Verificar `SourceRun`/checkpoint real de cada batch, detectar batch perdido
  ou falho, e repetir sem sobreposição por claims/idempotência.
- [ ] Confirmar que exportações/downloads não dependem de disco transitório da VM;
  reter backup fora do provedor e concluir restore drill isolado antes de aceitar
  a variante gratuita.

### Alternativas que não são a recomendação inicial

- Koyeb Free oferece uma instância de 512 MB, 0,1 CPU e 2 GB SSD por organização,
  sem worker ou volumes, e pode dormir depois de uma hora. Não sustenta o worker
  atual. Seu [banco Free](https://www.koyeb.com/docs/databases) tem cinco
  compute-hours/mês, logo não é banco permanente.
- Vercel Hobby Cron pode executar uma vez por dia, com horário impreciso. Hobby é
  pessoal/não comercial e as diretrizes excluem scrapers; usar Vercel, se houver,
  apenas para frontend, nunca para coleta ou função de collection.
- Railway não é base gratuita contínua: o trial atual dá US$5 por 30 dias e depois
  o crédito Free é US$1/mês. Não orçar o projeto inteiro como always-on gratuito.
- Oracle Always Free pode preservar Compose e worker contínuo, mas a referência
  atual cita ARM com 2 OCPUs e 12 GB, não o número histórico de 4/24. Capacidade
  na região inicial pode faltar e recursos ociosos podem ser recuperados após
  sete dias; não prometer disponibilidade/durabilidade.
- Se Oracle avançar, criar raiz Terraform OCI separada, multi-provider e sem
  dependência do módulo AWS. Primeiro validar quota da conta e multiarch ARM de
  PostgreSQL customizado, API, frontend e worker; backups ficam fora da VM.
- Para piloto gratuito, console primeiro é aceitável para confirmar capacidades
  reais. Codificar Terraform/provider só após confirmar que APIs e features não
  exigem plano pago.

### Catálogo de provedores: classificação antes de criar conta

Uma franquia com overage cobrável não é “grátis 24x7”. A classificação abaixo
serve para descartar cedo opções cujo fim de trial, plano, arquitetura ou custo
contradiz o objetivo. Ela precisa ser revalidada no console e nos termos no dia
de provisionamento.

| Serviço/opção | Classe | Capacidade publicada relevante | Uso possível neste plano | Gate ou motivo de rejeição |
| --- | --- | --- | --- | --- |
| Aiven PostgreSQL Free | recorrente com limite rígido | 1 CPU, 1 GB RAM/storage, 20 conexões, sem cartão | banco candidato | Alembic, PG17, vector, unaccent e backup/restore isolados precisam passar |
| Neon Free | recorrente com limite rígido | 1 GB, 100 CU-h/projeto/mês, 10 branches, 6 h restore | banco candidato | compute não suporta atividade contínua sem orçamento; verificar dashboard |
| Render Free | recorrente, suspenso/limites | 512 MB, 0,1 CPU, disco efêmero e sleep | API HTTP de piloto | cold start, egress e sem worker/cron Free |
| Cloudflare Pages | recorrente com limite rígido | estático, 500 builds/mês | frontend candidato | build, SPA fallback e API autenticada |
| Firebase Hosting Spark | recorrente com limite rígido | 10 GB storage, 360 MB/dia, SSL | frontend candidato | somente estático; App Hosting pode exigir Blaze |
| Azure Static Web Apps Free | recorrente com limite rígido | 100 GB/mês, 250 MB/env, 500 MB total | frontend candidato | não usar overage para manter serviço; API/banco separados |
| GitHub Pages | gratuito com restrição de uso | repo público, 1 GB site, 100 GB/mês soft | demo pública | nunca frontend principal autenticado, dados pessoais ou transações |
| Netlify Free | franquia com hard cap compartilhado | 300 créditos para deploys de produção, egress, requests e compute | frontend experimental | custo compartilhado e bloqueio após créditos; banco não é gratuito assumido |
| Cloud Run Jobs | franquia seguida de cobrança | 240k vCPU-s e 450k GiB-s compartilhados | batch finito candidato | billing, registry/build/egress e deadline idempotente |
| Azure Container Apps Jobs | franquia seguida de cobrança | 180k vCPU-s, 360k GiB-s, 2M requests | batch finito candidato | subscription/billing, quota e custo excedente confirmados |
| IBM Code Engine jobs | franquia seguida de cobrança | 100k vCPU-s, 200k GB-s, 100k requests/mês | batch finito candidato | ephemeral 400 MB, registry/egress e timeout real verificados |
| Scaleway Serverless Jobs | franquia seguida de cobrança | 200k vCPU-s, 400k GB-s, AMD64, 10 GB efêmero | batch finito candidato | cartão, imagem AMD64 e custo excedente aprovados |
| Oracle Always Free ARM | recorrente com capacidade incerta | 2 OCPU, 12 GB ARM, 200 GB block total | VM/worker contínuo provisório | cartão, capacidade regional, reclaim por inatividade e multiarch |
| GCE e2-micro | recorrente, com billing e custos adjacentes | 1 GB RAM, 0,25 CPU, 30 GB disk, regiões US | VM de ensaio | IP público e excedentes não são assumidos zero; confirmar Billing |
| Azure PostgreSQL Flexible | trial temporário | B1MS, 32 GB storage/backup, 12 meses | avaliação limitada | não é banco Free recorrente |
| Xata | trial temporário | 14 dias | protótipo descartável | não é armazenamento permanente gratuito |
| CockroachDB | trial temporário/incompatível | US$400 por 30 dias para novas orgs | nenhum padrão | não é PostgreSQL real; extensão/SQL precisam validação separada |
| Fly.io | trial temporário | 2 VM-hours ou sete dias | nenhum padrão | passa a pago após trial |
| Hugging Face Spaces | incompatível para API Docker nova | static é Free; criação Docker/Gradio requer plano pago | demo estática | não anunciar CPU Basic como elegível a nova API |
| PythonAnywhere Free | incompatível para app completo | sem MySQL em novas contas; PG add-on pago | nenhum padrão | banco externo/saída limitados por allowlist |
| Deno Deploy Free | incompatível sem reescrita | runtime JS/TS, 1M requests, 20 GiB egress | nenhum padrão | não é drop-in para FastAPI/worker Python |
| Koyeb Free | incompatível para worker atual | 512 MB, 0,1 CPU, 2 GB SSD, sleep | API experimental | cartão, ausência de volume/worker e banco de 5 h/mês |

### Cinco arquiteturas viáveis, condicionadas e ordenadas

| Ordem | Topologia | Onde roda cada parte | Entrada para começar | Critério de aceitação | Quando migrar/abortar |
| --- | --- | --- | --- | --- | --- |
| 1 | Piloto preferido | Pages + Oracle API/jobs + Neon + Clerk | quota regional, auth, SSL e teste Alembic | Compose, backup externo, JWT e job finito passam | capacidade/reclaim, quota ou restore não atendem |
| 2 | Alternativa de API suspensa | Pages + Render API + Neon/Aiven + Clerk + CLI local | política, auth, SSL e teste Alembic | cold/warm, backup externo e batch local passam | CU-h/armazenamento excedem ou laptop não é confiável |
| 3 | Batch serverless GCP | Pages/Firebase + Render API + Aiven/Neon + Cloud Run Job | billing aprovado e imagem/egress medidos | job finito dentro da franquia e checkpoint idempotente | gasto estimado/excedente ou atraso impede coleta |
| 4 | Batch serverless Azure | Azure Static + Render API + Aiven/Neon + Container Apps Job | subscription/billing e limites reais | job, quota e restore passarem | banco trial ou custo recorrente sem aprovação |
| 5 | VM Always Free provisória | Oracle ARM + Compose completo | quota regional, cartão e imagens multiarch | Compose, backup externo, worker e reboot passam | capacidade ausente, reclaim ou operação exceder evidência |

As arquiteturas 3 e 4 executam jobs finitos e não estabelecem worker contínuo.
A arquitetura 5 preserva o desenho Compose, mas é provisória: não equivale a
SLA, não garante capacidade e não remove a necessidade de backup externo.

### Configuração por arquitetura e critérios mensuráveis

| Aspecto | 1: Oracle API/jobs + Neon | 2: Render + CLI local | 3/4: API + job serverless | 5: Oracle Compose/PG local | AWS fallback |
| --- | --- | --- | --- | --- |
| API | porta 8000 privada atrás de proxy TLS; JWT Clerk | HTTP dorme/cold start; JWT Clerk | job não atende HTTP | Nginx/API loopback em Compose | Nginx/API loopback em Compose |
| Banco | Neon SSL/pool testado; migrations isoladas | Neon/Aiven SSL/pool | Neon/Aiven SSL/pool | PG17 Alpine/pgvector local | PG17 Alpine/pgvector local |
| Coleta | job Oracle finito, deadline/claim | `run_pipeline_once.py` local, limitado | imagem job com deadline/claim | worker contínuo só após medição | worker contínuo só após medição |
| Estado de job | `SourceRun`, claim e checkpoint no Neon | mesmo contrato | mesmo contrato | mesmo contrato | mesmo contrato |
| Backup | OCI + cópia fora da conta; restore isolado | fora de API/banco | fora de job e banco | storage externo + restore isolado | S3 separado + restore isolado |
| Limite de custo | Neon 100 CU-h; meta operacional 80 CU-h | dashboard antes/depois de execução | orçamento por job, build e egress | quota e custo adjacente da conta | US$13–15/mês, crédito e Billing |
| Métrica de aceitação | proxy/TLS, restore e job finito | p95 cold/warm, restore e batch | duração, retries, franquia e restore | RAM/disco/reboot/restore | RAM/disco/reboot/restore |

**Cálculos de dimensionamento a preencher com medidas reais:**

- Compute de banco: `CU-h mensais = CU média × horas ativas por dia × dias`.
  Exemplo: `0,25 × 24 × 31 = 186 CU-h`; ultrapassa a franquia Neon de 100 CU-h.
  Na rota selecionada, 80 CU-h é o gatilho de revisão antes de ampliar jobs.
- Frequência de batch: `minutos/mês = execuções/dia × duração máxima em min × 30`.
  Exemplo: `2 × 10 × 30 = 600 min`, antes de CI, retry, build e backup.
- Espaço Neon: `quota = dados + índices + componentes reportados pelo provedor`;
  comparar somente esses itens contra a quota Neon e registrar 70% como aviso e
  80% como gate. Em Oracle/AWS, medir separadamente `disco host = WAL + dumps +
  exports + imagens + logs`; esses componentes não pertencem à quota Neon.
- Backup: `retenção = 7 × dump diário + 4 × dump semanal + margem de manifesto`.
  Só escolher 45 dias se o tamanho real e S3/armazenamento externo couberem no
  orçamento. Versionamento pode multiplicar bytes.
- RAM da VM (somente arquitetura 5 Oracle Compose/PG local ou AWS): `pico
  observado = PostgreSQL + API + worker + frontend/Nginx + SO`. Aceitar 2 GiB
  somente se o pico observado preservar aproximadamente 400 MB para SO e pelo
  menos 300 MB disponíveis durante carga, sem swap pesado. A rota selecionada
  não hospeda PG/Node local; medir API, jobs, proxy e SO sem prometer capacidade.

### Fontes oficiais adicionais do catálogo

- [Aiven PostgreSQL Free tier](https://aiven.io/docs/products/postgresql/concepts/pg-free-tier)
  e [preços PostgreSQL Aiven](https://aiven.io/pricing/postgresql) sustentam o
  candidato condicionado de 1 CPU/1 GB/20 conexões e seu backup limitado.
- [Google Cloud Free Program](https://cloud.google.com/free/docs/free-cloud-features)
  e [preços Cloud Run](https://cloud.google.com/run/pricing) sustentam a opção
  GCE/Jobs, ainda sujeita a Billing, egress, registry e excedentes.
- [Billing Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/billing)
  e [Azure PostgreSQL Free account](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-deploy-on-azure-free-account)
  sustentam jobs condicionais e o caráter temporário do banco Azure.
- [Limites IBM Code Engine](https://cloud.ibm.com/docs/codeengine?topic=codeengine-limits)
  e [amostra de billing IBM](https://cloud.ibm.com/docs/enterprise-management?topic=enterprise-management-sample)
  sustentam a opção batch, não uma promessa de API contínua.
- [Preços Scaleway Serverless](https://www.scaleway.com/en/pricing/serverless/)
  e [limitações de Jobs](https://www.scaleway.com/en/docs/serverless-jobs/reference-content/jobs-limitations/)
  sustentam o candidato AMD64 condicionado a cartão/custo.
- [Firebase pricing](https://firebase.google.com/pricing),
  [Azure Static Web Apps quotas](https://learn.microsoft.com/en-us/azure/static-web-apps/quotas),
  [Azure Static Web Apps pricing](https://azure.microsoft.com/en-us/pricing/details/app-service/static/)
  e [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
  sustentam opções somente de frontend.
- [Netlify pricing](https://www.netlify.com/pricing/),
  [créditos Netlify](https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/how-credits-work/)
  e [Netlify Database](https://docs.netlify.com/build/data-and-storage/netlify-database/)
  sustentam a rejeição de banco gratuito assumido.
- [Hugging Face Spaces](https://huggingface.co/docs/hub/spaces-overview),
  [sleep de Spaces](https://huggingface.co/docs/hub/spaces-gpus),
  [PythonAnywhere databases](https://help.pythonanywhere.com/pages/KindsOfDatabases),
  [allowlist PythonAnywhere](https://www.pythonanywhere.com/whitelist/),
  [Deno Deploy pricing](https://deno.com/deploy/pricing),
  [Koyeb pricing FAQ](https://www.koyeb.com/docs/faqs/pricing),
  [Xata pricing](https://xata.io/pricing),
  [CockroachDB pricing](https://www.cockroachlabs.com/pricing/) e
  [Fly.io trial](https://docs.fly.io/about/free-trial) sustentam as rejeições.

### Fontes oficiais do piloto gratuito

- [Render Free](https://render.com/docs/free) e
  [planos de compute Render](https://render.com/docs/compute-plans) sustentam os
  limites de sleep, disco, horas, API e ausência de worker/cron Free.
- [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/)
  sustenta os limites de hospedagem estática e build.
- [Neon Free Plan 1 GB por projeto](https://neon.com/blog/neon-free-plan-1-gb-per-project)
  é a fonte atual para 100 CU-h, 1 GB, branches e restore; confirmar no dashboard
  e não usar a publicação anterior de 0,5 GB.
- [Supabase pricing](https://supabase.com/pricing),
  [pausa de projetos Free](https://supabase.com/docs/guides/platform/free-project-pausing),
  [conexão PostgreSQL](https://supabase.com/docs/guides/database/connecting-to-postgres)
  e [backup/restore](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)
  sustentam a avaliação alternativa e seus endpoints.
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
  e [eventos de workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
  sustentam a avaliação condicional de schedule.
- [Koyeb instances](https://www.koyeb.com/docs/reference/instances),
  [Vercel Cron](https://vercel.com/docs/cron-jobs/usage-and-pricing),
  [Vercel Hobby](https://vercel.com/docs/plans/hobby),
  [fair use Vercel](https://vercel.com/docs/limits/fair-use-guidelines),
  [Railway trial](https://docs.railway.com/pricing/free-trial),
  [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
  e [Oracle Free Tier](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm)
  documentam as opções não escolhidas.
- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/) sustenta
  a avaliação opcional de backups, sujeita a billing/ativação e custo excedente.

## Referências de preço e produto

- [Preços do Lightsail](https://aws.amazon.com/lightsail/pricing/) fundamenta a
  conferência do plano e custo por região.
- [Free Tier plans](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html)
  fundamenta a verificação de plano, crédito e expiração no Billing.
- [Perguntas frequentes do AWS Free Tier](https://aws.amazon.com/free/free-tier-faqs/)
  descreve a separação entre créditos e atividades elegíveis.
- [Billing e contas do Lightsail](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-frequently-asked-questions-faq-billing-and-account-management.html)
  fundamenta a checagem de parada, IP e cobrança residual.
- [Recurso `lightsail_instance`](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lightsail_instance)
  e [portas públicas](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lightsail_instance_public_ports)
  definem os recursos a validar contra a versão fixada do provider.
- [Backend S3 do Terraform](https://developer.hashicorp.com/terraform/language/backend/s3)
  documenta `use_lockfile`, versionamento e dados sensíveis no state.
- [Gerenciar budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
  e [filtros de budget](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-create-filters.html)
  sustentam alertas; alerta não bloqueia gasto.

## Fases e critérios de interrupção

| Fase | Prioridade | Saída | Não avançar se |
| --- | --- | --- | --- |
| Descoberta | P0 | preço, crédito, identidade e versões evidenciados | Free Plan ou orçamento não confirmados |
| Base Terraform | P0 | backend e plano revisado sem segredos | plano incluir destruição/substituição |
| Imagens e host | P0 | Compose de produção privado e reversível | imagens não estiverem por digest |
| Migração | P0 | backup, restauração isolada e corte mensuráveis | RPO/RTO não forem atingidos |
| Observação | P0 | 24 h obrigatórias, 72 h reais preferidas | OOM, fila crescente ou backup vencido |
| Otimizações | P1 | redução medida sem perda de retenção | medição ou rollback faltar |
| Saída Free Plan | P0 | backup e remoção guardada | backup/restauração não validados |

## Matriz de recursos e arquivos previstos

| Raiz/arquivo a criar | Responsabilidade | Recursos/resultado |
| --- | --- | --- |
| `infra/terraform/bootstrap/versions.tf` | versões e provider | Terraform >=1.10 e provider fixado |
| `infra/terraform/bootstrap/main.tf` | estado remoto | bucket state, SSE-S3, versões e bloqueio público |
| `infra/terraform/bootstrap/variables.tf` | entradas | região, nomes e tags sem segredo |
| `infra/terraform/bootstrap/outputs.tf` | saídas | nome/ARN não secreto do state |
| `infra/terraform/bootstrap/terraform.tfvars.example` | exemplo | valores fictícios, nunca chave |
| `infra/terraform/lightsail/versions.tf` | versões/backend | lockfile e backend S3 com lockfile |
| `infra/terraform/lightsail/main.tf` | compute/rede/dados | instância, Static IP, attachment, portas, S3, IAM |
| `infra/terraform/lightsail/variables.tf` | contrato | região, CIDR SSH, digest, retenções e limites |
| `infra/terraform/lightsail/outputs.tf` | operação | IP, comando de tunnel e IDs não secretos |
| `infra/terraform/lightsail/terraform.tfvars.example` | exemplo | sem dados reais nem state |
| `infra/terraform/lightsail/userdata.sh.tftpl` | bootstrap | Docker, usuário, diretórios, unit/timer idempotentes |
| `compose.aws.yaml` | runtime futuro | override explícito para imagens e volumes de produção |
| `docker/postgres/Dockerfile.runtime` | banco futuro | Alpine/PG17/pgvector preservados e tag imutável |
| `ops/systemd/opportunity-radar-backup.service` | backup | dump, manifesto, validação, upload e alerta |
| `ops/systemd/opportunity-radar-backup.timer` | agenda | execução diária `Persistent=true` |

Os nomes acima são entregáveis futuros. Eles não existem ainda; exemplos que os
referenciam só devem rodar depois da tarefa correspondente.

## Foco de revisão

1. Saldo Free Plan esgotado ou serviço inelegível deve bloquear `apply`, sem
   assumir upgrade pago nem continuar por crédito anunciado.
2. Plano Terraform que substitui a instância ou destrói bucket deve falhar no
   gate até existir backup restaurado e aprovação explícita.
3. Falha de upload S3 deve preservar os dois últimos backups locais válidos e
   impedir prune local, mesmo quando o dump novo foi criado.
4. Reboot, queda de banco e retry de worker não podem criar duas execuções ou
   duas gravações concorrentes da mesma fonte.
5. Ausência, quota ou bloqueio de Groq/Tavily deve degradar com segurança e
   log sanitizado, sem confundir bloqueio de provedor com credencial inválida.

---

### Tarefa 1: registrar pré-requisitos e orçamento antes da infraestrutura

**Arquivos:**

- Criar: `infra/terraform/README.md`.
- Criar: `infra/terraform/evidence/.gitkeep` e regra de ignore que preserva só
  esse marcador (`evidence/*` e `!evidence/.gitkeep`).
- Não criar: credenciais, relatórios de Billing com dados pessoais ou planos.

**Aceitação:** uma revisão consegue reproduzir a decisão de custo sem encontrar
segredo e identifica a data real de expiração no Billing.

- [ ] Abrir **Billing**, registrar em evidência local privada o saldo, a data de
  início/expiração, os serviços elegíveis, a moeda e o preço Lightsail da região.
- [ ] Confirmar que a instância de 2 GiB/2 vCPU/60 GB/IPv4 existe na região
  escolhida e que o preço observado cabe em US$13–15/mês com margem para S3.
- [ ] Confirmar o saldo remanescente do crédito inicial de US$100 informado,
  excluir até US$100 adicionais da capacidade-base e excluir impostos, serviços
  externos e excedentes do cálculo.
- [ ] Instalar ou verificar versões em uma estação administrativa, sem exibir
  perfis ou chaves: `terraform version`, `aws --version` e `docker compose version`.
- [ ] Executar `aws sts get-caller-identity` somente localmente e registrar
  account/ARN mascarados em evidência privada; não copiar saída para Git.
- [ ] Habilitar MFA da root e criar principal IAM operacional mínimo fora da root.
- [ ] Registrar no README que Organizations, Control Tower, Identity Center via
  Organizations e upgrade automático estão fora do escopo.
- [ ] Configurar alerta de custo de US$13 e US$15 se o serviço suportar o Free
  Plan; se não suportar, documentar passo manual de Budget no console. Alertas
  avisam e não desligam recursos nem interrompem cobrança.

**Testes e evidência:**

- [ ] Executar no diretório raiz: `git check-ignore -v infra/terraform/evidence/*`
  para provar que evidências privadas não entram no commit.
- [ ] Verificar manualmente links AWS desta seção e anexar somente referências,
  data de consulta e decisão ao README versionado.

**Rollback:** nenhum recurso foi criado; revogar o principal IAM recém-criado se
a descoberta reprovar o custo ou a elegibilidade.

### Tarefa 2: criar bootstrap de state remoto seguro e separado

**Arquivos:**

- Criar: `infra/terraform/bootstrap/versions.tf`.
- Criar: `infra/terraform/bootstrap/main.tf`.
- Criar: `infra/terraform/bootstrap/variables.tf`.
- Criar: `infra/terraform/bootstrap/outputs.tf`.
- Criar: `infra/terraform/bootstrap/terraform.tfvars.example`.
- Criar: regras de `.gitignore` específicas para `.tfvars`, `tfplan` e logs locais.

**Interfaces:**

- Produz `terraform_state_bucket`, `terraform_state_key` e região para a raiz
  `lightsail`; os valores reais entram somente no ambiente/arquivo ignorado.
- Consome `aws_region`, prefixo de projeto e tags sem identificadores pessoais.

- [ ] Fixar `required_version = ">= 1.10"` e versão do provider AWS; executar
  `terraform init` para gerar e revisar `.terraform.lock.hcl`.
- [ ] Declarar bucket de state privado, SSE-S3, versionamento e bloqueio público.
- [ ] Declarar lifecycle somente para versões não correntes, com prazo documentado;
  não expirar objeto/versão atual do state.
- [ ] Aplicar `prevent_destroy` ao bucket e revisar que state não recebe outputs
  de chaves, segredo de banco ou conteúdo de `userdata` com segredo.
- [ ] Proibir backend local no uso compartilhado. O bootstrap roda primeiro com
  state local temporário, depois migra o próprio state uma vez para S3, seguindo
  a confirmação interativa do Terraform e registrando o procedimento.
- [ ] Não adicionar DynamoDB. Configurar a raiz Lightsail posteriormente com
  `use_lockfile = true` e testar suporte no Terraform/provider fixados.
- [ ] Criar exemplo de variáveis com nomes de bucket fictícios, sem valores que
  possam ser usados como credencial, conta ou IP real.

**Comandos futuros, executados em `infra/terraform/bootstrap`:**

```powershell
terraform fmt -check
terraform init
terraform validate
terraform plan -out=tfplan
```

- [ ] Revisar `tfplan` fora do Git; o plano não pode criar acesso público nem
  indicar delete/replacement inesperado.
- [ ] Aplicar somente após a revisão humana do plano e salvar evidência privada
  sem segredos. Executar um segundo `terraform plan` e exigir `0 to add, 0 to
  change, 0 to destroy` antes de continuar.

**Rollback:** manter o state remoto e versionado; nunca apagar o bucket para
“recomeçar”. Investigar divergência por versão anterior do state e plano novo.

### Tarefa 3: declarar a Lightsail, rede, dados e guardas Terraform

**Arquivos:**

- Criar: `infra/terraform/lightsail/versions.tf`.
- Criar: `infra/terraform/lightsail/main.tf`.
- Criar: `infra/terraform/lightsail/variables.tf`.
- Criar: `infra/terraform/lightsail/outputs.tf`.
- Criar: `infra/terraform/lightsail/terraform.tfvars.example`.
- Criar: `infra/terraform/lightsail/userdata.sh.tftpl`.

**Interfaces:**

- Consome bucket/key do bootstrap, `aws_region`, bundle Lightsail, CIDR SSH `/32`,
  digest das imagens e configuração não secreta de backup.
- Produz endereço IPv4 anexado, IDs de recursos e instrução de tunnel sem chave.

- [ ] Configurar backend S3 privado com `use_lockfile = true`, bucket/key vindos
  de configuração externa e provider/região explícitos.
- [ ] Declarar `aws_lightsail_instance`, `aws_lightsail_static_ip`, attachment e
  `aws_lightsail_instance_public_ports`; permitir só SSH TCP do `/32` aprovado.
- [ ] Fechar todas as portas IPv6 enquanto a política e teste IPv6 não existirem.
- [ ] Adicionar `prevent_destroy` à instância, buckets de state e backup, e uma
  validação/precondição que exija região e CIDR SSH explícitos.
- [ ] Criar bucket de backups separado do state, privado, SSE-S3, versões e
  lifecycle de diários por sete dias, semanais por quatro semanas e máximo de
  45 dias apenas se a projeção baseada no tamanho real couber no orçamento.
- [ ] Manter retenção de state separada da retenção de dados; não reutilizar
  lifecycle de backup para state.
- [ ] Criar política IAM de backup limitada ao prefixo da instância e às ações
  Put/Get/List. Não declarar `aws_iam_access_key` nem segredo no Terraform.
- [ ] Criar a chave IAM manualmente depois do `apply`, armazená-la com `0600` em
  diretório de host separado de `/app`, e definir data de rotação e revogação.
- [ ] Não pressupor perfil de instância EC2. Pesquisar e provar suporte Lightsail
  antes de trocar por credencial short-lived.
- [ ] Limitar `userdata` a Docker, Compose, usuário Ubuntu, diretórios, serviço
  e timer. Torná-lo idempotente e sem segredo, imagem ou release de aplicação.

**Comandos futuros, executados em `infra/terraform/lightsail`:**

```powershell
terraform fmt -check
terraform init
terraform validate
terraform plan -out=tfplan
```

- [ ] Revisar cada mudança do plano: criação esperada, zero delete, zero replace,
  portas esperadas, buckets privados e nenhuma string de segredo.
- [ ] Aplicar apenas o arquivo revisado: `terraform apply tfplan`.
- [ ] Rodar o segundo plano e registrar zero mudança antes de provisionar a app.

**Rollback:** se o `apply` falhar, não usar `destroy` como correção. Corrigir a
causa, replanejar e, antes de qualquer remoção, restaurar backup de prova quando
houver dados. Static IP só é removido após confirmar que está sem associação.

### Tarefa 4: preparar runtime imutável e Compose de produção privado

**Arquivos:**

- Criar: `compose.aws.yaml`.
- Criar: `docker/postgres/Dockerfile.runtime` se a publicação exigir imagem própria.
- Modificar: `.github/workflows/pipeline.yml`.
- Modificar: `.gitignore`.

**Interfaces:**

- Consome digests imutáveis de API, worker, frontend e PostgreSQL customizado.
- Produz um único host com PostgreSQL na rede Docker, API/frontend apenas loopback
  e Nginx como ponto local de acesso.

- [ ] Publicar a API a partir do estágio explícito `runtime`; publicar worker a
  partir de seu único estágio final e frontend a partir do estágio final Nginx,
  todos por digest/hash. Não passar `--target runtime` ao worker/frontend.
- [ ] Adicionar publicação da imagem PostgreSQL customizada somente se ela
  preservar PG17 Alpine, pgvector e as extensões de migrations. Construir e
  testar antes de apontar qualquer volume existente para ela.
- [ ] Criar `compose.aws.yaml` com `image: ...@sha256:...` em todos os serviços e
  override explícito de `build: !reset null`, se a versão Compose fixada suportar
  a tag. Caso contrário, documentar um Compose standalone sem `build`.
- [ ] Validar a mesclagem com a versão Compose escolhida para garantir que não
  restem `build`, tags `latest` ou alvo `test` herdados silenciosamente.
- [ ] Expor somente `127.0.0.1:3000` no host, manter API em loopback/rede Docker
  e PostgreSQL sem porta host. Nginx encaminha frontend e `/api` internamente.
- [ ] Criar bind mount do host para `data/backups`; o Compose atual só monta
  `local_backups` no worker, portanto a API não pode assumir esse volume.
- [ ] Fazer dump com `docker compose exec` na API, ou helper dedicado com o
  volume e ferramentas PostgreSQL. Credencial S3 fica apenas no host.
- [ ] Configurar log Docker `local` ou `json-file` com `max-size=10m` e
  `max-file=3`; reter exportações por sete dias e no máximo duas releases de
  imagens. Fazer prune seletivo; nunca usar `docker system prune --volumes`.
- [ ] Configurar um Uvicorn sem `--reload`; desligar sugestões com
  `WORKER_SUGGEST_ENABLED=false` inicialmente e não instalar Ollama local.

**Testes futuros:**

```powershell
docker compose -f compose.yaml -f compose.aws.yaml config
docker compose -f compose.yaml -f compose.aws.yaml pull
docker compose -f compose.yaml -f compose.aws.yaml up -d
docker compose -f compose.yaml -f compose.aws.yaml ps
```

- [ ] Exigir que `config` mostre digests, nenhum `build`, portas apenas loopback
  e o volume host de backup corretamente declarado.

**Rollback:** manter o digest da release anterior e rodar o Compose com ele;
reverter somente se a migration for compatível. Fazer backup antes de update e
proibir release que exija downgrade de schema sem caminho escrito e testado.

### Tarefa 5: migrar dados com backup lógico, cutoff e restauração isolada

**Arquivos:**

- Criar: `ops/backup/run-backup.sh`.
- Criar: `ops/backup/verify-manifest.sh`.
- Criar: `ops/systemd/opportunity-radar-backup.service`.
- Criar: `ops/systemd/opportunity-radar-backup.timer`.
- Modificar: `scripts/backup.py` somente se necessário para aceitar flag explícita.

**Interfaces:**

- Consome `DATABASE_URL` somente no container, diretório host de backup e chave
  IAM fora do repositório.
- Produz dump lógico, manifesto com SHA-256, data, tamanho, schema/Alembic e
  resultado de upload verificável.

- [ ] Usar `pg_dump` e `pg_restore` lógicos. Não copiar volume Docker bruto.
- [ ] Fazer backup diário com timer systemd `Persistent=true`; validar dump e
  manifesto SHA-256 antes do upload e registrar falha sanitizada.
- [ ] O `backup.py` já lê `BACKUP_RETENTION_DAYS`, mas o bloco de ambiente atual
  do Compose não o transmite. Durante dump passar `--prune-days 0`, pois o prune
  embutido acontece antes da saída e portanto antes da verificação de upload.
- [ ] Depois de upload validado, executar prune local separado, limitado, que
  mantém ao menos os dois últimos backups válidos. Em falha de upload não rodar
  prune nem apagar a cópia local nova.
- [ ] Agendar S3 com diários sete dias e semanais quatro semanas; ajustar 45 dias
  com tamanho real. Medir bytes de dump, WAL, tabela, índices, exports e backups
  antes de prometer caber em 60 GB.
- [ ] Executar cutoff: parar worker e escritas, aguardar jobs ativos, gerar dump
  final, registrar contagens e retomar somente uma instância de worker. Não
  aceitar duas coletas simultâneas.
- [ ] Incluir no manifesto versões PG, extensões, revisão Alembic, perfis, fontes,
  aplicações e contagens relevantes. Conservar origem e backup até o gate passar.
- [ ] Definir inicialmente idade máxima de 24 h para o último dump bom e meta
  RTO de 30 min. Medir dump/restauração real, não dump pequeno de teste, em
  ambiente `_test` fora da VM operacional; RPO estritamente menor exige intervalo
  menor, custo aprovado e prova de duração/falha.

**Testes futuros:**

```powershell
python scripts/backup.py --output-dir data/backups --label restore-drill
pg_restore --list data/backups/restore-drill.dump
```

- [ ] Restaurar em Docker/projeto isolado e banco com sufixo `_test`, em outra
  máquina ou capacidade separada, nunca lado a lado da produção de 2 GiB.
- [ ] Comparar SHA-256, manifesto, extensões, Alembic, contagens antes/depois e
  tempo total. Uma consulta de contagem em produção pode ser somente leitura.

**Rollback:** restaurar o dump lógico comprovado em ambiente isolado primeiro.
Ao voltar produção, explicar que uma restauração pode perder escritas posteriores
ao cutoff e executar nova verificação de contagens antes de liberar o worker.

### Tarefa 6: medir RAM, armazenamento e retenção antes de otimizar

**Arquivos:**

- Criar: `ops/metrics/capacity-snapshot.sh`.
- Criar: `docs/operations/capacity-baseline.md`.
- Modificar: `compose.aws.yaml` somente após o baseline.

**Interfaces:**

- Consome métricas do host, Docker e PostgreSQL sem logar URLs, tokens ou chaves.
- Produz série temporal com data, release digest, carga conhecida, memória, disco
  e crescimento por categoria.

- [ ] Medir `free`, `vmstat`, `df`, `docker stats`, `docker system df`, tamanho
  de tabelas/índices top 10, WAL, exports e backups antes e depois de cargas.
- [ ] Definir limites de decisão: reserva de SO de aproximadamente 400 MB, pelo
  menos 300 MB disponíveis durante carga, sem swap pesado, disco <70% aviso e
  80% crítico. Esses valores são gates, não promessa de capacidade.
- [ ] Avaliar piloto de `WORKER_EVALUATE_BATCH_SIZE=20` em vez de 50 e
  `WORKER_ANALYZE_BATCH_SIZE=3` em vez de 10; jobs diferentes ainda podem ser
  simultâneos porque cada job APScheduler tem `coalesce/max_instances=1`, sem
  limite global de memória.
- [ ] Medir um worker/API somente e concorrência real. Não afirmar que batches
  menores reduzem RAM sem amostra comparável.
- [ ] Testar candidatos PostgreSQL `shared_buffers=128MB`, `work_mem=4MB`,
  `maintenance_work_mem=64MB`, `max_connections=30` e pool API 2+1 apenas em
  estágio. Preservar cache do engine e `API_STATEMENT_TIMEOUT_MS` em testes de
  concorrência.
- [ ] Considerar swap de 1 GB apenas como emergência; ele não corrige falta de
  capacidade. Não criar swap como evidência de sizing aprovado.
- [ ] Manter autovacuum. `DELETE` libera páginas para reutilização, não devolve
  necessariamente espaço ao SO; não executar `VACUUM FULL` na VM pequena por
  locks e espaço temporário, e nunca apagar WAL manualmente.
- [ ] Só propor compressão de payload, deduplicação de índices ou remoção de
  pgvector depois de perfil de tamanho e testes. Não remover extensão por padrão.

**Testes e evidência:**

- [ ] Anexar baseline de baixa atividade e de carga controlada sem dados pessoais,
  comparando picos, média, disco e latência na mesma release.
- [ ] Recusar alteração de limites se memória disponível ficar abaixo de 300 MB,
  houver OOM ou a fila crescer em três ciclos consecutivos.

**Rollback:** reverter variáveis e configurações PostgreSQL ao baseline medido;
guardar resultados antes de qualquer ajuste seguinte.

### Tarefa 7: aplicar retenção somente após política, backup e medição

**Arquivos:**

- Criar: testes para a limpeza física Tavily em
  `tests/backend/acquisition/test_tavily_extract_cache.py`.
- Modificar: `src/opportunity_radar/acquisition/tavily.py` somente na fase opcional.
- Modificar: `src/opportunity_radar/worker.py` somente se a agenda de limpeza
  Tavily precisar ser conectada.
- Modificar: `.env.example` e `compose.aws.yaml` apenas para flags efetivamente
  transmitidas ao container.

**Interfaces:**

- A limpeza recebe um cutoff UTC, processa lotes idempotentes e preserva cache
  fresco. A API de cache existente continua retornando miss para expirados.

- [ ] Manter `PAYLOAD_RETENTION_DAYS=365` no lançamento inicial. Propor piloto de
  30 dias somente depois de aprovação de política, backup restaurado e evidência
  de que metadados, hashes e `SourceOccurrence` continuam para auditoria.
- [ ] Documentar que o piloto perde capacidade de reprocessar payload expirado.
- [ ] Manter assessment retention desabilitada; se for habilitada, usar dry-run
  representativo, snapshot anterior, proteção de análises current/latest e claims
  AI, e justificar o padrão de sete dias. O prune é irreversível e uma restauração
  pode perder escritas novas.
- [ ] Manter `AI_CALL_RECORD_RETENTION_DAYS=30` e verificar em produção a execução
  diária do worker, não apenas a configuração.
- [ ] Implementar opcionalmente limpeza física Tavily em lotes com cutoff, lock ou
  claim de concorrência e transação curta. Testar zero remoções antes do cutoff,
  remoção de expirados, repetição idempotente e duas execuções concorrentes.
- [ ] Manter TTL de 30 dias inicialmente. Explicar que reduzir TTL sem limpar
  linhas aumenta misses e potencial custo Tavily, sem recuperar armazenamento.
- [ ] Confirmar que flags em `.env.example` passam pelo bloco de ambiente Compose;
  `BACKUP_RETENTION_DAYS` requer flag explícita, não só variável de ambiente.

**Pré-condição e testes futuros:**

- [ ] Criar antes um `.env.aws-test` ignorado, com `POSTGRES_DB` terminado em
  `_test` e `DATABASE_URL` apontando ao PostgreSQL de projeto Compose exclusivo.
  Não montar volumes externos/operacionais e não deixar o Compose carregar `.env`
  normal.
- [ ] Passar `RUN_DATABASE_INTEGRATION=1` e
  `DATABASE_INTEGRATION_ISOLATED=1` explicitamente com `docker compose run -e`,
  ou por overlay futuro que os mapeie para o container; `--env-file` sozinho não
  prova que as flags chegaram ao serviço. Só então testar Tavily, backup e restore.

**Rollback:** desabilitar o job de limpeza novo e restaurar backup isoladamente;
não tentar recriar payload ou cache apagado com dados operacionais.

### Tarefa 8: validar aplicação, operações e recuperação após deploy

**Arquivos:**

- Criar: `docs/operations/aws-post-deploy-checklist.md`.
- Criar: `ops/health/post-deploy-smoke.sh`.
- Modificar: `.github/workflows/pipeline.yml` para manter validações repetíveis.
- Testes existentes: `tests/backend/test_health.py` e
  `tests/backend/test_doctor.py`.

**Interfaces:**

- Consome IP/tunnel e digests da release sem imprimir segredo.
- Produz checklist datado com resultado, URL sanitizada, horário, release e
  decisão de gate.

- [ ] Confirmar instância, chave SSH, regras de firewall, IP anexado, portas IPv4
  e IPv6 fechadas conforme política antes de iniciar a aplicação.
- [ ] Pelo tunnel, verificar `/health/live`, `/health/ready`, `/health`, frontend
  `/` e rotas `/api/health/*` existentes em `routes.py`; distinguir liveness de
  readiness e das consultas interativas.
- [ ] Verificar Alembic atual, extensões PostgreSQL, healthchecks Docker, perfil
  salvo/restaurado, CRUD e uma fonte controlada com coleta, dedupe, normalização,
  matching, busca e jornada de aplicação. Não inserir seeds operacionais.
- [ ] Testar Groq e Tavily reais só com orçamento aprovado e logs sanitizados.
  Distinguir bloqueio/egress/quota de erro de credencial e confirmar degradação
  quando AI faltar.
- [ ] Provar execução por `last_success` do worker e `SourceRun`, não por agenda
  configurada. Testar restart de container e reboot da VM.
- [ ] Testar retry, idempotência e falha de banco somente em ambiente isolado;
  não derrubar banco operacional para o ensaio.
- [ ] Restaurar fora do host operacional e medir RTO contra 30 min. Validar
  manifesto SHA, schema, extensões e contagens sem modificar produção.
- [ ] Observar 24 h reais como mínimo e 72 h preferidas. Não usar
  `scripts/soak_gate.py` na produção: ele grava fixtures e usa relógio simulado.
- [ ] Exigir sem OOM, memória disponível >=300 MB sustentada, sem swap pesado,
  disco sob limiar, crescimento explicado, fila sem aumento por três ciclos e
  logs sem segredo. Para consultas interativas típicas, medir p95 <2 s; health
  tem métrica separada.

**Testes futuros de código, antes do deploy:**

- [ ] Quando houver mudança de código, executar lint/typecheck backend, `npm run
  check` no frontend e os testes focados de health, doctor, backup e restore.
- [ ] Antes de qualquer teste que escreva banco, criar o `.env.aws-test` ignorado
  com URL para PostgreSQL Compose exclusivo e nome terminado em `_test`, sem
  volumes externos. Invocar Compose com `--env-file .env.aws-test`, projeto único
  e as duas flags de isolamento via `run -e` ou overlay que as entregue ao serviço.
- [ ] Executar integração uma vez ao fim somente sob essas pré-condições; nunca
  executar suite contra banco operacional ou confiar só no nome do projeto.

**Rollback:** manter serviço na release anterior por digest se os gates falharem,
desde que schema seja compatível. Caso não seja, parar escrita, escolher backup
validado e executar restauração com a perda de escritas posterior ao cutoff
explicitamente registrada.

### Tarefa 9: executar calendário de saída do Free Plan

**Arquivos:**

- Criar: `docs/operations/free-plan-exit-runbook.md`.
- Modificar: `infra/terraform/README.md` com calendário e guardas de saída.

**Aceitação:** a equipe consegue encerrar ou migrar sem cobrança residual e sem
destruir a única cópia válida dos dados.

- [ ] Criar lembretes para data Free Plan menos 30 dias, menos sete dias e data
  final; em cada marco, reconfirmar Billing, crédito e preço vigente.
- [ ] No marco menos 30, executar backup e restauração isolada. Decidir entre
  encerrar, migrar com orçamento aprovado ou continuar somente após confirmação
  humana de custos pagos.
- [ ] No marco menos sete, congelar alterações de infraestrutura, repetir prova
  de restauração e listar instância, Static IP, snapshots, buckets e versões S3.
- [ ] Para encerrar, parar escrita, fazer backup final, validar manifesto e
  restauração, então executar plano Terraform guardado que mostra somente os
  alvos aprovados. Não usar `force_destroy` sem política separada.
- [ ] Depois da remoção, revisar console para IP desanexado, snapshot, bucket,
  objetos/versionamento e Budget restante. Registrar custo final em evidência
  privada sem conta, chaves ou dados pessoais.

**Rollback:** se backup ou restauração falhar, cancelar remoção, manter recursos
e investigar dentro do orçamento. Não apagar buckets para resolver uma falha de
saída.

## Sequência operacional resumida

1. Concluir Tarefa 1 e bloquear se Billing/Free Plan não confirmar a hipótese.
2. Concluir bootstrap (Tarefa 2) e revisar dois planos sem alterações pendentes.
3. Concluir Tarefas 3 e 4 sem aplicação de release até as imagens terem digest.
4. Ensaiar backup/restauração isolados da Tarefa 5 antes do cutoff.
5. Medir capacidade na Tarefa 6 e aceitar ou recusar a VM com dados reais.
6. Implantar uma única release, executar Tarefa 8 e observar pelo período real.
7. Executar otimizações e retenções somente como fases P1 aprovadas.
8. Preparar e ensaiar a saída da Tarefa 9 antes do prazo Billing.

## Auto-revisão do plano

- [x] Cobre infraestrutura, segurança de acesso, estado, backup, migração,
  observabilidade, custo, RAM/disco, testes pós-deploy e encerramento.
- [x] Separa fatos observados de propostas futuras e não afirma `apply`, deploy,
  backup ou testes como executados.
- [x] Nomeia arquivos, comandos, critérios de aceitação, rollback e isolamento
  obrigatório do banco para cada mudança material.
- [x] Inclui os cinco riscos de revisão e tarefas que os exercitam.
- [x] Exige TLS e autenticação de backend antes do piloto público, e condiciona
  autenticação/TLS públicos AWS, retenção e otimização a evidência posterior.

## Handoff de execução

O plano está pronto para revisão em
`docs/superpowers/plans/2026-10-06-aws-terraform-deploy-economico.md`. Ele não
autoriza aplicação Terraform, criação de recursos AWS, deploy ou alteração de
configuração. Um executor delimitado deve implementar uma tarefa por vez e
entregar o resultado para revisão antes da próxima mutação material.
