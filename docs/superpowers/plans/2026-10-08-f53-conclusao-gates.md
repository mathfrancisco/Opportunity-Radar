# F53 — plano de conclusão e gates de implementação

> **Para agentes implementadores:** executar uma tarefa por vez na árvore existente e marcar caixas somente com evidência registrada. Usar `superpowers:executing-plans` para os pacotes locais. Tarefas de provedor ficam bloqueadas até sua autorização específica; este plano não autoriza essas ações.

**Objetivo:** Recuperar e integrar o trabalho local já iniciado, fechar os controles locais de F53 e percorrer F53-01–F53-18 em ordem de dependência, sem afirmar hospedagem aceita antes de evidência datada e gates do dono.

**Arquitetura:** Preservar a branch e as alterações P1 existentes; estabilizar dashboard e worker antes de validar tenancy A/B e auth contra a API integrada. Depois fechar os pacotes locais de frontend e cada card F53, mantendo aquisição determinística separada de enrichments opcionais e usando jobs finitos. Recursos de provedor, dados reais e release só entram na etapa em que houver autorização e os gates anteriores estiverem provados.

**Stack:** FastAPI, SQLAlchemy/Alembic, PostgreSQL, pytest, React/Vite/TypeScript, Clerk SDK já presente, Vitest/Playwright, Docker Compose, Terraform OCI futuro, Neon e Cloudflare Pages.

**Fontes:** `docs/53-plano-hospedagem-cloudflare-oracle-neon-clerk.md`; `docs/53-roadmap-hospedagem/README.md`; cards `docs/53-roadmap-hospedagem/cards/f53-01-*.md` a `f53-18-*.md`; `docs/superpowers/plans/2026-10-08-auth-tenancy-lp.md`; `docs/54-spec-redesign-completo-frontend.md`.

## Restrições globais

- Preservar branch, commits, worktrees, alterações staged/unstaged e arquivos untracked; não limpar `.tmp/`, `.worktrees/` nem os arquivos de trabalho existentes.
- A fotografia inicial verificada é `feat/f54-redesign-frontend`, HEAD `e70cee8599cf1a3c1a98caa2d76adab96183ccdb`, 14 commits à frente do upstream observado e zero atrás; não fazer fetch, push ou atualização de PR neste plano. Cada pacote local aprovado pode ter um commit pequeno e exclusivo depois de revisão independente, testes focados, Ruff e `git diff --check`.
- As 16 alterações P1 existentes e suas responsabilidades estão identificadas no mapa abaixo. `src/opportunity_radar/matching/currency.py` pertence exclusivamente ao slice worker indicado neste plano; não repartir a edição desse arquivo.
- Implementadores trabalham sequencialmente na mesma árvore para preservar o estado local. Fazer revisão de cada pacote antes de passar ao seguinte; workers não alteram simultaneamente arquivos compartilhados.
- Não executar teste de integração contra o banco padrão do Compose. A integração exige `RUN_DATABASE_INTEGRATION=1`, `DATABASE_INTEGRATION_ISOLATED=1` e `DATABASE_URL` de banco isolado terminado em `_test`; confirmar também que o servidor de destino não é operacional. Executar a suíte completa apenas uma vez, depois da última edição.
- Nunca mostrar, gravar ou versionar secrets, bearer/JWT, DSN, `.env`, dump, state, IDs reais, e-mails, IPs, URLs privadas ou payloads pessoais. Clerk/JWKS em testes são fixtures locais sintéticas; não chamar issuer real.
- F53-16 usa dados de fixture exclusivamente. O ensaio local offline usa JWT/JWKS sintéticos; um piloto hospedado, se autorizado especificamente, usa esses mesmos dados de fixture com autenticação Clerk real. Nunca levar o signer offline de teste para cloud, nem usar dado real. F53-18 é a primeira janela que pode tratar dados reais, e somente após autorização separada e todos os gates anteriores.
- Sem aprovação registrada de teto/orçamento, conta e responsável, não criar conta, domínio, credencial, recurso OCI/Neon/Cloudflare/Clerk, regra DNS, CI secret, deployment ou workload pago. Nenhuma tarefa daqui autoriza produção, push ou mudança de PR.
- Neon: meta operacional `<=80 CU-h/mês` e `<1 GB`; valores exibidos em painéis devem ser medidos no momento, não inferidos de limites publicados. OCI A1 é alvo, sujeito a capacidade/quota real da tenancy. Nenhuma carga artificial, ping, polling, worker ou healthcheck para impedir suspensão.
- O Compose local inicia dependências do banco automaticamente se usado sem isolamento. Cada validação deve usar projeto exclusivo, imagens e overrides explicitamente seguros e URL `_test` validada; não executar literalmente um `docker compose run api` que possa subir o banco operacional.
- SPEC 54 WP6 e WP7 seguem pendentes até F53 entregue e autorizada. A implementação F54 não é escopo deste plano.

## Foco de revisão

- `_latest_assessments` com versão de perfil explícita: a seleção de UUID atual deve preservar o tipo/objeto esperado antes de acessar `.label`; cobrir versões ausente, atual e histórica em teste de query.
- Interrupção/retomada de coleta: run parcial não fecha ausência nem duplica efeito; cobrir interrupção depois de claim e retry idempotente no pacote worker/F53-10.
- Ownership: identidade A nunca lê nem altera dados pessoais de B por UUID conhecido; cobrir `404` para UUID estrangeiro, criação, atualização e exclusão em suites A/B isoladas. Usuário membro recebe `403` nas rotas globais/administrativas; métricas administrativas podem existir, mas agregados pessoais sempre usam somente `identity.sub`.
- Dashboard: `new_count` é calculado pelas assessments do perfil do dono, e moeda ativa pertence ao dono, nunca ao catálogo global. O overview de membro não retorna campos operacionais ou de terceiros.
- Auth: `GET /session` mínimo retorna apenas a capability autenticada `{is_owner}` se não existir contrato equivalente; não aceita `sub`, metadata ou role fornecidos pelo cliente para conceder owner.
- Migration: auditar a migration existente `20261008_0069` e seu downgrade deliberadamente recusado; confirmar que falha fechada não executa DDL nem remove ownership. Não criar migration adicional ou soltar constraints/ownership sem falha reproduzida e revisão do pacote.
- Identidade de navegador: sessão ausente ou expirada não dispara queries privadas; identidade/metadata/browser não pode conceder owner; cobrir spy de requests e rotas diretas.
- Alvos de backup/import: URL de produção, manifesto/hash inválido, senha em argv, destino não vazio ou extensão ausente falha antes de escrita; cobrir guards em fixture e banco isolado.

---

## Estado observado antes da execução

| Área | Estado | Evidência e limite |
| --- | --- | --- |
| Árvore | Trabalho local presente na branch listada acima | `git status --short --branch`, `git log -1 --oneline`; 16 arquivos modificados e diversos untracked/worktrees preservados. |
| P1 dashboard/worker | Alterações locais em revisão/integração; não aceitas | `dashboard/queries.py`, `dashboard/saved_searches.py`, `presentation/http/dashboard.py`, `acquisition/service.py`, `matching/currency.py`, `opportunities/suggestions.py`, `worker.py` e testes relacionados estão modificados. |
| Auth/tenancy | Plano de auth existe; código-base integrado tem mudanças anteriores que precisam de auditoria contra esse plano | `docs/superpowers/plans/2026-10-08-auth-tenancy-lp.md`; frontend `@clerk/react` já existe, mas `apps/web/src/auth/` ainda não existe e há provider/controles globais; rotas atuais precisam ser comparadas aos guards e à LP pública previstos. Nenhum aceite F53 decorre disso. |
| F53 | Nenhum card aceito; 01, 07, 08, 10, 14 e 15 têm preparação local em andamento | Inventário/revisão local e slices existentes não são aceite de card. Não há `docs/53-roadmap-hospedagem/evidencias/`. A data de 2026-10-06 no índice é histórica e deve ser atualizada só por evidência. |
| Infraestrutura externa | Sem prova atual de orçamento aprovado, quota/owner de conta ou recurso criado | Logo F53-01/02/03 e todos os atos de provedor continuam bloqueados. Não inferir preço, quota ou capacidade atuais. |
| F53-14 | Risco de credencial confirmado no código-base: backup inclui DSN em argv; restore usa `--dbname=DSN` | Referências observadas `scripts/backup.py:104` e `scripts/restore_check.py:101`; há worktree separado `f53-14-backup` com alteração própria: preservar e revisar/adaptar, não sobrescrever nem assumir integrado. |
| F53-10 | Implementação futura não existe no branch atual | `scripts/run_pipeline_once.py` ainda não existe; outro worktree sujo possui alterações em services e `platform/pipeline.py`: preservar e inspecionar antes de integrar. |
| F54 | WP6/WP7 ainda não podem iniciar | SPEC 54 exige F53 entregue/aceita para auth real, smoke, preview e release. Nenhum dos AC54-01..10 está considerado aceito por este plano. |

## Mapa exato de arquivos e responsabilidades

| Pacote | Arquivos próprios ou tocados | Responsabilidade / limite |
| --- | --- | --- |
| Pré-voo P1 | `src/opportunity_radar/dashboard/queries.py`; `dashboard/saved_searches.py`; `presentation/http/dashboard.py`; `tests/backend/dashboard/test_inbox_cost_shape.py`; `test_inbox_pointer.py`; `test_queries.py`; `test_recency_mirror_integration.py`; `test_saved_searches.py`; `test_search_filters.py`; `test_search_fulltext.py` | Fechar query/API/saved-searches e regressões de dashboard nas edições existentes. Não reverter as edições ou alargar API sem contrato. |
| Pré-voo worker | `src/opportunity_radar/acquisition/service.py`; `matching/currency.py`; `opportunities/suggestions.py`; `worker.py`; `tests/backend/opportunities/test_suggestions.py`; `tests/backend/test_worker.py` | Integrar o slice worker de forma sequencial. `matching/currency.py` tem um único dono de edição nesta fase. |
| Auth Package 1 | `src/opportunity_radar/platform/config.py`; `src/opportunity_radar/presentation/http/auth.py`; `presentation/http/routes.py`; `presentation/http/app.py`; `tests/backend/http/test_auth.py`; `tests/backend/test_health.py` | Validação offline de JWT/JWKS, identidade imutável e separação explícita de rotas públicas/privadas. Alinhar com código atual em vez de duplicá-lo. |
| Auth Package 2 | Modelos pessoais encontrados pelo inventário; migration existente `20261008_0069`; `tests/backend/migrations/test_owner_sub_tenancy.py` | Auditar colunas/índices e downgrade recusado fail-closed em banco `_test`; não atribuir dono a catálogo global, criar migration nem remover ownership sem defeito reproduzido e revisão. |
| Auth Package 3 | Rotas/services/repositories de profile, pipeline, matching, dashboard, opportunities, acquisition, companies; testes HTTP por grupo | Aplicar `RequestIdentity.sub` em dados pessoais, owner em operações globais, catálogo read-only para autenticados; A/B. Não editar módulos paralelamente. |
| Auth Package 4 / F53-08 | `apps/web/src/main.tsx`; `app/App.tsx`; `lib/api.ts`; novo `auth/*`; nova `routes/LandingPage.tsx`; `components/Sidebar.tsx`; testes React e `tests/e2e/browser/auth-guards.spec.ts` | Clerk condicional, token por requisição, LP pública, guards de UX e navegação. A API segue autoridade. Preservar skip link, Escape, foco e mobile drawer. |
| Auth Package 5 | `presentation/http/dashboard.py` e query/service de dashboard; `apps/web/src/routes/OverviewPage.tsx`; `features/dashboard/*`; testes backend/frontend | Projeção ordinária sem diagnóstico operacional; não buscar payload de owner e escondê-lo na UI. |
| Auth Package 6 | `.env.example`; `compose.yaml`; `compose.dev.yaml`; `apps/web/.env.example` se aplicável; guia operacional estreito | Nomes/placeholders somente e orientação segura; sem valores reais. |
| F53-01 | Apenas evidência pós-autorização em `docs/53-roadmap-hospedagem/evidencias/f53-01-baseline-<data>.md` | Inventário, orçamento/moeda/aprovador, recuperação, medição local e painel redigidos; sem código ou criação de recurso. Diretório ainda não existe. |
| F53-02 | Evidência redigida; mapa futuro de hostname em configuração apenas depois dos cards de código | Propriedade e rollback de domínio/DNS/Clerk; não alterar DNS enquanto bloqueado. |
| F53-03 | Novo `infra/terraform/oci/{providers,versions,variables,outputs,network,compute,iam,dns}.tf`, `envs/pilot.tfvars.example`, `README.md` conforme runbook | State/lock/IAM e plan revisado. Exemplos sem secret; bootstrap/applies externos exigem aprovação separada. |
| F53-04 | `infra/terraform/oci/*.tf`, exemplo de inputs e evidência de plan | VM A1 2 OCPU/12 GB como alvo sujeito à quota, boot 50 GB, firewall mínimo, sem porta DB. Não aplicar automaticamente. |
| F53-05 | Dockerfiles de API/worker existentes, novo `compose.cloud.yaml`, contexto `.dockerignore` e referências da imagem | Build ARM64 e Compose só com migration, API, worker finito e proxy; sem PostgreSQL, Redis ou frontend runtime. Evitar sobreposição com CI, que pertence ao F53-15. |
| F53-06 | `scripts/backup.py`, `scripts/restore_check.py` somente para compatibilidade e teste piloto isolado; suites PostgreSQL/Alembic | Inventário de schemas, extensões, timeout e restore de fixture. Não apontar para Neon operacional. |
| F53-07 | `platform/config.py`, `presentation/http/auth.py`, roteamento/app e testes de auth | JWT Clerk validado e dono comparado exclusivamente com `sub`; somente `/health/live` público. Auth local já existente será auditada e complementada, não substituída por fallback. |
| F53-08 | Arquivos frontend do Auth Package 4, `apps/web/package.json` apenas se comando atual exigir; guia de build Pages | Build root `apps/web`, `dist`, Clerk publishable e API HTTPS como únicos `VITE_*` permitidos. Criar/configurar Pages é ato externo bloqueado. |
| F53-09 | Proxy TLS/reverse proxy dentro de `compose.cloud.yaml` e configuração cloud associada; API CORS em `presentation/http/app.py`/config | HTTP→HTTPS, CORS origin exata, portas mínimas, `/health/live` sem DB. Cloud probes/scan externos só com autorização. |
| F53-10 | Novo `scripts/run_pipeline_once.py`; `src/opportunity_radar/platform/pipeline.py` ou módulo existente após inspeção; integração com `scripts/collect.py` e services; `tests/backend/test_pipeline_runner.py` novo | Ordem `collect_enabled_sources` → `normalize_opportunities` pendentes → `evaluate_pending`; deadline, claim/lease, SIGTERM e retomada. Não rodar continuamente. Não sobrescrever o worktree sujo F53-10. |
| F53-11 | Unidades/timer futuros em `infra/systemd/` e wrapper do runner, guia/evidência | Janela UTC finita, timeout menor que janela, sem catch-up ou conexão ociosa. Ativar timer no host é externo e bloqueado. |
| F53-12 | Limites futuros em `compose.cloud.yaml` e parâmetros realmente consumidos pelo código | Medir três janelas comparáveis antes de declarar CPU/RAM/pool. Não criar variável sem consumidor ou serviço auxiliar. |
| F53-13 | Job/módulo de retenção novo somente após lineage e testes de fixture; relatório dry-run; talvez schema/indices apenas se teste exigir | Preservar canonical, CRM, lineage, referências e item mais recente; aplicar a política proposta apenas depois de backup/restore validado e autorização explícita para dado real. |
| F53-14 | `scripts/backup.py`; `scripts/restore_check.py`; testes `tests/backend/` do backup/restore; docs de execução; adaptar o slice em `.worktrees/f53-14-backup` sem apagar seu trabalho | Remover DSN/senha de argv; `PGPASSFILE`/`PGSERVICE`, checksum/manifest, validação de destino antes de conectar, scratch isolado. Nenhum dump/cópia cloud nesta tarefa local. |
| F53-15 | Exclusivamente `.github/workflows/pipeline.yml`, fixtures offline/scripts de CI e configuração de manifest ARM | Teste fail-closed, JWT/JWKS offline, guard `_test`, arm64. Dono único de CI e manifesto/build; não editar esse workflow em F53-05 ou outras tarefas. |
| F53-16 | Smoke/tests e evidência `evidencias/f53-16-aceite-<data>.md`; runner e Pages somente leitura durante piloto | Smoke local usa JWT/JWKS offline e dados sintéticos; aceite hospedado autorizado usa os mesmos dados de fixture com Clerk real. Nunca levar signer offline à cloud nem fechar o card pelo smoke local. |
| F53-17 | Definição operacional de alarmes/monitoramento e evidência `evidencias/f53-17-incidente-<data>.md` | Testar alerta/incidente e recuperação sem credenciais em logs; alarmes OCI/email reais são gate externo. |
| F53-18 | Runbook de import/cutover, scripts de verificação e evidência `evidencias/f53-18-cutover-<data>.md` | Primeira etapa potencial com dados reais. Freeze writers, cópia criptografada, target novo/vazio, `pg_restore` sem `--clean`, conferências e decisão humana de reconciliar. Não executar sem aprovação separada. |

---

## Sequência executável

### Etapa 0 — preservar a árvore e validar o ponto de partida

**Arquivos:** nenhum para editar. Inspecionar os arquivos P1, diff de cada worktree relevante, branches, arquivos untracked e testes existentes; conferir `git status --short --branch` e `git worktree list --porcelain`. Não resetar, stashar, limpar nem cherry-pick nesta etapa. Registrar snapshot textual redigido da revisão, nomes dos arquivos e hashes sem incluir valores de env.

- [ ] Confirmar que o HEAD ainda é `e70cee8599cf1a3c1a98caa2d76adab96183ccdb` e que todo trabalho observado continua presente.
- [ ] Inspecionar os diffs P1 e os slices sujos `f53-10-pipeline` e `f53-14-backup`; identificar commits/arquivos que podem ser aplicados sem descartar alterações. Não usar conteúdo do Compose para inferir banco seguro.
- [ ] Confirmar que `docs/53-roadmap-hospedagem/evidencias/` ainda não existe e não criar o diretório como prova fictícia.
- [ ] Saída: relatório curto local com inventário e dependências; nenhuma evidência operacional F53.

### Etapa 1A — recuperar P1 dashboard antes de auth integrada

**Dono:** Terra. **Arquivos:** somente o pacote Pré-voo P1 dashboard do mapa. Fazer uma mudança de cada vez. Rever os testes já alterados e corrigir a regressão de `_latest_assessments` para perfis explícitos, sem trocar o objeto por UUID quando o chamador usa `.label`. Depois consolidar queries/saved searches/API dashboard sem alargar o contrato.

- [ ] Executar os testes focados do dashboard (`tests/backend/dashboard/test_queries.py`, `test_saved_searches.py`, `test_search_filters.py`, `test_search_fulltext.py`, `test_inbox_pointer.py`, `test_inbox_cost_shape.py`) num projeto Compose exclusivo e banco descartável explicitamente isolado; não usar as tabelas operacionais.
- [ ] Incluir o teste de query de versão de perfil atual/ausente/histórica, o caso de duas atualizações recentes do espelho, `new_count` A/B e saved search B que tenta renomear/abrir/excluir UUID de A, preservando a linha de A.
- [ ] Cobrir `404` para UUID estrangeiro, overview de membro sem campos operacionais/de terceiro, e identidade explícita sem bypass de produção no teste de cost shape. Não duplicar o teste de tenancy inbox existente.
- [ ] Revisar mudanças em `tests/backend/dashboard/test_recency_mirror_integration.py` separadamente: só executar se o alvo confirmar `_test` antes da conexão.
- [ ] Rodar Ruff dos arquivos tocados e `git diff --check`; obter revisão independente `cavecrew-reviewer`, corrigir e retestar achados aplicáveis.
- [ ] Aceite: suites focalizadas passam; diff limitado aos arquivos do pacote; nenhuma chamada externa; sem mudança em `.github/workflows/pipeline.yml`. Depois da revisão, criar commit local pequeno somente destes arquivos.
- [ ] Evidência: comandos literais, saída/exit code, banco de destino mascarado e revisão do diff. Rollback: reverter apenas hunks deste pacote após guardar diffs locais; jamais restaurar arquivo inteiro em cima de alterações concorrentes.

### Etapa 1B — recuperar P1 worker antes de auth integrada

**Dono:** Luna. **Arquivos:** somente o pacote Pré-voo worker do mapa; `matching/currency.py` tem um único dono. Consolidar acquisition, currency, suggestions e worker contra fixtures offline, sem tocar dashboard.

- [ ] Executar `tests/backend/opportunities/test_suggestions.py` e `tests/backend/test_worker.py`; provar idempotência e semântica parcial de coleta.
- [ ] Rodar Ruff dos arquivos tocados e `git diff --check`; obter revisão independente `cavecrew-reviewer`, corrigir e retestar achados aplicáveis.
- [ ] Aceite: testes focados passam, nenhuma chamada externa e diff limitado ao pacote. Depois da revisão, criar commit local pequeno somente destes arquivos.
- [ ] Evidência e rollback seguem as mesmas restrições de isolamento e de preservação da Etapa 1A.

### Etapa 2 — revisão integrada backend e A/B antes do frontend

**Arquivos:** Auth Packages 1–3 e somente o backend do Package 5; reutilizar o contrato de `docs/superpowers/plans/2026-10-08-auth-tenancy-lp.md`. Reconciliar esse plano com as mudanças auth já presentes no branch antes de editar: uma fonte de identidade no servidor, rotas privadas por padrão, `/health/live` como única rota pública mínima, ownership por `sub` validado e owner por configuração de servidor. A parte frontend do Package 5 fica na Etapa 3, após esta revisão conjunta e A/B.

- [ ] Depois dos commits/revisões independentes das Etapas 1A e 1B, fazer revisão conjunta de dashboard, worker e auth antes do frontend; confirmar `401` sem/credencial inválida, `403` para identidade normal em rotas owner e `200` válido para owner.
- [ ] Exercitar `owner_sub` A/B em profile, preferences, application/pipeline/history, saved searches/follow-ups e matches, cobrindo CRUD e UUID conhecido; dados pessoais sempre filtrados na query/repository e atribuídos na API.
- [ ] Testar rotas globais (sources/runs, homologation, administração de companies, status/operations e telemetria) como owner-only; catálogo público de oportunidades apenas leitura para usuário autenticado conforme matriz do plano de auth.
- [ ] Testar `/health/live` sem DB e exigir auth nas outras health/readiness/metrics; falha JWKS fecha as rotas privadas. Credenciais/JWT nunca aparecem em log.
- [ ] Auditar `20261008_0069` em banco isolado `_test`: upgrade, contagens antes/depois, índices e orphan checks; o downgrade deve ser recusado fail-closed antes de DDL e preservar ownership. Sem derivar usuário de email/perfil e sem classificar dados globais como pessoais.
- [ ] Rodar suites focadas e suites existentes de guard de integração antes da suíte completa final. Confirmar os três guards em `tests/backend/conftest.py`; caso de URL padrão deve falhar antes de conectar.
- [ ] Aceite: revisão independente cavecrew-reviewer por pacote e uma revisão conjunta; achados corrigidos e retestados. Evidência contém route matrix, resultado A/B e revisão Alembic, nunca DSN/ID real. Rollback: `0069` não faz downgrade; produção não é alvo de rollback local.

### Etapa 3 — integração frontend Clerk segura (código local F53-08)

**Arquivos:** Auth Package 4, parte frontend do Package 5 e, após a configuração auth estabilizar, Package 6. Preservar o SDK já declarado; não adicionar biblioteca sem incompatibilidade comprovada.

- [ ] Criar testes Vitest para `getToken()` imediatamente antes de cada requisição privada, header apenas em memória, ausência de armazenamento/localStorage, serialização e log do token.
- [ ] Tornar `ClerkProvider` condicional à chave pública. Sem chave, mostrar falha de configuração clara; nunca fingir usuário autenticado. Manter `/` disponível como LP pública sem Clerk configurado.
- [ ] No pacote auth/frontend, adicionar `GET /session` mínimo que retorne somente `{is_owner}` se a auditoria não achar capability equivalente; a identidade vem exclusivamente do token validado no servidor e o cliente não envia `sub`, metadata ou role para obter privilégio.
- [ ] Depois da configuração auth estabilizar, preparar os placeholders de `.env.example`/Compose e guia do operador do Package 6 sem valores reais; testar startup/config fail-closed localmente. Isso não cria conta, credencial, recurso externo ou autorização de deploy.
- [ ] Implementar callbacks e guards de UX: sessão anônima recebe LP/login; usuário autenticado é roteado para Overview; usuário comum vê Overview/Inbox/Pipeline/Profile; owner vê rotas operacionais. Não confiar em ID, metadata ou papel fornecido pelo browser.
- [ ] Proteger as dez rotas diretas e links profundos em E2E offline; verificar que uma resposta API `401/403` não vira sucesso visual.
- [ ] Testar navegação móvel/sidebar, skip link, fechar com Escape, foco/restauração, 320/360 px e ausência de polling adicional.
- [ ] Rodar testes focados Vitest e `cmd /c C:\nvm4w\nodejs\npm.cmd run check` em `apps/web`; E2E usa serviço local e fixtures sintéticas.
- [ ] Aceite: nenhuma rota privada consulta antes do estado auth, token não vaza, LP continua renderizando sem `VITE_CLERK_PUBLISHABLE_KEY`; evidência local. Rollback preserva LP/rotas sem contornar proteção server-side.

### Etapa 4 — F53-01: inventário e orçamento (P0, primeiro gate externo)

**Arquivos:** apenas evidência redigida em `docs/53-roadmap-hospedagem/evidencias/f53-01-baseline-<data>.md`, depois da autorização para consultar as contas/painéis. Nenhum código ou recurso.

- [ ] Compilar owner e recuperação para OCI, Cloudflare, Neon, Clerk e registrador; registrar mês/moeda/teto aprovado e responsáveis por custo.
- [ ] Consultar painéis atuais com o responsável; anotar plano, região, quota/uso e link oficial sanitizado. Verificar A1 disponível na home region, uso, custo e limites. Medir baseline local de contagens e duração de coleta.
- [ ] Fazer cálculo Neon com CU, horas e projeção explícita; teto `<=80 CU-h` e `<1 GB`. Se estiver acima ou sem owner/teto, resultado é `não autorizado` e F53-02/03 não avançam.
- [ ] AC01–AC04: owner/recovery; teto monetário e quota; data/unidade/fonte; console confirma capacidade. Prova negativa: falta de owner, projeção excedida ou captura com segredo impede avanço.
- [ ] Evidência aprovada e revisão do owner; rollback não se aplica. Se a preparação criar custo/recurso inadvertido, parar e acionar dono antes de prosseguir.

### Etapa 5 — F53-02 e F53-03: propriedade/DNS e state/IAM

**Ordem:** F53-02 e F53-03 dependem de F53-01 e podem ter investigação/redação separadas, mas mudanças de conta seguem autorização individual.

**F53-02 (evidência/procedimento, nenhuma troca de DNS neste plano):** registrar propriedade, MFA, recuperação, plano de OAuth, reservar `app.<DOMINIO>` e `api.<DOMINIO>`, TTL, owner e record anterior. AC01–AC04: donos em comum, reserva não exposta, instância Clerk/domínio próprios e restauração do record praticável. Teste negativo: `pages.dev`/OAuth pessoal não qualifica produção. Parar se owners diferirem ou DNS não tiver reversão. Evidência: matriz redigida e captura DNS aprovada.

**F53-03 (bootstrap/state/IAM, provisionamento aguarda autorização):** criar `infra/terraform/oci/` com provider/version pins, variables/outputs, networking/compute/IAM/DNS, exemplo `pilot.tfvars` sem segredo e README. Verificar validação/format, plan de ensaio, lock concorrente, principal negado fora de compartment e recuperação pós-cancelamento. AC01–AC04: mínimo privilégio, exclusão mútua de state, plan sem secret, state recuperável. Gate: Resource Manager/lock e preço confirmados na conta; alternativa state local criptografado explicita limitação de single-operator. Rollback: nenhum apply; descartar só stack de ensaio que o owner identificou e autorizou.

### Etapa 6 — F53-04: VM, rede e Terraform plan

**Arquivos:** `infra/terraform/oci/*.tf`, exemplo de inputs e evidência de plan. Plan é revisão, não autorização de `apply`.

- [ ] Propor VM A1 2 OCPU/12 GB e boot 50 GB; firewall permite 80/443 e SSH só CIDR administrativo, sem 5432/6379. Plan não contém secret nem expõe state.
- [ ] Rodar `terraform fmt -check`, `terraform validate` e `terraform plan` apenas em sandbox/plan mode após F53-03; o plan deve apontar add/update/destroy legíveis, sem apply.
- [ ] AC01–AC04: shape/disk esperados; scan autorizado sem portas DB; inspeção redigida de inputs/state; login SSH administrativo comprovado somente em VM piloto autorizada.
- [ ] Gate: cota, região, owner e janela aprovados. Evidência inclui revisão e plan sanitizado. Rollback: sem apply; após apply autorizado, destruir somente recursos do stack/IDs confirmados pelo owner e seguir runbook de remoção.

### Etapa 7 — F53-05: imagem ARM e Compose cloud

**Arquivos:** Dockerfiles da API/worker, `.dockerignore`, novo `compose.cloud.yaml`; CI e manifest são exclusivamente F53-15. Runner finito continua de propriedade F53-10.

- [ ] Produzir builds reproduzíveis `linux/arm64` e executar no piloto ARM aprovado; separar API e job finito. Compose cloud contém apenas migration, API, job e proxy, sem Postgres local, Redis, frontend runtime, scheduler residente ou volume DB.
- [ ] Confirmar migration única, API em processo próprio, live healthcheck sem DB, digest imutável e encerramento graceful/deadline do worker quando runner existir.
- [ ] Inspecionar build context/layers sem imprimir ambiente; confirmar `.env`, dumps, state, secrets e credenciais ausentes. Imagem x86 deve ser rejeitada antes de promoção.
- [ ] AC01–AC04: ARM64/digest/health; composição mínima; job termina; camadas/contexto limpos. Evidência: commit/digest/plataforma/duração/status redigidos. Rollback por digest anterior, sem alterar banco.
- [ ] Gate: somente piloto com host aprovado; publicar registry/deploy requer autorização separada.

**Preparação sem aceite:** antes do gate de host, F53-05 pode preparar localmente a composição ARM/Compose mínima sem declarar AC03 aceito. O dono de F53-10 prepara então o runner finito mínimo que fornece deadline/saída para a validação de AC03, preservando a propriedade F53-10. Só depois dessa preparação cruzada e do host autorizado F53-05 é validado/aceito; o aceite restante de F53-10 ocorre na sua própria etapa. Preparação local não fecha card nem gate.

### Etapa 8 — F53-06: compatibilidade Neon e restore isolado

**Arquivos:** suites de schema/migration e scripts backup/restore; sem alterar endpoint runtime enquanto teste não justificar.

- [ ] Antes de qualquer restore desta etapa, o dono de F53-14 prepara localmente o ajuste do worktree para não passar DSN/senha por argv e valida o guard com fixture. Isso é somente pré-requisito técnico de F53-06, não conclui F53-14, não executa cópia externa nem altera o dono do card.
- [ ] Montar inventário dinâmico de schemas Alembic e testar PG17, `vector`, `unaccent`, permissões, FTS, pool/pre-ping e `statement_timeout` em Neon de ensaio com aprovação ou fixture Postgres isolada local.
- [ ] Validar backup/restore apenas depois da correção F53-14 de argv, em fixture/servidor isolado com `CREATEDB`; `_test` no nome não prova que servidor está isolado.
- [ ] Projetar consumo por duração real e confirmar `<=80 CU-h/mês`, `<1 GB`; 0,25 CU durante 24x7 é cerca de 186 CU-h e reprova a projeção.
- [ ] AC01–AC04: PG17/extensões/schema; timeout; manifesto restore em isolado; quota medida. Prova negativa: sem extensão/CREATEDB/isolamento ou projeção acima do limite, bloquear migration. Rollback: descartar somente branch Neon de teste autorizada, nunca base produtiva.

### Etapa 9 — F53-07: auth API e tenancy

**Arquivos:** Auth Packages 1–3, testes offline, fixtures sintéticas. Separar auditoria/implementação local de Clerk externo.

- [ ] Testar dono válido RS256/JWKS local, assinatura/issuer/exp/nbf/alg inválidos, `kid` desconhecido, rotação, falha JWKS, `azp`, `aud` apenas quando configurado e usuário diferente. Fixture usa chave gerada de teste, nunca sessão real.
- [ ] Auth aplica-se a leitura e escrita; `/health/live` é público mínimo; demais rotas privadas/owner seguem matriz. Comparar somente `sub` verificado com `CLERK_OWNER_SUB`; negar roles, e-mail ou metadata como privilégio.
- [ ] Fazer A/B em todas as entidades pessoais e owner negative em cada grupo administrativo; UUID estrangeiro retorna `404`, membro recebe `403` em rotas globais/admin e overview de membro não inclui campos operacionais/de terceiros. Checar logs de motivo/correlation ID sem token ou PII.
- [ ] Validar os critérios do card: dono autorizado nas operações globais, token inválido 401, membro autenticado usa somente seus dados pessoais e recebe 403 nas operações globais, claims/origin conforme contrato e logs redigidos. Falha do provedor não libera rota. Rollback: interromper exposição do serviço; nunca tornar endpoints anônimos.
- [ ] Gate de instância Clerk/dominio próprio fica separado: sem owner/conta aprovada, somente fixtures offline.

### Etapa 10 — F53-08: frontend Clerk/Pages (código local antes de Pages)

**Arquivos:** Auth Package 4. A configuração de Pages/hostnames não é arquivo local e exige F53-02/07 e aprovação.

- [ ] Verificar build local `apps/web` em `dist`; `VITE_*` apenas `VITE_API_BASE_URL` e Clerk publishable key. Scan do bundle bloqueia segredo/chave privada/URL Neon.
- [ ] Testes browser em origem local cobrem `/`, deep link, reload, asset inexistente, sessão ausente, dono, token inválido e outro `sub`; requests chegam a API HTTPS somente em preview autorizado.
- [ ] Validar os critérios do card: root/build/output e fallback SPA; env públicas; dono autentica, membro acessa seus próprios dados e operações globais recusam 403; rota direta sem falso 404. Sem deploy, aceite externo Pages continua pendente.
- [ ] Rollback de preview escolhe artefato anterior compatível após aprovação; não introduzir secret para recuperar UI.

### Etapa 11 — F53-09: TLS, CORS e exposição de rede

**Arquivos:** proxy em `compose.cloud.yaml`, CORS/config da API, testes e guia. Porta pública do app não autoriza acesso ao DB.

- [ ] Testes locais de configuração: origin permitido exata `https://app.<DOMINIO>`, origin não aprovado sem `Access-Control-Allow-Origin`, Authorization preflight restrito, redirecionamento TLS e backend só na rede interna.
- [ ] Provar `/health/live` sem conexão Neon e limitar readiness a deploy/on-demand; nenhum monitor em 10 segundos chama `/health`/`/health/ready`.
- [ ] AC01–AC05: certificado válido e redirect, CORS allow/deny, sem banco/portas internas públicas, live sem DB, readiness documentada. Teste externo/scan só em ambiente e janela autorizados.
- [ ] Evidência: output redigido de probes e configuração. Rollback: digest/config proxy e records anteriores; manter backend fechado se TLS/CORS falharem.

### Etapa 12 — F53-10: runner de pipeline finito

**Arquivos:** `scripts/run_pipeline_once.py`, `platform/pipeline.py` se módulo ainda necessário após inspeção, integração com services e testes de worker/runner. Preservar o worktree existente deste card; adaptar commits/hunks, não copiar arquivos sobrepostos por inteiro.

- [ ] Após a preparação local de F53-05, preparar o runner finito mínimo de deadline/saída necessário ao AC03 de F53-05, sem declarar F53-10 aceito e sem agendamento cloud.
- [ ] Runner recebe `RUN_ID`, `DEADLINE_UTC`, opera uma vez e sai. Ordem fixa: coleta habilitada, normalizações pendentes, `evaluate_pending`; análise IA e retenção ficam opt-in.
- [ ] Reutilizar claim/lease/fencing existentes; deadline do runner menor que hard timeout de service, que por sua vez fica dentro da janela agendada. Testar concorrência de dois processos, SIGTERM, estágio que falha, reinício e run interrompido.
- [ ] Não marcar presença/ausência a partir de execução parcial, não repetir efeitos de etapa e não implementar retry infinito. Coleta determinística continua independente de descoberta/enrichment opcional.
- [ ] AC01–AC05: deadline/saída, claim único, shutdown graceful, retomada segura, invariável de ausência. Rodar testes focados `tests/backend/test_worker.py` e novo teste do runner offline. Rollback: desativar runner; deixar API no digest anterior e preservar run state.
- [ ] Gate: sem agendamento cloud ou execução em banco operacional nesta etapa.

### Etapa 13 — F53-11 e F53-12: timer finito e medições de recursos

**F53-11 arquivos:** unidades futuras `infra/systemd/opportunity-radar-pipeline.service` e `.timer`, wrapper e evidência. **F53-12 arquivos:** limites em Compose e config de runtime somente se já consumida.

- [ ] Definir UTC, dono, horários, janela/deadline, timeout e regra sem sobreposição/catch-up. Timer inicia runner local, não chama API pública nem grava heartbeat quando parado.
- [ ] Testar reboot, timer perdido, duplicação, SIGTERM, janela perdida, sem conexão DB em repouso e sem avalanche no catch-up. Em piloto autorizado, desabilitar timer e confirmar unidade inativa para rollback.
- [ ] F53-12 exige três runs idênticos de fixture/digest; medir CPU/RSS/conexões e idle antes/durante/depois. Derivar limites com margem documentada, confirmar pool fecha/idle e orçamento Neon.
- [ ] AC F53-11 AC01–AC05 e F53-12 AC01–AC04, com journals/métricas redigidos. Não inventar `pool_size`/env ou worker residente para satisfazer métrica. Rollback: parar timer e reverter apenas limites ao último conjunto medido.

### Etapa 14 — F53-14: backup externo e restore

**Arquivos:** scripts e tests do mapa; integrar com o slice já existente no worktree `f53-14-backup`, respeitando alterações locais. Incluir fixture de dump corrompido, manifest ausente, extensão/CREATEDB negados e recusa de alvo de produção.

- [ ] Remover DSN/senha de argv nos dois scripts; adotar `PGPASSFILE` 0600/`PGSERVICE` ou mecanismo equivalente, validar alvo antes de conectar e testar processos/logs redigidos.
- [ ] Backup deve gerar dump/manifest/checksum consistentes; restore isolado confirma revision, extensões, contagens/relações e remove scratch. `--allow-missing-manifest` não conta como aceite.
- [ ] Executar apenas com dump de fixture e destino isolado local `_test`; cópia externa cifrada/bucket OCI é etapa de provedor e fica bloqueada.
- [ ] AC01–AC04: manifesto/cópia, restore comparativo, scratch/isolamento, retenção somente após restore. Falha conserva geração anterior. Rollback: não prune nem apagar dump; reverter código apenas com hunk/commit próprio.
- [ ] Após card, mandar para F53-13/16/17 somente hash, bytes, status e relatório redigido; nunca dump ou DSN.

### Etapa 15 — F53-13: política/execução de retenção

**Arquivos:** novo job/módulo e testes apenas depois de definido lineage real; preservar canonical, CRM, lineage, última evidência e assessments referenciados.

- [ ] Implementar `--dry-run` com corte/data/lote e relatório por tipo; fronteiras temporais, referência protegida, relações pendentes e retomada do lote cobertos em fixture.
- [ ] Medir storage/crescimento com a mesma query antes/depois; apresentar a proposta raw 365→30 dias e assessments opt-in 7 dias sem aplicá-la em dado real.
- [ ] Aplicar somente em fixture isolada, gerar backup pré/pós e restore pós-lote em segundo alvo `_test`; cache expira por TTL sem apagar objeto canônico.
- [ ] AC01–AC04: só candidatos elegíveis, restore/relações válidos, bytes medidos, TTL isolado. Falha suspende job e mantém backup; dados reais perdidos exigem incidente e aprovação, nunca novo purge.
- [ ] Autorização separada é obrigatória antes de qualquer retenção real.

### Etapa 16 — F53-15: CI isolada e imagem multiarch (dono único)

**Arquivos:** somente owner deste pacote modifica `.github/workflows/pipeline.yml`, fixtures e scripts/config de CI/manifest. Nenhum outro pacote altera os mesmos arquivos.

- [ ] CI testa startup sem auth (falha fechada), dono JWT/JWKS offline, claims errados/outro `sub`, guard que recusa URL não `_test` antes de DB, e manifest API/worker `linux/arm64`.
- [ ] Reparar o harness offline antes da validação final: curls e2e recebem JWT/JWKS de fixture explícita, `compose.ci` usa a factory de produção com middleware de identidade ativo e o worker recebe `WORKER_OWNER_SUB` sintético. Não usar `dev.local_app`, bypass anônimo, signer de teste em cloud ou credencial real.
- [ ] Isolar jobs unit/web/integration; fixture JWT/JWKS local; verificar secrets dummy não têm valor real. Fluxo não cria Pages/OCI/Neon/Clerk nem executa deploy.
- [ ] Testar caso positivo e negativo de cada guard; executar action local/offline quando possível e revisar workflow; validação no GitHub exige autorização para publicar/push.
- [ ] AC01–AC05: fail closed, autorizado offline, claims negativos determinísticos, URL recusada e manifest ARM64. Rollback: reverter somente commit CI dedicado e deixar deploy ausente.

### Etapa 17 — F53-16: aceite de piloto só com fixtures

**Arquivos:** suíte smoke e evidência em `docs/53-roadmap-hospedagem/evidencias/f53-16-aceite-<data>.md` depois de existir teste local; não adicionar credentials reais.

- [ ] Executar API local, `/health/live` anônimo, todas rotas com JWT/JWKS de fixture, inválidos/normal owner, API assets/fallback SPA e TLS/CORS simulados/locales.
- [ ] Executar uma janela única do runner com fixture e timer desligado; medir conexão/idle no sandbox, backup/restore local, CI e manifest. O ensaio local não faz login Clerk ou request para hostname real.
- [ ] Um piloto hospedado posterior exige autorização específica e usa somente dados de fixture, porém autenticação Clerk real; nunca confia no signer/JWKS offline de teste no cloud. Registrar a autorização e a prova redigida antes do piloto.
- [ ] AC01–AC05: status/auth, TLS/CORS/SPA, job finito e idle, backup/restore, CI/ARM. Redigir run ID e métrica. Um AC externo Pages/OCI/Neon não verificado permanece bloqueado; o card jamais usa dado de usuário.
- [ ] Rollback: parar serviço/job piloto; preservar artefatos e restaurar digest anterior, sem restore em DB real.

### Etapa 18 — F53-17: monitoramento e exercício de incidente

**Arquivos:** guia e configuração de alerta futura, mais evidência redigida `evidencias/f53-17-incidente-<data>.md`. Conta/contato/alarme real exige aprovação explícita.

- [ ] Definir alertas de host/job/backup/quota com owner, severidade, limiar e período ocioso aceitável; testar alerta sintético local sem enviar e-mail externo.
- [ ] Em ambiente de piloto autorizado, validar tópico Active, métrica FIRING, entrega de contato controlado, restauração de threshold/OK; nenhum ID/e-mail aparece nos artefatos.
- [ ] Simular incidente: parar timer/writers, preservar digest/log/hash, restaurar apenas isolado, corrigir no piloto, smoke F53-16, owner decide retomada. Não destruir container/state/dump como diagnóstico.
- [ ] AC01–AC05: entrega e estado de alarme, limiar restaurado, incidente preserva backup e retoma janela. Rollback: restaurar alerta anterior; se qualquer AC falhar, timer permanece desativado e F53-18 bloqueado.

### Etapa 19 — F53-18: cutover e recuperação (primeiro possível uso de dados reais)

**Arquivos:** procedimento da janela e evidência `evidencias/f53-18-cutover-<data>.md`; revisão separada de qualquer alteração de dados/config. Nenhuma execução autorizada implicitamente.

- [ ] Antes de janela, obter autorização específica para origem/destino, dados, domínio/DNS, credenciais, horário, custo, RPO/RTO e owner. Verificar F53-01–17 aceitos e backup externo/restaurado.
- [ ] Exercitar todo procedimento primeiro em fixture/destino novo e vazio isolado. Freeze writers/jobs/claims; dump final, cópia cifrada, hash ciphertext após transferência, `PGPASSFILE` 0600, TLS `verify-full`, compatibilidade/extensões e destination identity confirmada pelo owner.
- [ ] Import separado de `restore_check.py`: `pg_restore --no-owner --no-privileges --exit-on-error` somente no alvo vazio identificado e aprovado, sem `--clean`/`--create`; verificar revision/schema/constraints/manifest e smoke F53-16 antes de DNS/writers.
- [ ] DNS em etapa controlada respeita TTL; provar TLS/CORS/JWT/Pages e destino. Se nenhum dado novo foi escrito, restaurar record/digest anterior; depois de escrita, congelar os dois lados e obter decisão humana de reconciliação. Nunca sobrescrever origem/destino por reflexo.
- [ ] AC01–AC05 e V01–V05: restore/checksum, writers quiescentes, DNS/auth/dados válidos, rollback preserva escrita nova, custo/RPO/RTO/owner. Erro aborta janela antes de writers.
- [ ] Aprovação explícita do owner encerra o card; conservar origem, dump e backup externo conforme plano, registrar incidentes e decisão. Deploy, DNS, import e promoção ficam bloqueados até autorização escrita e revisão de prontidão.

## Ordem de dependência oficial

```text
F53-01 -> F53-02 -> F53-04 -> F53-05 -> F53-09
        -> F53-03 -> F53-04
F53-01 -> F53-06 -> F53-10 -> F53-11 -> F53-16 -> F53-17 -> F53-18
F53-02 -> F53-07 -> F53-08 -> F53-16
F53-04 + F53-06 -> F53-14 -> F53-13 -> F53-18
F53-05 + F53-06 + F53-07 -> F53-15 -> F53-16
F53-05 + F53-06 + F53-10 -> F53-12 -> F53-16
F53-09 + F53-11 + F53-14 -> F53-17
F53-13 + F53-16 + F53-17 -> F53-18
```

Também respeitar a tabela canônica de `docs/53-roadmap-hospedagem/README.md`: F53-03 é pré-requisito de F53-04; F53-10 depende de F53-05 e F53-06; F53-13 depende de F53-06 e F53-14; F53-15 depende de F53-05, 06 e 07. Nenhuma sequência desta página encurta esses gates.

## Matriz dos 18 cards

Nenhum card está aceito. F53-01 está **em andamento** apenas na parte de inventário local; orçamento, painel e quota continuam pendentes. F53-07, F53-08, F53-10, F53-14 e F53-15 estão **em andamento** somente por preparação/código local parcial e precisam de integração, testes e gates; F53-14 inclui um slice em worktree separado. Os demais estão **bloqueados/pendentes** por dependência ou evidência externa. A existência de código local, conta ou alteração em worktree não satisfaz aceitação. Atualizar status somente com teste positivo/negativo aplicável, revisão, prova datada redigida e rollback do card.

| Card | Status inicial | Dependência | Saída e critério mínimo de aceite | Evidência necessária | Rollback/gate |
| --- | --- | --- | --- | --- |
| F53-01 | Em andamento: inventário local; painel/orçamento pendentes | — | AC01–04: owners/recovery; teto/moeda e Neon `<=80 CU-h`; baseline com data/unidade/fonte; cota A1 confirmada no painel | tabela datada de inventário, medição local, projeção explícita, alertas redigidos e revisão do dono | sem teto/owner/quota, estado `não autorizado`; nenhum recurso criado |
| F53-02 | Bloqueado | 01 | AC01–04: ownership de registrador/DNS/Clerk, hostnames reservados, domínio Clerk próprio, TTL e retorno anterior | matriz DNS/owners, estado antes, consulta externa quando mudança for autorizada | sem alteração; record anterior documentado; pages.dev/OAuth pessoal não qualifica prod |
| F53-03 | Bloqueado | 01 | AC01–04: IAM mínimo, exclusão mútua de state, plan sem secret, state recuperável após cancelamento | plan revisado, prova de deny/lock/recuperação redigida | sem apply até autorização; stack só removida com identidade validada |
| F53-04 | Bloqueado | 02,03 | AC01–04: A1 target 2/12 e boot 50 GB, portas mínimas, sem secret em plan, acesso administrativo | `fmt`/`validate`/plan, inspeção firewall redigida e prova do piloto aprovado | sem apply automático; porta 5432/6379 ou plan inesperado bloqueia |
| F53-05 | Bloqueado | 04 | AC01–04: ARM64, Compose cloud mínimo, job acaba no deadline, imagem sem secret | digest/plataforma/health, Compose sanitizado e revisão de camadas | rollback para digest anterior; não toca DB |
| F53-06 | Bloqueado | 01 | AC01–04: PG17/extensions/schemas; timeout; restore fixture; quota/bytes na meta | matriz de compatibilidade, suites isoladas, relatório de restore e consumo | descartar só ambiente de ensaio; produção permanece intocada |
| F53-07 | Em andamento: auth local, sem aceite/gates Clerk | 02 | critérios do card: owner nas operações globais, 401 inválido, membro nos próprios dados/403 global, claims/azp/aud e logs limpos | testes offline + matriz de rotas + inspeção de log redigido | falha fecha rotas; nunca permitir anônimo como fallback |
| F53-08 | Em andamento: SDK/bootstrap local; Pages não autorizada | 02,07 | critérios do card: Pages build em apps/web/dist, só env pública, owner API OK, membro nos próprios dados/403 global, deep-link SPA | build local e browser; configuração/domínio externo só quando autorizado | voltar deployment anterior compatível; chave secreta no bundle bloqueia |
| F53-09 | Bloqueado | 04,05,07 | AC01–05: TLS, CORS allow/deny, portas internas fechadas, live DB-free, readiness sob demanda | probe/scan autorizado, headers redigidos, painel idle | rollback proxy/records; banco e API permanecem fechados quando falha |
| F53-10 | Em andamento: runner/slice em worktree, sem aceite | 05,06 | AC01–05: deadline; claim sem efeitos duplicados; SIGTERM; retomada; parcial não fecha ausência | testes offline concorrentes/interrompidos, logs de runner redigidos | desativar runner e preservar estado; sem retry infinito |
| F53-11 | Bloqueado | 10 | AC01–05: uma janela observada, reboot sem duplicação, timeout, idle sem DB, alerta de janela perdida | timer/status, cronologia, série Neon e alerta redigidos | disable timer, aguardar processo/graceful exit; sem catch-up |
| F53-12 | Bloqueado | 05,06,10 | AC01–04: três medições, conexões idle, Neon `<=80 CU-h/<1 GB`, sem serviços extras | três séries comparáveis de CPU/RSS/conexão/uso | voltar aos limites medidos; custo excessivo pausa janela |
| F53-13 | Bloqueado | 06,14 | AC01–04: dry-run só candidatos, relações restauráveis, bytes medidos, TTL preserva dados | relatório antes/depois, backup+restore pós-lote em isolado | suspender retenção; real-data purge necessita aprovação e backup |
| F53-14 | Em andamento: slice em worktree separado, sem aceite | 04,06 | AC01–04: dump/manifest/checksum/cópia, restore isolado integral, scratch removido, retenção segura | hash/bytes/status e comparativo redigido; argv sem DSN | preservar gerações; falha nunca faz prune nem promoção |
| F53-15 | Em andamento: CI local, sem aceite/publicação | 05,06,07 | AC01–05: auth fail-closed, fixtures offline, claims 401/403, URL guard, manifest ARM64 | pipeline e resultados negativos/positivos; execução remota somente autorizada | rollback de commit dedicado; nenhum deploy automático |
| F53-16 | Bloqueado | 08,09,11,12,14,15 | AC01–05: API fixture, TLS/CORS/SPA, job+idle, backup/restore, CI/ARM; **apenas fixtures** | smoke/capturas/logs sintéticos redigidos e revisão datada | desligar piloto; AC externo ausente mantém card bloqueado |
| F53-17 | Bloqueado | 09,11,14 | AC01–05: alarmes FIRING/OK, entrega controlada, limiar restaurado e exercício com backup | tópico/owner/UTC mascarados, cronologia de incidente e smoke 16 | timer para até remediação e nova prova; preservar state/dump |
| F53-18 | Bloqueado | 13,16,17 | AC01–05/V01–05: backup final, writers parados, import/validações, DNS/auth, rollback de escrita nova e custo/RPO/RTO aprovados | cronologia owner, hash, comparações e smoke redigidos | antes de write restaurar tráfego; depois de write congelar os lados e reconciliar com humano |

## Comandos e evidências de validação

- Para alterações Python locais, usar a menor suíte focada indicada na Etapa 1, seguida pelas suites do pacote auth/tenancy relevante. Em comandos Docker, usar nome de projeto exclusivo, imagens atuais aprovadas e bind mount/override explícito do working tree, desativar o banco operacional/dependências implícitas e validar a variável de destino mascarada antes de executar.
- Frontend: em `apps/web`, `cmd /c C:\nvm4w\nodejs\npm.cmd test -- <arquivos-focados>` e `cmd /c C:\nvm4w\nodejs\npm.cmd run check`. Não alegar browser real, Clerk ou Pages por um teste local.
- Terraform: apenas validação/formatação e `plan` offline/de ensaio depois de autorização de conta. `apply` não faz parte da validação local.
- Backup/restore: só fixture ou servidor de integração isolado, com os três guards e URL `_test`; verificar argv em processo, checksum, manifesto, Alembic, extensões, contagens e relações. Não imprimir URL nem conteúdo `.env`.
- F53 cloud acceptance: registrar data UTC, revisão/digest, owner, comandos, status, resultado, origem da evidência e redactions. E-mail, host, account/tenancy OCID, conta, hostname privado e IDs ficam mascarados.
- Final do pacote local: rodar revisão de correção por pacote (dashboard/worker, auth/migration/A-B, frontend) e correção conjunta; executar backend isolado completo uma vez após todas as alterações; `npm run check`; suites browser locais pertinentes; `git diff --check`. Check local nunca equivale a CI, deployment, Neon quota, restore externo ou aceite de produção.

## Gates externos pendentes

Nenhuma das aprovações abaixo é dada por este plano. Cada execução deve anexar o gate específico, dono que aprovou, ambiente e escopo. Se falta, executar apenas preparação local sem recurso externo.

1. **F53-01:** teto monetário, owner e recuperação para cada provedor, domínio e custo de renovação; autorização para ler os respectivos painéis.
2. **F53-02/03:** owner comprova domínio/zonas/Clerk e autoriza alteração; criação de tenancy/Resource Manager/IAM/state precisa autorização própria.
3. **F53-04/05:** owner aceita região/shape/orçamento, VM/rede, registry e execução de build/pull/deploy; `terraform apply`/criação de VM nunca decorre de `plan`.
4. **F53-06/14:** projeto/banco de ensaio aprovado, destino comprovadamente isolado, permissões, quota, criptografia e operador; backup externo/upload em bucket é outra aprovação.
5. **F53-07/08:** owner autoriza instancia Clerk, domínio próprio, OAuth, chaves no secret manager e publicação Pages; chaves reais nunca entram em repo/artefato/log.
6. **F53-09/11/12/17:** autorização para scan externo, regra DNS/proxy, host/timer, medição da tenancy, notificações/e-mail e alarmes OCI.
7. **F53-15:** qualquer push, ajuste de secrets/workflow remoto, imagem em registry ou trigger de release requer autorização explícita; validação local offline pode seguir.
8. **F53-16:** mantém fixtures apenas; credencial real ou dado real exige aprovação além do aceite sintético e não deve ser incorporado à fixture.
9. **F53-18:** aprovação nominada da janela, origem/destino Neon, importação, DNS/tráfego, freeze writers, RPO/RTO, orçamento e plano humano de reconciliação. Só este card pode iniciar cutover, mas não o autoriza sozinho.

## SPEC 54 fora da etapa atual

- WP6 permanece pendente até F53 auth real ser entregue e aceita: testes offline de sessão ausente/expirada, login/logout, forbidden/owner e smoke do contrato real, sem expor token.
- WP7 permanece pendente até F53 operacional aceito e caminho de preview/release autorizado: preview, dez rotas diretas/deep links, jornadas, viewports, baseline, artefato anterior imutável e rollback frontend sem migração.
- Nenhum dos dez AC54 é marcado por um plano ou por esta implementação local. Encerramento F54 exige AC54-01–10 individualmente evidenciados, aprovação explícita dos protótipos e baselines; `npm run check` isolado não fecha WP6/WP7.

## Auto-revisão do plano

- Cobertura: as etapas cobrem a recuperação P1, integrated backend/A-B, frontend auth, todos os 18 cards e os pacotes F54 pendentes.
- Dependências: ordem e arestas respeitam o índice canônico; F53-15 tem propriedade exclusiva de CI/ARM; F53-14 e F53-10 respeitam worktrees com alterações próprias.
- Evidência: status inicial não afirma card concluído; F53-16 é sintético; F53-18 é primeiro possível uso real; deploy, provedor e produção permanecem explicitamente bloqueados.
- Segurança de dados: nenhum comando aqui permite integração no DB operacional ou expõe DSN; integração exige os três guards e destino `_test` validado.
- Placeholder scan: sem TODO/TBD; testes não previstos para arquivos ainda inexistentes foram nomeados como novos apenas no card que os possui.
