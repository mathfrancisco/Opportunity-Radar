claude# Plano de hospedagem: Cloudflare Pages, OCI, Neon e Clerk

> **Status: planejado, não implementado (2026-10-06).** O Opportunity Radar
> atual é um aplicativo pessoal sem autenticação. Este runbook especifica uma
> implantação futura; não cria contas, recursos, chaves, DNS, deploys ou código.

## Resultado pretendido

```text
browser -> app.<domínio> (Cloudflare Pages + Clerk)
              | JWT
              v
         api.<domínio> (TLS proxy na OCI A1)
              | privado na VM
              v
        FastAPI + jobs em janelas -> Neon PostgreSQL
              |
              +-> bucket privado OCI + cópia criptografada do dono
```

O frontend é um artefato estático construído no Pages. A VM Oracle executa API,
proxy HTTPS e jobs; não executa PostgreSQL, build do frontend nem runtime do
frontend. O banco é Neon. O Clerk fornece autenticação, e a API continua sendo
o ponto de autorização.

## Decisões, limites e orçamento

| Item | Escolha planejada | Gate antes de criar |
| --- | --- | --- |
| Web | Cloudflare Pages | Confirmar build/output e limites atuais do Pages. |
| API/jobs | OCI A1, 2 OCPUs/12 GB | Capacidade em home region, imagem ARM e CI multiarch. |
| Dados | Neon Free | Meta <=80 CU-h/mês, <1 GB e extensões validadas. |
| Login | Clerk Hobby | Domínio próprio, DNS administrável e proprietário da aplicação. |
| State | OCI Resource Manager | Bootstrap manual, IAM mínimo, state/lock e preço/suporte confirmados. |
| Backup | Bucket OCI privado + cópia independente | Restore isolado provado antes de retenção. |

OCI Always Free anuncia 1.500 OCPU-h e 9.000 GB-h mensais, equivalentes a até
2 OCPUs/12 GB A1 no mês; o alvo de 2 OCPUs/12 GB consome toda essa cota. Boot e block volumes
compartilham 200 GB, com cinco backups de volume, no home region. Há risco de
recuperação de instância ociosa: acompanhar CPU, rede e RAM e não depender de
capacidade sem confirmar no console. [OCI Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)

Neon anunciou 1 GB e 100 CU-h mensais por projeto Free. Rodar 0,25 CU por 24x7
aproxima 186 CU-h/mês e não cabe. A meta de <=80 CU-h é uma margem operacional,
não uma garantia de gratuidade; medir no dashboard antes de ampliar janelas. Não
criar ping, keepalive ou carga para impedir suspensão. [Neon Free](https://neon.com/blog/neon-free-plan-1-gb-per-project)

Clerk Hobby lista 50.000 MRUs por app. Produção requer domínio próprio e DNS
controlável, chaves `pk_live`/`sk_live` e credenciais OAuth próprias; `pages.dev`
é aceitável apenas como piloto de desenvolvimento. Se não existir domínio, seu
registro e renovação são custo do plano. [Clerk pricing](https://clerk.com/pricing)
e [produção Clerk](https://clerk.com/docs/guides/development/deployment/production).

## Pré-requisitos e conta

- [ ] Registrar proprietário humano das contas OCI, Cloudflare, Neon e Clerk e
  contato de recuperação fora do repositório.
- [ ] Registrar domínio, registrador, responsável por DNS e orçamento anual;
  reservar `app.<domínio>` e `api.<domínio>`.
- [ ] Guardar Neon URL, Clerk secret, OAuth secrets, SSH administrativo e chave
  de criptografia de backup só em cofre/variáveis do provedor: nunca Git,
  `.tfvars`, user-data, state, imagem ou logs.
- [ ] Confirmar no console OCI capacidade A1 no home region, imagem ARM elegível
  e limites da tenancy antes de Terraform.

## Terraform OCI e bootstrap de state

Criar um root exclusivo `infra/terraform/oci/`; ele não importa backend, contas
ou state AWS. Estrutura mínima futura:

```text
infra/terraform/oci/
  providers.tf  versions.tf  variables.tf  outputs.tf
  network.tf    compute.tf   iam.tf         dns.tf
  envs/pilot.tfvars.example  README.md
```

1. Fazer manualmente o bootstrap mínimo: compartment, principal de operação,
   políticas IAM de menor privilégio e stack OCI Resource Manager. Não colocar
   segredo em variável Terraform, output ou cloud-init.
2. Usar Resource Manager como opção principal de state/lock depois de confirmar
   suporte e preço na conta. A FAQ informa que não há cobrança dedicada,
   preserva state e suporta locking; recursos provisionados podem cobrar se
   saírem da franquia. [FAQ Resource Manager](https://www.oracle.com/cloud/cloud-native/resource-manager/faq/)
3. Executar `init`, plano de ensaio, lock concorrente e recuperação controlada.
   Revisar cada mudança antes de apply e guardar identificador do job/stack.
4. Se Resource Manager não atender à conta/região, usar state local criptografado
   com cópia offline como alternativa de operador único. Registrar que não tem
   locking colaborativo nem recuperação gerenciada.

State pode conter valores sensíveis derivados: impedir que segredos cheguem a
ele, restringir leitura e não anexá-lo a tickets.

## VM, rede, TLS e Compose futuro

Provisionar uma VM ARM com 2 OCPUs/12 GB e boot padrão de 50 GB inicialmente:
não há PostgreSQL local que justifique disco maior. Aplicar atualizações de
segurança, usuário administrativo sem senha, chaves SSH e firewall. Permitir
80/443 publicamente, 22 somente do CIDR administrativo e nenhuma porta de
PostgreSQL. O proxy termina TLS para `api.<domínio>` e só alcança Uvicorn na rede
interna da VM.

Criar `compose.cloud.yaml` novo, sem depender de `compose.yaml` nem
`compose.dev.yaml`. Ele terá somente `migrate`, `api`, `worker` e proxy; todos
recebem `DATABASE_URL` Neon por secret manager/arquivo protegido no host. Não
montar volumes de banco e não construir/servir `apps/web` nele. A sequência é:

1. Build ARM64 e teste da imagem; só então publicar digest imutável aprovado.
2. Subir `migrate` uma vez e verificar versão Alembic.
3. Subir API privada, health/readiness e proxy TLS; provar `https://api.<domínio>`.
4. Subir worker com switches limitados, janelas finitas e logs.
5. Apontar Pages para a API somente após os controles de autenticação passarem.

### RAM, armazenamento e execução inicial

O experimento inicial usa a imagem runtime da API (o Compose atual usa o alvo
`test`, portanto a imagem cloud precisa ser medida separadamente), um processo
de API e um job por vez. Medir RSS de pico e headroom antes de declarar qualquer
capacidade; não há benchmark prometido. Não adicionar Redis, modelo local ou
outro daemon para compensar limites. Limitar logs, imagens e dumps, paginar ou
streamar processamento e usar batches e limites de pool são mudanças futuras
que exigem implementação e medição.

O payload bruto tem retenção atual de 365 dias. Só considerar 30 dias depois de
backup restaurado, proveniência preservada e registro relacionado protegido. A
retenção de avaliações de sete dias é opt-in; TTL de cache não apaga objetos
persistidos. Medir uso real antes de criar swap, volume extra ou daemon
adicional. Reavaliar risco de reclaim OCI quando CPU, rede ou RAM sustentarem
ociosidade; atividade artificial não é medida de disponibilidade.

## Cloudflare Pages

1. Criar projeto após escolher commit aprovado. Configurar raiz `apps/web`,
   comando de instalação `npm ci`, build `npm run build` e saída `dist` (Vite
   atual sem `outDir` personalizado); confirmar o diretório no primeiro preview.
2. Definir somente `VITE_API_BASE_URL=https://api.<domínio>` e
   `VITE_CLERK_PUBLISHABLE_KEY`. Uma variável `VITE_*` vai ao bundle: nunca
   colocar Neon URL, `sk_live`, credencial OAuth ou chave de backup.
3. Configurar fallback SPA sem capturar arquivos estáticos. Testar `/`, rota
   profunda, reload e preview antes da promoção.
4. Configurar domínio `app.<domínio>` e DNS Clerk para produção; manter
   `pages.dev` somente em desenvolvimento. Confirmar limites atuais na
   [documentação Pages](https://developers.cloudflare.com/pages/platform/limits/).

Na API, definir `FRONTEND_ORIGIN=https://app.<domínio>` e permitir o preflight
para `Authorization` apenas nessa origem. Não usar wildcard junto de credenciais.
Testar uma origem permitida e uma origem rejeitada antes da promoção.

## Neon: migração, pool e quota

Criar projeto separado para piloto e outro alvo isolado de teste/restauração;
nunca usar banco operacional na integração. Confirmar Postgres 17, pgvector,
unaccent, permissões `CREATE EXTENSION` para `vector` e `unaccent` no papel
fornecido e tamanho antes de importar. Executar:

1. `pg_dump` da origem por URL direta protegida, checksum e armazenamento
   criptografado fora da VM.
2. Restaurar no alvo isolado, rodar Alembic e verificar dados/esquema.
3. Repetir a restauração ensaiada no Neon piloto, então migrar no cutover com
   janela registrada e rollback definido.
4. Somente após aceite, apontar `DATABASE_URL` de runtime ao Neon de produção.

API e worker usam engines padrão com `pool_pre_ping=True`; a engine de API já
passa `options` para `statement_timeout`. A compatibilidade da URL pooler Neon
com SQLAlchemy, psycopg e esse `connect_args` é gate de ensaio, não propriedade
assumida. Medir conexões das duas engines, sessões, erros e CU-h por janela.
`pool_size` e `max_overflow` pequenos exigem configuração futura, pois não há
variáveis de ambiente para isso hoje; reduzir frequência, batch e duração de
jobs antes de considerar upgrade.

## Clerk e autorização da API

Implementação é trabalho futuro. A configuração prevista é:

1. Desenvolvimento pode usar instância/chaves de desenvolvimento. Produção só
   inicia após domínio/DNS, `pk_live`, `sk_live` servidor e OAuth próprio.
2. Frontend envia token de sessão Clerk à API por `Authorization: Bearer`. A
   chave publicável é a única chave Clerk no bundle.
3. FastAPI valida assinatura e issuer, expiração e `azp`/authorized parties;
   valida audience quando configurada. Usar JWKS/fluxo documentado pelo Clerk.
   [Manual JWT](https://clerk.com/docs/guides/sessions/manual-jwt-verification)
   e [authenticate request](https://clerk.com/docs/reference/backend/authenticate-request).
4. Depois de validar o token, comparar `sub` imutável com allowlist de dono em
   configuração de servidor. O app não é multi-tenant; qualquer login não basta.
5. Jobs usam identidade interna/configuração do servidor e banco; jamais token
   de sessão humana.

Cobrir rotas diretas que leem ou mudam dados sensíveis. CORS e UI escondida não
são autenticação. Testes obrigatórios: token ausente/malformado 401; expirado ou
assinatura inválida 401; `sub` válido não aprovado 403; dono aprovado 200.

## Jobs Oracle: janela finita, overlap e fencing

O worker atual agenda coleta, normalização, avaliação, análise e retenção.
`heartbeat()` apenas gera log e não escreve no banco. `observe_job` e os jobs
reais escrevem estado/telemetria; normalização e avaliação usam 60 s hoje.
`collect.py` cobre coleta e não é executor completo de pipeline.

No piloto, rodar worker em janelas delimitadas por timer/serviço supervisionado,
com início/fim, timeout, log e métrica. Ao terminar a janela, solicitar
shutdown gracioso e aguardar parada segura depois da execução; não usar SIGKILL
nem timer que interrompa um job ativo. Preservar exclusão mútua, leases/claims,
fencing e monitoramento: uma execução não pode sobrepor outra ou fechar uma
ausência parcial. Iniciar com subset de jobs e agenda conservadora. Um runner de
pipeline completo é gate antes de depender de uma invocação para todos os
estágios.

Alertar em deadline, lease vencido, janela perdida, fila crescente, erro Neon,
falha de backup, uso acima da trajetória de 80 CU-h e indisponibilidade OCI.
Não substituir telemetria por “serviço online”.

## Backup, restore e retenção

1. Produzir dump lógico por URL Neon direta, não URL pool sem validação;
   criptografar antes do upload ao bucket OCI privado.
2. Manter cópia independente criptografada do dono. Após trial, OCI Always Free
   tem 20 GB combinados e 50.000 requisições/mês: contar dumps, versões e state.
   [OCI storage limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
3. Rodar restore periódico para alvo local isolado ou projeto isolado do
   provedor, seguido de checks de schema e amostra de dados. Não confiar somente
   na janela de instant restore de seis horas do Neon.
4. `scripts/restore_check.py` pode requerer `CREATE`/`DROP`; não apontá-lo à
   produção e registrar se a conta Neon não concede esses privilégios.
5. Fixar `prune-days=0` até backup restaurado e política documentada. Depois,
   escolher retenção por RPO/RTO, custo e teste de restauração.

## Rollout, aceitação e rollback

| Etapa | Prova de aceite | Rollback |
| --- | --- | --- |
| Compatibilidade | CI ARM64/multiarch, imagem inicia, PG17/vector/unaccent isolado passa | Não criar produção. |
| Infra | State/lock, IAM, firewall, DNS e TLS `api` verificados | Destruir apenas recurso novo aprovado; preservar auditoria. |
| Dados | Dump com checksum e restore isolado | Reapontar API durante janela planejada. |
| Auth | Matriz 401/403/200 em rotas sensíveis | Despublicar/fechar ingress até corrigir. |
| Piloto | Sem overlap, health, alertas e <=80 CU-h projetados | Pausar timers/worker e investigar. |
| Produção | Domínios, chaves live, backup e monitoramento | Reverter Pages e imagem ao build/digest anterior. |

Executar integração somente com `RUN_DATABASE_INTEGRATION=1`,
`DATABASE_INTEGRATION_ISOLATED=1` e database terminando em `_test`; nunca no
Neon operacional. Health não substitui teste de auth, backup ou pipeline.

## Pendências e gates finais

- [ ] Verificar limites/preços atuais antes de provisionar.
- [ ] Confirmar domínio/DNS para Clerk produção e TLS de `api.<domínio>`.
- [ ] Confirmar capacidade A1/imagem ARM e adicionar CI multiarch.
- [ ] Criar Terraform OCI separado e provar Resource Manager state/lock ou
  documentar state local criptografado.
- [ ] Criar `compose.cloud.yaml` sem Postgres/frontend.
- [ ] Validar Neon pool/SQLAlchemy, PG17, vector, unaccent e <=80 CU-h medidos.
- [ ] Implementar Clerk, allowlist de `sub` e matriz 401/403/200.
- [ ] Implementar timers/janelas e runner completo futuro.
- [ ] Provar backup, restore isolado, alertas e rollback antes de `prune-days`.

Enquanto houver pendência, o estado é “planejado”, não hospedado, autenticado,
pronto para produção ou sem custo.

---

# Procedimento detalhado e evidências por etapa

Esta segunda parte transforma as decisões acima em uma sequência executável.
Ela é deliberadamente prescritiva, mas não é um conjunto de comandos para criar
infraestrutura hoje. Onde a configuração ou o código ainda não existe, o texto
identifica o card que precisa entregá-lo antes da ação.

## Índice operacional

1. [Pré-flight e ferramentas](#pré-flight-e-ferramentas)
2. [Contas, domínio e orçamento](#contas-domínio-e-orçamento)
3. [Bootstrap OCI, state e IAM](#bootstrap-oci-state-e-iam)
4. [Rede, VM e runtime](#rede-vm-e-runtime)
5. [Imagens e entrega contínua](#imagens-e-entrega-contínua)
6. [Neon, migrações e compatibilidade](#neon-migrações-e-compatibilidade)
7. [Clerk, frontend e autorização da API](#clerk-frontend-e-autorização-da-api)
8. [Pages, DNS, TLS e CORS](#pages-dns-tls-e-cors)
9. [Jobs e janelas finitas](#jobs-e-janelas-finitas)
10. [Capacidade, retenção e backups](#capacidade-retenção-e-backups)
11. [Testes, aceite e operação](#testes-aceite-e-operação)
12. [Cutover, rollback e recuperação](#cutover-rollback-e-recuperação)
13. [Sequência dos cards](#sequência-dos-cards)

## Pré-flight e ferramentas

### Objetivo e fronteiras

O objetivo é hospedar um frontend estático no Cloudflare Pages, uma API e jobs
na OCI, dados no Neon e identidade no Clerk. A arquitetura não autoriza criar
recursos, alterar DNS, migrar dados ou ativar login enquanto os gates desta
seção não estiverem registrados.

O plano geral de alternativa em AWS fica fora deste runbook. Consulte o
[plano de AWS e Terraform](superpowers/plans/2026-10-06-aws-terraform-deploy-economico.md)
somente se a decisão de plataforma mudar formalmente. Não misture state, custos
ou instruções AWS com o piloto OCI.

### Registro de decisão

Antes de abrir qualquer console, crie um registro privado de mudança com estas
informações:

| Campo | Valor a registrar | Resultado esperado |
| --- | --- | --- |
| Mudança | Piloto, staging ou produção | Escopo e data explícitos. |
| Dono | Uma pessoa com recuperação | Responsável por aprovar e interromper. |
| Janela | Início, fim e fuso horário | Não há operação aberta. |
| Reversão | Build anterior, DNS anterior e dono | Cada ação reversível tem executor. |
| Dados | Nenhum, cópia ou produção | O risco de dados está classificado. |
| Custo | Teto mensal e alerta | A franquia não é tratada como garantia. |

Não registre segredos nesse documento, em tickets ou no histórico do shell.
Registre apenas o local do cofre, o nome lógico da credencial e quem pode
recuperá-la.

### Ferramentas do operador Windows

Execute os passos locais no PowerShell, na raiz do repositório. O ambiente atual
tem `apps/web`, `compose.yaml`, `compose.dev.yaml`, scripts Python e workflows
de CI. Não há hoje Terraform OCI, `compose.cloud.yaml`, integração Clerk ou
pipeline de imagem cloud.

1. Abra PowerShell e entre em `C:\Users\mathf\Documents\GitHub\Opportunity-Radar`.
2. Confirme que a árvore de trabalho está compreendida antes de criar um commit
   de implantação. Alterações não relacionadas não fazem parte do release.
3. Leia `README.md`, `docs/30-runbook.md` e este arquivo. O runbook existente
   descreve comandos locais de backup e restauração que devem continuar sendo a
   referência até que o card de cloud os adapte.
4. Use o ambiente Python ou os containers já documentados pelo repositório para
   checks de código. Não instale dependências globalmente para compensar erro de
   configuração.
5. Use os consoles OCI, Neon, Clerk e Cloudflare somente com a conta de
   operador registrada. Cada console deve ter MFA e contato de recuperação.

Resultado esperado: o operador sabe qual máquina e qual conta usa em cada
passo. Falha comum: executar um comando de Compose em Windows com caminhos de
Linux copiados de um timer OCI. Diagnóstico: confira o prompt e o diretório
atual; os passos de VM abaixo são para Ubuntu na OCI, não PowerShell.

### Inventário de fatos atuais

O inventário é parte do gate F53-01. Registre o hash do commit testado e a data
da inspeção, pois estes fatos podem mudar antes do rollout:

| Área | Fato observado | Implicação de hospedagem |
| --- | --- | --- |
| Web | `apps/web` é Vite e gera `dist` | Pages constrói com `npm ci` e `npm run build`. |
| Web | `.env.example` usa `VITE_API_BASE_URL=/api` | Produção precisará URL absoluta da API. |
| Compose | API atual publica `127.0.0.1:8000` | O proxy cloud será novo e a API fica privada. |
| Compose | O target atual da API é `test` | Runtime ARM exige target e medição próprios. |
| Worker | Jobs vivem em `opportunity_radar.worker` | Não presumir que `collect.py` executa pipeline inteiro. |
| Banco | O projeto usa migrations Alembic | Migração é etapa única e anterior a API/worker. |
| Auth | Não há Clerk no runtime atual | Frontend e backend precisam de implementação e testes. |

Faça uma nova inspeção antes de cada card se qualquer um desses itens mudar.
Não promova uma decisão de planejamento a fato de implementação sem uma revisão
do diff e evidência de teste.

### Checkpoint de pré-flight

Marque todos os itens antes de seguir para uma conta ou provedor:

- [ ] O commit candidato, o dono e a janela estão registrados.
- [ ] Os contatos de recuperação e MFA foram revisados fora do repositório.
- [ ] A pessoa que pode reverter Pages, OCI, Neon e Clerk está disponível.
- [ ] A recuperação de dados tem destino isolado definido.
- [ ] Nenhum teste de integração será apontado ao banco operacional.
- [ ] Nenhum segredo será passado em `VITE_*`, state Terraform ou log de CI.

Se algum item faltar, pare no gate. O rollback de uma infraestrutura ainda não
criada é não criar a infraestrutura.

## Contas, domínio e orçamento

### Criar e separar as contas

Execute estes passos no navegador, em uma sessão de operador com MFA.

1. Crie ou selecione a tenancy OCI no home region desejado. Confirme no console
   que a capacidade A1 está disponível antes de escrever Terraform.
2. Crie ou selecione uma conta Cloudflare controlada pelo proprietário do
   aplicativo. Registre o zone ID apenas em inventário privado, se necessário.
3. Crie um projeto Neon separado para o piloto. Não reutilize um projeto de
   testes compartilhado para produção.
4. Crie uma aplicação Clerk separada por ambiente. Não reutilize chaves de
   desenvolvimento em produção.
5. Defina ao menos dois administradores para cada conta quando o plano permitir.
   Teste a recuperação sem divulgar os códigos de recuperação.

Resultado esperado: cada provedor exibe a conta e o ambiente corretos. Falha
comum: usar uma organização pessoal temporária como proprietária de produção.
Diagnóstico: veja a página de membros, a fatura e a recuperação antes de criar
o primeiro recurso.

### Domínio e DNS

Produção requer domínio próprio. `*.pages.dev` serve para desenvolvimento e
preview, mas não substitui o domínio verificado pelo Clerk nem credenciais OAuth
de produção.

1. Registre ou escolha o domínio principal e registre custo anual, renovação e
   proprietário.
2. Decida os nomes estáveis `app.<domínio>` e `api.<domínio>`.
3. Delegue ou mova a zona DNS para o Cloudflare somente depois de registrar os
   nameservers anteriores e a forma de restaurá-los.
4. Mantenha uma lista de cada registro criado, seu TTL, finalidade e dono.
5. Reserve os registros que Clerk pedir para domínio, e-mail ou OAuth. Não
   adivinhe valores CNAME/TXT: copie-os da aplicação Clerk desse ambiente.
6. Antes de trocar um registro existente, capture o valor anterior e confirme a
   janela de propagação com o registrador.

Resultado esperado: `app` e `api` têm destinos planejados e registros Clerk
pendentes ou validados. Falha comum: trocar o domínio no Clerk antes de possuir
o DNS. Diagnóstico: a verificação mostra pendente; restaure o registro anterior
e conclua a posse da zona.

### Custos e limites em 6 de outubro de 2026

Estes números são referências de planejamento, não promessa de preço. Revise os
dashboards e páginas oficiais no dia do provisionamento.

| Serviço | Referência | Decisão operacional |
| --- | --- | --- |
| OCI A1 | 1.500 OCPU-h e 9.000 GB-h/mês | 2 OCPUs e 12 GB consomem a cota mensal inteira. |
| OCI block | 200 GB Always Free | Começar com boot de 50 GB e medir. |
| OCI object | 20 GB e 50.000 requests/mês Always Free | Contar dumps, restores, versões e downloads. |
| Neon Free | 1 GB e 100 CU-h/mês | Meta interna <=80 CU-h, com alerta antes disso. |
| Clerk Hobby | 50.000 MRUs por app | Domínio, OAuth e uso podem criar custo externo. |

As referências oficiais são [OCI Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm),
[Neon Free](https://neon.com/blog/neon-free-plan-1-gb-per-project) e
[Clerk pricing](https://clerk.com/pricing). A leitura do plano do Neon deve
confirmar limites atuais antes de calcular custo.

Uma capacidade mínima de 0,25 CU contínua por 24 horas durante 31 dias seria
cerca de 186 CU-h. Isso ultrapassa 100 CU-h e também a meta de 80 CU-h. Não use
consulta periódica, readiness que consulta banco ou keepalive para evitar
suspensão: isso aumenta custo e não prova disponibilidade.

### Gate de orçamento F53-01

Antes de criar recurso faturável:

1. Abra a tela de uso de cada provedor.
2. Registre o valor inicial de CU-h, armazenamento, egress, requests e MRUs.
3. Configure alertas disponíveis abaixo do teto de cada provedor.
4. Determine o teto monetário mensal fora da franquia e quem pode aprová-lo.
5. Registre qual serviço deve ser pausado primeiro ao atingir o alerta: jobs,
   preview ou produção.

Resultado esperado: uma pessoa consegue responder quanto custa o piloto e como
interrompê-lo. Se a resposta depender de estimativa sem painel, não habilite
jobs de produção.

## Bootstrap OCI, state e IAM

### Limite deste bootstrap

O bootstrap é manual porque o Terraform ainda não existe. Depois de pronto, o
state e os jobs devem viver no OCI Resource Manager. O serviço mantém state e
locking por stack; uma stack não deve executar dois jobs ao mesmo tempo. Consulte
a [visão geral do Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/resourcemanager.htm),
[criação de stack](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-stack.htm)
e [criação de job](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-job.htm).

Resource Manager não tem cobrança dedicada anunciada, mas os recursos que ele
cria podem cobrar. Não conclua que uma stack é gratuita sem revisar cada recurso
e sua região.

### Passos de bootstrap no console OCI

1. Em **Identity & Security**, crie um compartment exclusivo do ambiente.
2. Crie um grupo de operadores de infraestrutura. Não use usuário raiz para
   ações cotidianas.
3. Crie uma política de menor privilégio limitada ao compartment. Separe quem
   lê state de quem aplica alterações, quando a equipe justificar essa divisão.
4. Crie um principal de automação para CI somente quando o workflow existir.
   Não gere chave de API sem local aprovado para armazenamento.
5. Em **Developer Services**, crie a stack Resource Manager usando a fonte de
   Terraform revisada pelo card F53-03.
6. Configure variáveis não secretas na stack. Entregue segredos por mecanismo
   de secret manager suportado, não como output, `tfvars` ou user-data.
7. Execute primeiro um plan. Revise additions, changes e destroys.
8. Execute apply apenas com a janela aprovada e guarde o URL/ID do job no
   registro de mudança.

Resultado esperado: uma stack possui histórico, state e lock próprios. Falha
comum: duas pessoas iniciam apply em fontes diferentes. Diagnóstico: consulte o
job ativo da stack; não force novo apply. Aguarde, cancele somente com dono e
replaneje a partir do state atual.

### Estrutura Terraform futura

F53-03 e F53-04 criam o root. Até isso acontecer, os nomes abaixo são desenho,
não arquivos existentes:

```text
infra/terraform/oci/
  providers.tf        versions.tf       variables.tf
  iam.tf              network.tf        compute.tf
  outputs.tf          envs/pilot.tfvars.example
  README.md
```

O root deve receber apenas identificadores e valores públicos que sejam seguros
no state. `DATABASE_URL`, chave privada SSH, chave Clerk secreta, credenciais
OAuth, chave de backup e tokens de registro não podem aparecer em plano,
output, estado, `terraform.tfvars` versionado ou shell history.

### Revisão de IAM

Antes do primeiro apply, revise em pares:

- [ ] O compartment é o do ambiente correto.
- [ ] A política não permite gerenciar todos os compartments sem necessidade.
- [ ] O CI não recebeu poderes de tenancy ou de faturamento.
- [ ] Leitura de state está restrita e auditável.
- [ ] Credenciais humanas usam MFA e não são compartilhadas.
- [ ] Um recurso fora da franquia tem aprovação explícita.

Se uma política parece ampla porque o provedor exige escopo, documente a razão,
o recurso afetado e a data para rever. Não silencie o risco com um wildcard.

### Política IAM: molde para revisão, não comando pronto

Depois de F53-03 criar os grupos e confirmar os verbos exigidos pelo provider,
escreva políticas usando placeholders revisados. O formato abaixo mostra o
escopo esperado; substitua os valores somente no console OCI do ambiente certo:

```text
Allow group <grupo-infra-piloto> to manage virtual-network-family in compartment <compartment-piloto>
Allow group <grupo-infra-piloto> to manage instance-family in compartment <compartment-piloto>
Allow group <grupo-infra-piloto> to manage volume-family in compartment <compartment-piloto>
Allow group <grupo-deploy-piloto> to use instances in compartment <compartment-piloto>
```

Não cole esse molde como política final. O provider Terraform pode exigir verbs
ou famílias adicionais, e a equipe precisa reduzir o conjunto ao plan real.
Evite `manage all-resources in tenancy`; não conceda Object Storage, Vault,
DNS, IAM ou Billing sem um recurso e workflow que justifiquem o acesso.

Para revisar, abra **Identity & Security > Policies**, confirme compartment,
grupo, escopo e cada linha, e compare o resultado ao plan. Registre o nome da
política, mas não credenciais. Se o plan pedir permissão não prevista, pare,
classifique o recurso e faça nova revisão de menor privilégio.

## Rede, VM e runtime

### Desenho de rede F53-04

O Terraform futuro cria VCN, subnet pública para o proxy e a VM, route table,
internet gateway e NSG. Não crie banco local, Redis local ou frontend Node na
VM. A comunicação com Neon sai por TLS para a Internet; PostgreSQL não recebe
porta pública na OCI.

| Fluxo | Origem | Destino | Regra |
| --- | --- | --- | --- |
| HTTPS público | Internet | proxy `api` | TCP 443. |
| Desafio/acme se usado | Internet | proxy | TCP 80 durante validação. |
| Administração | CIDR do operador | VM | TCP 22, chave SSH, sem senha. |
| API interna | proxy local | Uvicorn | rede privada/local, sem NSG público. |
| Banco | VM | Neon | TLS de saída. |
| Postgres local | ninguém | VM | sem porta e sem serviço. |

### Criar a VM por Terraform e inspecionar no console

Depois de F53-04 e plan revisado, o Resource Manager cria a VM. O console serve
para inspecionar o resultado e confirmar quota; não crie VM paralela manual fora
do state.

1. Escolha shape ARM A1 com alvo máximo de 2 OCPUs e 12 GB apenas se a quota e
   capacidade forem confirmadas no home region.
2. Use imagem Ubuntu ARM suportada e grave versão e região no inventário.
3. Configure volume de boot de 50 GB como início. Não anexe volume adicional
   antes da medição de logs, imagens e backups.
4. Injete somente chave pública SSH no metadata. Nunca coloque segredo de app em
   cloud-init ou user-data.
5. Aplique NSG conforme a tabela. Restrinja SSH ao CIDR administrativo real.
6. Após iniciar, confirme no console IP público, NIC, NSG e boot volume.
7. Conecte por SSH a partir da estação de operador e verifique arquitetura ARM
   antes de usar uma imagem.

Resultado esperado: a VM aceita SSH somente da rede autorizada e não expõe
PostgreSQL ou Uvicorn. Falha comum: liberar `0.0.0.0/0` na porta 22 para testar.
Diagnóstico: revise NSG e rota; feche a regra ampla antes de continuar.

### Validar Terraform local e no Resource Manager

Estes comandos só são válidos depois de F53-03/F53-04 criarem
`infra/terraform/oci/` e de o Terraform compatível estar instalado na estação
Windows. Execute-os no PowerShell, no root Terraform, sem segredo na linha:

```powershell
Set-Location .\infra\terraform\oci
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

`init -backend=false` valida providers e módulos localmente sem fingir que o
state Resource Manager é backend local. Ele não substitui o plan remoto. Não
execute `terraform apply` localmente quando Resource Manager for a fonte de
state e lock escolhida.

No OCI, navegue em **Developer Services > Resource Manager > Stacks > <stack>
> Plan**. Revise o job, diff e variáveis mascaradas. Após a aprovação da janela,
use **Apply** no mesmo stack e registre o job ID. Se a fonte do stack divergir
do commit revisado, cancele e publique a fonte correta primeiro.

### Base do host Ubuntu

Estes passos são futuros e devem virar automação revisada no card F53-05. Na VM
Ubuntu, o operador deve:

1. Criar usuário administrativo nominal com chave SSH e desabilitar login por
   senha conforme política do sistema.
2. Aplicar atualizações de segurança dentro da janela e reiniciar se necessário.
3. Instalar Docker Engine e plugin Compose por fonte oficial da distribuição.
4. Criar diretório de release acessível ao usuário de deploy, com permissões
   mínimas e sem segredo em checkout Git.
5. Configurar rotação de logs e espaço máximo antes de iniciar containers.
6. Criar local protegido para um arquivo de ambiente entregue pelo cofre. Esse
   arquivo deve ser legível apenas pelo usuário do serviço.
7. Registrar versão do SO, Docker, Compose e kernel no inventário.

Resultado esperado: o host pode executar imagens por digest e não armazena
segredos no repositório. Falha comum: usar `.env` copiado do computador local.
Diagnóstico: trate a cópia como potencial vazamento, revogue o que foi exposto e
use entrega de segredo aprovada.

#### Instalação Docker: comandos de referência após F53-05

Execute na VM Ubuntu somente depois de a imagem e `compose.cloud.yaml` terem
sido entregues por F53-05. Confirme a versão Ubuntu na documentação oficial do
Docker antes de rodar, pois codenames e pré-requisitos podem mudar:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

Complete a entrada do repositório e a instalação seguindo [Install Docker Engine
on Ubuntu](https://docs.docker.com/engine/install/ubuntu/). Depois, valide
`docker version` e `docker compose version` como administrador. Adicione o
usuário de deploy ao grupo `docker` apenas se o modelo de ameaça aceitar o
privilégio equivalente a root; caso contrário, use `sudo` para operação manual.

Os diretórios são convenção proposta para F53-05, não arquivos existentes hoje:

```bash
sudo install -d -o "<deploy-user>" -g "<deploy-group>" -m 0750 /srv/opportunity-radar
sudo install -d -o root -g "<deploy-group>" -m 0750 /etc/opportunity-radar
```

A entrega de segredo cria ou substitui `cloud.env` atomica e explicitamente a
partir do cofre, com owner `root`, grupo de runtime e modo `0640`. O bootstrap
não cria o arquivo com `/dev/null`, porque uma reexecução poderia truncar segredo
válido. A entrega confere apenas os nomes esperados e permissões; nunca imprime
o arquivo com `cat`, `env` ou log verboso.

### Compose cloud futuro

`compose.cloud.yaml` não existe nesta árvore. F53-05 deve criá-lo e provar seu
comportamento. O desenho mínimo contém `migrate`, `api`, `worker` e proxy:

| Serviço | Função | Regra |
| --- | --- | --- |
| `migrate` | Executa `alembic upgrade head` uma vez | Sem restart automático. |
| `api` | Uvicorn privado | Só inicia após migration aceita. |
| `worker` | Pipeline agendado | Desabilitado até F53-10 e F53-11. |
| proxy | TLS e roteamento externo | Único serviço que publica portas. |

O arquivo não monta `postgres_data`, não tem container PostgreSQL, não constrói
ou serve `apps/web`, e não assume que o Compose de desenvolvimento serve como
produção. Use o `DATABASE_URL` adequado ao papel: URL direta para migration e
backup quando validada; URL pool para runtime somente se o gate de compatibilidade
confirmar pool, driver e limites.

O override cloud deve reaproveitar a rota existente sem acesso ao banco:

```yaml
# Trecho para compose.cloud.yaml, somente após F53-05 criá-lo.
services:
  api:
    healthcheck:
      test:
        ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"]
      interval: 30s
      timeout: 3s
      retries: 3
```

O intervalo é ponto de partida de planejamento, não limite validado. F53-12 deve
medir custo e ajustar. Não substitua `/health/live` por `/health` ou
`/health/ready` nesse loop: ambas as rotas atuais consultam banco.

### Health sem despertar banco

As rotas atuais já diferenciam os casos: `/health/live` não consulta banco;
`/health/ready` e `/health` consultam. O Compose atual chama `/health` a cada
dez segundos. Em Neon, essa frequência pode impedir scale-to-zero e consumir
CU-h. A referência do provedor confirma que consultas frequentes impedem o
endpoint de escalar a zero: [Neon endpoints](https://neon.com/docs/manage/endpoints/).

F53-05/F53-12 devem fazer o override cloud apontar o healthcheck frequente para
`/health/live`. Preserve a rota liveness mínima sem detalhes privados e sem
dependência de Clerk ou banco. Use `/health/ready` somente no deploy, sob demanda
ou em janela limitada e orçada; não a conecte a polling infinito do proxy.

O monitoramento precisa separar:

1. **Liveness**: processo HTTP responde sem abrir conexão ou executar query.
2. **Readiness**: verifica dependências necessárias para receber tráfego, com
   frequência e orçamento deliberados.
3. **Sinal operacional**: job, DB e backup aparecem no monitoramento; não são
   inferidos apenas por HTTP 200.

Antes de implementar esse override no Compose cloud, não trate a rota atual
como prova de que o monitoramento será economicamente seguro no Neon.

## Imagens e entrega contínua

### F53-05: imagem ARM e digest

O repositório atual não documenta uma imagem cloud multiarch nem um registry de
produção. O card deve escolher registry, permissões e retenção antes de escrever
workflow. A sequência de implementação deve ser:

1. Fixar versões de base e dependências no Dockerfile revisado.
2. Construir a imagem para ARM64 em CI.
3. Executar testes apropriados contra a imagem, incluindo inicialização da API.
4. Publicar somente imagem aprovada, identificada por digest imutável.
5. Registrar no artefato de release commit, digest, data, plataforma e autor.
6. Na VM, puxar o digest aprovado, nunca uma tag mutável como `latest`.
7. Guardar o digest anterior para rollback antes de qualquer troca.

Resultado esperado: o host executa o mesmo artefato aprovado pelo CI. Falha
comum: imagem x86 inicia localmente e falha na A1 ARM. Diagnóstico: inspecione
plataforma no manifest e reproduza a inicialização no alvo ARM antes do deploy.

### Variáveis de runtime e segredos

Divida configurações em três grupos:

| Grupo | Exemplos | Local permitido |
| --- | --- | --- |
| Pública de build | `VITE_API_BASE_URL`, chave publicável Clerk | Pages, bundle. |
| Runtime não secreto | `FRONTEND_ORIGIN`, nível de log, feature flags | secret store ou ambiente do host. |
| Segredo | Neon URL, Clerk secret, OAuth secret, chaves de backup | Cofre/secret manager, nunca bundle. |

Uma chave prefixada por `VITE_` é compilada para JavaScript que qualquer pessoa
pode baixar. A chave publishable Clerk pode ser pública; `sk_live`, URLs de
banco e credenciais OAuth não podem receber esse prefixo.

### Entrega na VM

Depois de F53-05 existir, a entrega deve seguir este protocolo, executado pela
automação aprovada ou por operador na VM:

1. Baixe o digest liberado.
2. Compare-o ao digest registrado pelo CI.
3. Valide sintaxe da configuração e presença dos nomes de segredo, sem imprimi-
   los.
4. Execute migration uma vez e pare se ela retornar erro.
5. Suba API atrás do proxy, mas sem ainda mudar DNS público.
6. Faça liveness, readiness e matriz de autenticação no endpoint controlado.
7. Registre versão ativa, digest anterior e hora.

Não acrescente um comando de Compose a esta documentação antes de o card criar
o arquivo correspondente. Um exemplo inexistente parece instrução executável e
causa drift operacional.

## Neon, migrações e compatibilidade

### Criar projeto e limitar conexões

No console Neon, execute para o ambiente correto:

1. Crie projeto ou branch de piloto com região compatível com a OCI escolhida.
2. Crie banco e role de aplicação com privilégios mínimos necessários.
3. Gere URLs separadas para migration, runtime e backup conforme o pooler e os
   privilégios disponíveis.
4. Guarde cada URL no cofre sob nome que declare ambiente e finalidade.
5. Registre capacidade inicial, autosuspend, armazenamento e CU-h no inventário.
6. Não execute migrations, testes ou `restore_check.py` contra o banco de dados
   operacional só para conferir conectividade.

O nome de uma URL não é prova de isolamento. Uma rotina que cria ou derruba
banco precisa de destino explicitamente separado e permissões revisadas.

### Gate de PostgreSQL 17 e extensões F53-06

O projeto precisa validar a versão oferecida, cada extensão exigida e o
comportamento das migrations em Neon. Faça isso em banco isolado, após o card
fornecer fixture e comando revisado:

1. Compare versão PostgreSQL reportada pelo Neon ao requisito de migrations.
2. Liste extensões disponíveis e confirme as necessárias pelo schema atual,
   incluindo vector e unaccent quando as migrations as solicitarem.
3. Execute upgrade a partir de banco vazio isolado.
4. Execute a suite de migração e os testes de query relevantes.
5. Faça downgrade somente quando a política de migration o permitir e preserve
   dados de teste para inspecionar perda.
6. Registre diferenças do pooler, de DDL e de transações para a decisão de URL
   direta versus URL pooled.

Resultado esperado: uma matriz com versão, extensão, URL usada, migration e
teste aprovado. Falha comum: extensão existe em lista de marketing, mas não está
habilitada para o papel ou plano. Diagnóstico: pare antes de alterar produção e
escolha um plano ou desenho compatível.

### Pool, timeout e concorrência são mudanças futuras

O pool de SQLAlchemy, `pool_pre_ping`, tamanho de pool, `pool_timeout`,
`statement_timeout` e limite de concorrência ainda exigem design, mudança e
medição. Não copie números deste plano para produção sem F53-06 e F53-12.

Ao implementar, teste pelo menos:

- conexões simultâneas acima do limite escolhido;
- query que excede `statement_timeout`;
- recuperação de conexão pooled após suspensão/reconexão;
- migration pela URL direta e runtime pela URL escolhida;
- erro de credencial, banco inexistente e TLS inválido.

O resultado de cada teste precisa registrar se uma falha é controlada, se o
worker recua e se a API não deixa transação parcial.

### Migrations e URLs diretas

Execute migration somente uma vez por release e somente depois de backup atual
restaurável. A URL direta pode ser necessária para DDL, mas isso deve ser
confirmado pelo gate de compatibilidade do Neon e da biblioteca. Não coloque a
URL direta em frontend, logs, issue, output de plan ou estado Terraform.

Se uma migration falhar:

1. Pare API e worker candidatos antes de repetir.
2. Registre versão Alembic, erro sanitizado e digest do release.
3. Não altere manualmente tabelas para "fazer passar" sem plano de recuperação.
4. Decida entre migration corretiva, rollback suportado ou restore validado.
5. Só retome quando contagens e schema forem comparados ao backup.

## Clerk, frontend e autorização da API

### Decisão de identidade F53-07/F53-08

Clerk autentica a sessão; a API ainda autoriza cada request. O produto é um app
pessoal, portanto o `sub` imutável do usuário dono é a identidade a autorizar.
E-mail, nome e metadados editáveis não substituem `sub`.

1. Crie instâncias Clerk diferentes para desenvolvimento, preview e produção.
2. Configure domínio próprio e registros DNS solicitados pelo console Clerk.
3. Crie credenciais OAuth próprias para produção quando o provedor exigir.
4. Mantenha chave publishable no frontend e chave secreta somente no backend.
5. Defina allowlist de `sub` no lado servidor, entregue pelo cofre, com rotação
   documentada e auditoria de mudança.
6. Não habilite um segundo dono ou multi-tenant por inferência; isso precisa de
   requisito e modelo de autorização próprios.

### Validação JWT na FastAPI

F53-07 deve adicionar dependência e integração sem fixar uma versão não
verificada. Consulte o README do [SDK Python do Clerk](https://github.com/clerk/clerk-sdk-python/blob/main/README.md)
e fixe versão apenas depois de avaliar lockfile e compatibilidade.

Para cada request protegida, a implementação precisa:

1. Exigir `Authorization: Bearer <JWT>` e rejeitar ausência ou formato inválido.
2. Buscar ou reutilizar JWKS pelo fluxo suportado, com rotação segura de chaves.
3. Verificar assinatura e algoritmo permitido; não aceite `none` nem algoritmo
   escolhido pelo token sem allowlist.
4. Verificar `iss` contra o issuer da instância Clerk correta.
5. Verificar `exp` e `nbf` considerando pequeno skew de relógio explicitamente
   configurado e testado.
6. Verificar `azp` por `authorized_parties` em `snake_case`, conforme SDK
   Python, quando a aplicação usar esse claim.
7. Verificar `aud` quando a instância ou o template de token o emitir; não
   invente audience ausente para contornar uma incompatibilidade.
8. Comparar `sub` à allowlist imutável depois de validar criptograficamente o
   token. Retorne 403 para sujeito válido, mas não autorizado.
9. Registrar decisão de auth sem token, e-mail, URL, segredo ou JWT completo.

JWKS deve aceitar rotação: em falha de `kid` desconhecido, atualize conforme o
SDK e tente somente o fluxo controlado. Não desligue a validação de assinatura
para reparar uma rotação.

### Matriz obrigatória de autorização

F53-07 não fecha sem testes de API para esta matriz:

| Caso | Resposta esperada | Evidência |
| --- | --- | --- |
| Sem header | 401 | Rota não chega ao handler. |
| Bearer malformado | 401 | Não vaza parser ou stack trace. |
| Assinatura ou `iss` inválido | 401 | JWKS não é contornado. |
| `exp` passado ou `nbf` futuro | 401 | Relógio é tratado corretamente. |
| Algoritmo fora da allowlist | 401 | Não há downgrade de algoritmo. |
| `azp` ou `aud` incompatível, se aplicável | 401 | Claim é validado quando presente/configurado. |
| `sub` válido fora da allowlist | 403 | Autenticação não concede acesso. |
| Dono permitido | 200/ação esperada | Rota mantém comportamento autorizado. |

Cubra leitura e mutação. Esconder um botão no React, limitar CORS ou usar uma
rota de Pages não substitui a proteção no FastAPI.

### Frontend Clerk

F53-08 deve integrar o SDK React aprovado e testes de UI. Configure no Pages
apenas a chave publishable e a URL pública da API. O frontend deve obter token
de sessão e enviá-lo por `Authorization` nas chamadas protegidas.

Teste também logout, token expirado, tela de acesso negado e recarga em rota
profunda. Se a chave publishable ou domínio Clerk estiver errado, o preview deve
falhar de modo visível sem expor segredo no console do navegador.

## Pages, DNS, TLS e CORS

### Projeto Cloudflare Pages F53-08

No console Cloudflare, depois de o commit e a integração Clerk estarem prontos:

1. Crie o projeto Pages a partir do repositório e branch aprovados.
2. Defina **Root directory** como `apps/web`.
3. Defina **Build command** como `npm run build` e instalação como `npm ci`.
4. Defina **Build output directory** como `dist`.
5. Adicione variáveis de preview e produção separadamente.
6. Em produção, defina `VITE_API_BASE_URL=https://api.<domínio>` e a chave
   publishable Clerk daquele ambiente.
7. Gere preview e verifique build, assets e console antes de promover.

O Pages serve SPA por padrão quando não existe um arquivo `404.html` na raiz do
output. Não acrescente redirect catch-all sem necessidade: ele pode capturar
arquivos reais. A referência é [servir Pages e SPA](https://developers.cloudflare.com/pages/configuration/serving-pages/).

### Verificação do preview

No navegador, com o URL de preview:

1. Abra `/` em janela privada.
2. Navegue para uma rota interna suportada pelo frontend.
3. Atualize essa rota diretamente.
4. Abra URL de um asset real e confirme que ele não recebe HTML da SPA.
5. Faça login no ambiente de preview somente se ele tiver Clerk de preview.
6. Confirme que requests vão ao endpoint de preview permitido, não a produção.

Resultado esperado: a rota profunda recarrega e assets continuam sendo assets.
Falha comum: usar regra de redirect universal para esconder 404. Diagnóstico:
remova a regra, confirme que `dist/404.html` não existe e siga o padrão
nativo do Pages.

### Domínios, HTTPS e DNS F53-09

Depois de preview aceito:

1. Adicione `app.<domínio>` ao projeto Pages e conclua o registro DNS indicado.
2. Provisione proxy TLS na OCI e confirme que `api.<domínio>` possui certificado
   válido, cadeia confiável e hostname correto antes de direcionar clientes.
3. Crie o registro DNS de `api` com TTL conservador durante o piloto.
4. Verifique resolução de rede externa e conexão HTTPS sem ignorar certificado.
5. Registre certificado, expiração e responsável por renovação automática.
6. Só então altere `VITE_API_BASE_URL` de produção para o hostname estável.

Não exponha Uvicorn na Internet para obter TLS rapidamente. O proxy é o único
terminador HTTPS e deve encaminhar para API privada.

### CORS e origem do frontend

O Compose atual usa `FRONTEND_ORIGIN` e o valor local padrão. F53-09 deve fazer
a configuração de produção aceitar exatamente `https://app.<domínio>`.

1. Defina `FRONTEND_ORIGIN` como URL completa, sem adivinhar wildcard.
2. Permita os métodos e headers realmente usados, incluindo `Authorization` se
   o frontend enviar Bearer token.
3. Faça preflight `OPTIONS` de uma origem permitida e confirme headers de
   resposta.
4. Repita a request a partir de origem não permitida e confirme ausência de
   acesso CORS, sem usar isso como autenticação.
5. Teste host, scheme e porta diferentes, inclusive `http` e subdomínio typo.

Falha comum: URL de Pages termina com slash enquanto a allowlist espera outro
formato. Diagnóstico: compare o header `Origin` real do browser ao valor de
configuração; normalize na implementação, não por wildcard amplo.

## Jobs e janelas finitas

### Limite do que existe hoje

O worker atual agenda coleta, normalização, avaliação, análise e retenções. O
script `scripts/collect.py` é uma CLI finita de coleta e não um executor de
pipeline completo. Não use uma invocação manual de `collect.py` como prova de
que todas as etapas rodaram.

F53-10 deve definir o pipeline finito completo, sua ordem, entradas, resultado
e evidência. Antes dele, mantenha jobs cloud desabilitados.

### Desenho de uma execução finita

Uma execução futura precisa declarar:

| Campo | Exemplo de significado | Gate |
| --- | --- | --- |
| Run ID | Correlação de todos os logs | Consultável após o término. |
| Janela | Hora limite em UTC | Não inicia perto demais do deadline. |
| Fontes | Conjunto autorizado | Não autoativa descoberta. |
| Concorrência | Limite por host/pipeline | Medido, não inferido. |
| Lease/fencing | Dono do trabalho | Impede sobreposição e escrita antiga. |
| Resultado | Sucesso, parcial, falha, timeout | Não fecha ausências em parcial. |
| Próxima ação | Retentar, pausar, investigar | Não repete tempestivamente. |

Uma coleta parcial não prova ausência de vaga. Um 304 valida uma representação,
mas não fecha cobertura completa. Mantenha essa semântica também quando jobs
saírem do laptop para a OCI.

### Timer e systemd: desenho, não arquivo pronto

Não há unit systemd ou timer no repositório. F53-11 deve criar, revisar e testar
o template. Até isso acontecer, nenhum snippet abaixo é para colar em `/etc`.

O template precisa contemplar:

1. Serviço `Type=oneshot` que chama o runner de pipeline implementado.
2. Usuário dedicado e diretório de trabalho explícito na VM Ubuntu.
3. Arquivo de ambiente protegido, não variáveis inseridas no unit.
4. Timeout maior que a janela segura, mas finito e justificado por medição.
5. `ExecStop` ou mecanismo equivalente que solicite shutdown gracioso.
6. Timer que não dispara nova instância se a anterior ainda está em término.
7. Logs identificados por run ID e retenção controlada.
8. Estado observável que mostre início, deadline, término e resultado.

Não force `SIGKILL` para encerrar uma coleta apenas porque a janela acabou. O
processo deve parar de aceitar novo trabalho, concluir seção crítica ou marcar
o run como interrompido, renovar/liberar lease conforme implementação e sair.
Se o desligamento gracioso exceder o prazo, pagine o operador e preserve logs
antes de qualquer ação destrutiva.

### Ensaiar a janela

Em ambiente isolado e depois que F53-10/F53-11 existirem:

1. Rode uma janela com fonte fixture ou subconjunto aprovado.
2. Registre início, cada estágio, fim e uso de CPU/RAM/conexões.
3. Simule deadline durante trabalho não crítico e confirme shutdown gracioso.
4. Tente iniciar segundo run e confirme claim/lease/fencing recusar ou aguardar.
5. Simule falha Neon e confirme que o estado não marca coleta completa.
6. Compare contagens e eventos com o resultado esperado do teste.

Resultado esperado: a execução termina, não sobrepõe outra e deixa evidência
suficiente para explicar falha. Um serviço "active" não é evidência desse gate.

## Capacidade, retenção e backups

### F53-12: RAM, CPU, conexões e armazenamento

Comece com uma API e no máximo uma execução de job por vez. Meça antes de
alterar concorrência, pool, swap, discos ou daemons.

Para cada piloto, registre:

- RSS máximo de API, worker, proxy e containers auxiliares;
- CPU média e picos por etapa;
- memória disponível e ocorrência de OOM;
- conexões Neon abertas, espera de pool e erros de timeout;
- tamanho de logs, imagens, exports, dumps e volume de boot;
- CU-h, armazenamento Neon e pedidos Object Storage;
- duração de liveness/readiness e se tocaram banco.

Se RAM esgotar, pare jobs, colete evidência e reduza escopo. Não adicione swap
ou aumente máquina automaticamente: ambos alteram custo e mascaram leak ou
concorrência inadequada.

### F53-13: retenção de dados

A retenção de payload bruto é 365 dias no comportamento atual. Uma redução para
30 dias é condicional a evidência de backup/restauração, proveniência preservada
e proteção do registro relacionado. Não altere esse valor apenas para reduzir
uso de armazenamento.

As avaliações têm retenção de sete dias opt-in conforme configuração de worker.
Confirme qual job está habilitado no ambiente antes de declarar que elas serão
apagadas. Um TTL de cache expira cache; não apaga linhas persistidas, exports,
dumps ou proveniência de CRM.

Antes de mudar retenção:

1. Liste tabelas, payloads, exports e backups afetados.
2. Identifique referência de proveniência que precisa sobreviver.
3. Restaure backup isolado e compare schema, contagens e amostra de relações.
4. Meça economia real de dados após simulação.
5. Aplique primeiro em ambiente isolado e observe um ciclo inteiro.
6. Registre aprovação, versão de política e plano de reversão.

### F53-14: backup e restore

Os scripts existentes já definem flags; use somente suas opções verificadas:

```text
scripts/backup.py --output-dir "<diretório>" --label "<rótulo>" --prune-days "<dias>"
scripts/restore_check.py --dump "<arquivo>" --backup-dir "<diretório>"
```

Use `--keep` somente para diagnóstico aprovado: ele preserva o database scratch
e pode consumir quota. Registre o nome, o motivo e a data de remoção antes de
habilitá-lo; o fluxo normal deixa o script remover o scratch ao finalizar.

Não use `--allow-missing-manifest` como evidência forte de recuperação. Essa
opção relaxa uma garantia e precisa de justificativa explícita se for usada em
um diagnóstico.

O código atual entrega a DSN a `pg_dump` e `pg_restore` por argumento de
processo. Em host compartilhado, isso pode expor senha para inspeção de processo.
F53-14 precisa adaptar o caminho cloud para `PGPASSFILE`, `PGSERVICE` ou ambiente
protegido equivalente, sem URL secreta no argv. Antes do piloto, verifique logs,
histórico do shell e processos com uma credencial de teste; não aceite esse
risco apenas porque o dump e o restore retornam sucesso.

O procedimento alvo é:

1. Gere dump lógico com URL direta somente após o gate de Neon confirmar a URL.
2. Armazene localmente em diretório protegido pelo tempo mínimo necessário.
3. Calcule e registre checksum sem publicar o conteúdo.
4. Criptografe antes de enviar para bucket OCI privado.
5. Envie cópia independente criptografada para controle do dono, separada da
   conta operacional quando possível.
6. Verifique objeto, tamanho, checksum e idade do backup no destino.
7. Execute `restore_check.py` contra destino isolado. O script pode criar e
   derrubar database, portanto forneça uma URL base com privilégios e ambiente
   adequados; sufixo `_test` por si só não prova que um destino remoto é seguro.
8. Compare schema, migrations, contagens e relações essenciais.
9. Registre RPO, RTO medido, dump usado e resultado. Só então avalie pruning.

#### Restore verificável e seguro

O import de recuperação usa um database novo, vazio e isolado, criado sob a
conta de teste aprovada. Nunca aponte `pg_restore` ao banco de origem, ao banco
operacional ou a um nome apenas parecido. Antes de executar, registre em tela de
leitura host/branch, database, dono e confirmação de destino vazio.

Depois que F53-14 implementar credencial sem segredo em argv, use um serviço
libpq protegido (`PGSERVICE` e `PGPASSFILE`) ou equivalente. O exemplo abaixo
é o procedimento alvo, não um comando disponível antes dessa adaptação:

```ini
# /etc/opportunity-radar/pg_service.conf (0600; sem password)
[opportunity_radar_restore]
host=<hostname-neon-aprovado>
dbname=<database-novo-vazio>
user=<usuario-restauracao>
sslmode=verify-full
sslrootcert=/etc/opportunity-radar/neon-ca.pem
```

```bash
export PGSERVICE=opportunity_radar_restore
export PGSERVICEFILE=/etc/opportunity-radar/pg_service.conf
export PGPASSFILE=/etc/opportunity-radar/pgpass
export PGSSLMODE=verify-full
export PGSSLROOTCERT=/etc/opportunity-radar/neon-ca.pem
DUMP_PATH='<caminho-para-dump-validado>'
test -s "$DUMP_PATH"
pg_restore --exit-on-error --no-owner --no-privileges \
  --dbname='service=opportunity_radar_restore' "$DUMP_PATH"
psql 'service=opportunity_radar_restore' -v ON_ERROR_STOP=1 -c \
  "SELECT current_database(), current_setting('server_version');"
```

1. Confirme permissões `0600`, dono e caminho único de `pg_service.conf`, CA e
   `pgpass`; confirme que nenhum comando, log ou histórico contém a senha.
2. Verifique que `verify-full` aceita apenas hostname Neon aprovado e CA testada.
   Erro de cadeia ou hostname encerra o passo antes de queries.
3. Valide hash/tamanho/manifesto antes de `pg_restore`; não use
   `--allow-missing-manifest` para aprovar recuperação.
4. Rode `pg_restore` com `--exit-on-error` e pare no primeiro erro. Não acrescente
   `--clean` ou `--create` a um destino que não tenha sido validado como vazio.
5. Consulte versão PostgreSQL, `alembic_version`, extensões e schemas esperados;
   compare contagens e relações essenciais com a origem congelada.
6. Registre duração, dump/manifesto por identificador mascarado, checks e RTO.

Este import mantém o destino isolado para inspeção/aceite; ele não cria scratch
nem usa `--keep`. Em fluxo separado de ensaio, `scripts/restore_check.py` pode
criar e derrubar seu próprio database scratch. Só nesse script, `--keep` é opção
de diagnóstico aprovada com prazo e responsável; o fluxo normal permite cleanup
do script ao concluir.

Falha de checksum, manifest, `pg_restore`, migration, extensão ou contagem
interrompe o restore. Preserve a evidência sanitizada, descarte apenas o alvo
isolado e investigue; não sobrescreva o banco operacional para tentar novamente.

Mantenha `--prune-days=0` enquanto o restore não for demonstrado. O alvo de
retenção deve considerar RPO, custo, volume e ao menos um restore periódico.

### Criptografia e acesso

Proteja backup em trânsito com TLS e em repouso com criptografia gerenciada ou
chave controlada documentada. A chave de criptografia, URL do banco e credencial
de bucket têm donos e rotação separada. Não deixe uma cópia restaurável e sua
chave no mesmo checkout ou na mesma VM sem proteção adicional.

Teste perda de uma credencial de leitura e o caminho de recuperação de acesso.
Não teste perda de dados apagando backup de produção.

## Testes, aceite e operação

### F53-15: testes isolados

O repositório exige três condições para integração de banco:

```text
RUN_DATABASE_INTEGRATION=1
DATABASE_INTEGRATION_ISOLATED=1
DATABASE_URL=<database de teste isolado>
```

O guard também exige que o nome de database termine em `_test`. Isso é uma
barreira necessária, não autorização para apontar a suite ao Neon operacional.
Use instância, projeto/branch, credenciais e volume exclusivos do teste; os
dados de produção nunca entram no compose de CI.

Hoje há cenários end-to-end que fazem leitura e escrita anônimas. Ao introduzir
Clerk, F53-15 deve adaptá-los para fixture offline de JWT/JWKS e sujeito dono da
instância isolada. O CI não usa chave live, não consulta JWKS público e não cria
um bypass de autenticação de produção para tornar esses testes verdes.

Antes de executar a suite:

1. Inspecione a URL sem imprimir senha e confirme host e database de teste.
2. Confirme `RUN_DATABASE_INTEGRATION=1` e
   `DATABASE_INTEGRATION_ISOLATED=1`.
3. Use nome único de projeto Compose e volume novo para evitar colisão local.
4. Execute a suite conforme workflow de CI ou runbook do repositório.
5. Colete apenas resultado sanitizado, versão de migration e hash do commit.
6. Derrube recursos de teste conforme procedimento do próprio ambiente, nunca
   com comando amplo que possa atingir compose operacional.

#### Fixture offline de Clerk no CI

Depois de F53-07 implementar o validador e F53-15 adicionar fixtures, mantenha
uma chave de teste e JWKS de teste versionados somente se forem material público
de fixture. A chave privada de produção, `sk_`, sessão de navegador e URL JWKS
live nunca entram no workflow. O trecho é contrato futuro para
`.github/workflows/pipeline.yml`; ajuste nomes de testes depois de existirem.

```yaml
- name: Run isolated database and JWT integration tests
  env:
    RUN_DATABASE_INTEGRATION: "1"
    DATABASE_INTEGRATION_ISOLATED: "1"
    DATABASE_URL: ${{ secrets.CI_ISOLATED_DATABASE_URL }}
    CLERK_TEST_ISSUER: https://clerk.test.invalid
    CLERK_TEST_JWKS_PATH: tests/fixtures/auth/jwks.json
    CLERK_TEST_OWNER_SUB: user_test_owner
  run: pytest -q tests/backend/presentation/test_auth.py tests/integration
```

1. Faça o secret `CI_ISOLATED_DATABASE_URL` apontar a projeto/branch e database
   exclusivamente de teste cujo nome termine em `_test`; não reutilize Neon ou
   volume operacional.
2. Gere tokens localmente durante o teste com header `alg`/`kid` da fixture e
   payload `iss`, `sub`, `exp`, `nbf`, além de `aud`/`azp` se contratados.
3. Teste dono válido, ausência de token, assinatura/issuer/algoritmo inválidos,
   expiração, `nbf` futuro, outro `sub` e rotação de `kid` sem rede externa.
4. Faça o job falhar se o fixture tentar buscar JWKS público, se o guard de DB
   negar isolamento ou se a URL não terminar em `_test`.
5. Publique somente status, commit, migration e nomes de testes. Mascare URL,
   headers, token e qualquer output do cliente PostgreSQL.

Esse YAML não pode ser copiado como prova de implementação: F53-15 deve criar
os caminhos/fixtures e validar a sintaxe do workflow antes de ativá-lo.

### Testes negativos de hospedagem

F53-16 deve executar e registrar, no mínimo:

| Cenário | Resultado de aceite |
| --- | --- |
| API sem token | 401 sem dados. |
| Token adulterado, expirado e `nbf` futuro | 401. |
| Usuário Clerk válido fora da allowlist | 403. |
| Origem CORS não autorizada | Browser não ganha acesso. |
| Certificado ou hostname inválido | Cliente não aceita TLS. |
| Neon indisponível | API/worker degradam sem corrupção. |
| Job sobreposto | Lease/fence protege escrita. |
| Deadline de job | Parada é graciosa e registrada. |
| Dump corrompido | Restore falha antes de substituir dados. |
| Restore isolado | Schema e dados essenciais conferem. |
| Pages rota profunda | Reload funciona, asset real não vira HTML. |
| Digest errado | Deploy é bloqueado antes de subir container. |

Uma checagem de `/health/live` não substitui essas provas. Ela prova apenas que
o processo HTTP responde sem banco e sem detalhes de auth; DB, autorização,
backup e pipeline precisam de suas próprias evidências.

### F53-17: monitoramento e incidente

Configure alertas antes de tráfego real para:

- uso de CU-h em trajetória acima da meta de 80;
- armazenamento Neon, bloco OCI, Object Storage e logs em crescimento;
- RAM baixa, OOM, CPU sustentada e disco cheio na VM;
- conexões/timeout de banco e migration falha;
- certificado próximo da expiração e DNS divergente;
- jobs atrasados, deadline excedido, lease vencido e run parcial;
- idade excessiva de backup e falha de restore;
- taxa de 401/403 anormal, sem registrar credenciais ou JWTs.

#### Alarmes, destinatário e prova de entrega

Antes de configurar um alarme, confira plano, quotas e preço atuais de
Monitoring/Notifications na tenancy; não assuma que alertas ou entregas são
gratuitos e ilimitados. No console OCI, crie um tópico Notifications e adicione
e confirme e-mail do responsável operacional fora do repositório.

1. Abra **Observability & Management > Monitoring > Alarm Definitions** e use
   **Create Alarm** no compartment do piloto.
2. Escolha namespace, métrica e dimensão do recurso exato, como OCID da VM;
   não use métrica agregada de outro ambiente.
3. Defina condição, trigger e duração. Para RAM/CPU/disco, escolha threshold
   observável; para backup/job, publique métrica/evento somente após F53-10–14
   existirem em vez de inferir por HTTP 200.
4. Selecione o tópico e a subscription confirmada, configure repetição/cadência
   e habilite o alarme. Registre dono, canal, threshold, duração e custo/limite.
5. No piloto, use uma regra segura e disparável ou métrica de teste para produzir
   estado `FIRING`; confirme recebimento pelo destinatário e arquive hora/ID
   mascarados. Em seguida, restaure threshold operacional e confirme `OK`.
6. Revise semanalmente alertas de custo/recursos e após cada mudança de VM,
   banco, DNS, timer ou destinatário. Registre ausência de alerta como incidente.

Para Neon, Cloudflare, Clerk e DNS, use o mecanismo oficial que exista na conta
ou checklist manual com destinatário e cadência equivalentes. Cada alerta deve
deixar prova de criação, transição `FIRING`, entrega e retorno a `OK`; dashboard
sem destinatário não satisfaz F53-17.

Para incidente, o operador deve:

1. Declarar severidade, ambiente, hora e dono.
2. Congelar mudanças e salvar logs sanitizados, dashboard e digest ativo.
3. Pausar timers/worker se há risco de escrita incorreta ou custo contínuo.
4. Verificar alcance: API, Pages, auth, Neon, dados e backups.
5. Escolher rollback ou correção a partir de evidência, nunca por reinício em
   loop.
6. Registrar causa, impacto, ações, recuperação e follow-up.

### Guardas de teardown

Destruir infraestrutura exige gate separado. Antes de remover VM, database,
bucket, stack, DNS ou aplicação:

1. Confirme ambiente, tenancy, project ID e recursos exatos em tela de leitura.
2. Pause deploys e jobs; aguarde jobs ativos concluírem ou registrem parada.
3. Faça backup, checksum e restore recente verificável.
4. Exporte inventário de DNS, state e versões necessárias para reconstrução.
5. Obtenha aprovação do dono dos dados.
6. Remova somente recurso aprovado, um grupo por vez.
7. Confirme que o recurso removido não hospeda domínio, dados ou credenciais de
   outro ambiente.

Não use destroy abrangente contra tenancy, root de storage ou diretório sem
lista validada de alvos. O state e os logs de auditoria sobrevivem conforme a
política de retenção antes da remoção final.

## Cutover, rollback e recuperação

### Preparação para cutover F53-18

O cutover só começa depois de F53-01 a F53-17 terem suas evidências aceitas.
Agende uma janela de escrita controlada e notifique apenas os responsáveis
necessários. O objetivo é preservar consistência, não maximizar velocidade.

Antes da janela:

1. Escolha e registre digest novo e digest anterior.
2. Registre DNS antigo, TTL, destino Pages e origem da API.
3. Verifique backup recente com checksum e restore isolado bem-sucedido.
4. Verifique migration candidata em ambiente equivalente.
5. Confirme queue vazia ou política clara para trabalho em trânsito.
6. Prepare dashboard para contagens, erros, RAM, CU-h e jobs.
7. Confirme que o operador de rollback está disponível durante toda a janela.

### Sequência de cutover

1. Coloque todos os writers em quiescência: pause jobs, timers, automações e
   ações de escrita da API. Retire a API de escrita do balanceamento ou aplique
   modo de manutenção implementado; não force encerramento de job ativo.
2. Aguarde confirmação do último job e registre run ID/estado final.
3. Faça dump final, valide checksum e transfira-o por canal protegido. Não
   remova a cópia anterior nem deixe a URL do banco em argv, log ou ticket.
4. Restaure ou importe o dump no destino Neon novo, vazio e previamente
   validado, usando a URL direta aprovada e o método seguro de credencial de
   F53-14. Não aponte esse passo ao banco de origem ou ao banco operacional.
5. Confirme schema, versão Alembic, extensões, contagens e relações no destino.
   Compare com a origem ainda congelada e investigue qualquer divergência antes
   de migrar ou liberar tráfego.
6. Execute migration única no destino somente se a versão do dump exigir a
   migration candidata; verifique a versão Alembic e repita checks críticos.
7. Suba API no digest novo, execute liveness/readiness apropriados e testes de
   auth, CORS e rota protegida.
8. Habilite Pages/`app` e depois direcione `api` conforme a estratégia DNS
   aprovada. Confirme HTTPS de rede externa.
9. Faça smoke test com dono permitido, token inválido, rota pública e rota
   profunda do frontend.
10. Reative writers/jobs somente após a matriz e métricas iniciais aceitarem.
11. Monitore durante período definido e registre contagens após reativação.

### Critérios de abortar

Aborte e volte à fase segura se ocorrer qualquer um destes:

- migration falha ou schema não corresponde à versão esperada;
- comparação de contagens aponta divergência sem explicação;
- API aceita request sem JWT válido ou nega dono permitido;
- certificado/DNS envia tráfego a destino errado;
- RAM, conexões ou CU-h excedem limite sem diagnóstico;
- job perde lease, sobrepõe execução ou marca parcial como completa;
- backup final não tem checksum ou restore comprovado.

### Rollback sem perda adicional de dados

Rollback é uma operação de dados, não apenas mudar DNS. Faça nesta ordem:

1. Pare writers e jobs no destino novo para impedir divergência adicional.
2. Preserve logs, digest, migration, contagens e horário de corte.
3. Reaponte Pages/DNS ao destino anterior somente se ele ainda tiver dados
   consistentes e compatíveis com a migration executada.
4. Se houve escrita no destino novo, não descarte esses dados. Determine se
   existe reversão de migration suportada, reconciliação ou restore para alvo
   novo antes de aceitar perda.
5. Restaure backup apenas em destino isolado primeiro e valide schema/contagens.
6. Retome writers somente quando uma fonte de verdade e uma linha do tempo de
   dados forem aprovadas pelo dono.
7. Abra incidente e mantenha o ambiente falho preservado até terminar análise.

Não faça downgrade de migration ou restaure sobre produção como reflexo. A
prova de que rollback não perdeu dados é a comparação registrada de dados antes,
depois e após recuperação.

## Sequência dos cards

O [índice do roadmap 53](53-roadmap-hospedagem/README.md) é a fonte única para
ordem, dependências e saída verificável de F53-01 a F53-18. Este runbook detalha
o procedimento operacional e não replica a tabela: assim, uma alteração de
dependência não pode deixar duas fontes divergentes.

F53-18 é o único card que pode declarar o piloto hospedado após a evidência de
cutover. Nenhum card anterior cria autorização para afirmar que produção está
ativa, que a franquia cobre o uso, ou que dados podem ser apagados.
