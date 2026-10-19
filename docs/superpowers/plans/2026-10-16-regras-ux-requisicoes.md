# Plano de melhoria de regras, UX e volume de requisições

> Plano de execução. Cada alteração de código deve ser feita por um executor com escopo delimitado, seguida de revisão read-only e validação correspondente. Este documento não autoriza publicação, deploy, migração operacional ou mudanças de banco fora de ambiente isolado.

**Objetivo:** Tornar explícitas e consistentes as regras de elegibilidade e priorização, melhorar a leitura e os fluxos principais da interface, e reduzir chamadas HTTP desnecessárias sem perder frescor, segurança ou ações manuais.

**Abordagem:** Usar R55 como base aprovada para regras e coleta; propor duas extensões separadas, F para UX e G para tráfego, sujeitas a aprovação antes da implementação. Medir o comportamento atual em fixtures isoladas, prototipar os fluxos prioritários, implementar mudanças pequenas e comparar os mesmos cenários antes e depois.

**Tecnologias:** React, TypeScript, TanStack Query, API FastAPI, pytest, Vitest e o runner isolado de frontend baseado em Playwright já documentado em `docs/54-baseline` e `docs/54-final`.

**Referências:** `docs/55-plano-melhorias/README.md` em `origin/main` (R55 aprovado); `docs/54-continuation.md`; `DESIGN.md`; testes de matching e dashboard existentes; [TanStack Query: defaults importantes](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/important-defaults.md) e [cancelamento de queries](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/query-cancellation.md). A documentação oficial consultada distingue frescor (`staleTime`) de `refetchInterval`, que roda independentemente, e descreve que o cancelamento depende de consumir o `AbortSignal` na função de query. Este plano complementa R55 e não substitui suas decisões.

## Restrições globais

- Antes de implementar, inspecionar e reutilizar uma worktree adequada, começando por `.worktrees/r55-e1-e3-ingest` (branch `r55/e1-e3-ingest`) e `.worktrees/r55-e5-e6` (branch `r55/e5-e6-reduce`); só criar uma worktree isolada se nenhuma servir. Preservar checkout e alterações concorrentes.
- O checkout observado estava em `feat/f54-redesign-frontend`, HEAD `fbda51232628e1534f997d5f1810b7a9807cc6dc`; `origin/main` local estava em `511ed7ec4a1c8c94373b1d4b0ef29c48c7bac9e0`, com divergência local de 0 à frente e 89 atrás. Não foi feito fetch; confirmar atualidade antes de criar a worktree.
- R55 cobre frentes A migração, B coleta, C IA, D regras e E retenção/armazenamento. E2 retenção já está mesclada (#98); não recriar. D1 país, D2 desconhecido versus neutro, D3 senioridade, D4 sugestão de feedback, D5 explicação de encerramento, D6 auditoria de defeitos de interface, B3 HTML limpo e B4 senioridade/habilidades são referências existentes.
- F (UX) e G (requisições) são extensões propostas neste plano e ainda não aprovadas. Não tratá-las como cards R55 aceitos sem decisão explícita.
- Preservar o matching determinístico separado da IA. IA continua consultiva e não altera pontuação, veredito, candidatura, perfil ou estado de fonte sem ação humana explícita.
- Não inferir pesos de score novos. Qualquer mudança de pesos requer matriz aprovada com exemplos positivos e negativos antes da alteração de código.
- Preservar autenticação, isolamento por identidade/tenant, autorização, rotas, URLs, filtros, paginação existente (10/25/50/100), aplicação manual e controles manuais de fontes.
- Não medir nem executar testes de integração contra banco operacional. Testes de DB exigem banco isolado cujo nome termine em `_test` e as três variáveis de isolamento descritas nas instruções do projeto.
- Nenhum resultado documental ou de fixtures deve ser descrito como medição de produção ou prova de deploy.

## Foco de revisão

- Geografia ou área incerta deve ir para revisão; nunca descartar silenciosamente uma vaga-alvo por inferência ou IA. Localização estruturada pode indicar presença de escritório, não restrição de residência; testar isso separadamente.
- Dado desconhecido não equivale a compatível nem a incompatível. Testar ausência de dado versus evidência explícita contraditória e verificar estado de revisão.
- Senioridade precisa tratar Junior, Pleno/Intermediate/Mid e Senior por evidência textual consistente; score e explicação devem concordar.
- Falha, execução parcial ou ocorrência ainda ativa não pode encerrar uma oportunidade. Cobrir duas execuções completas consecutivas, outra ocorrência ativa e execução parcial.
- Cache e cancelamento não podem misturar identidades nem descartar mutação confirmada. Cobrir troca de identidade, resposta antiga tardia, erro de autorização e mutação concorrente.

## Baseline e limites a confirmar

Inspeção estática mostrou `refetchInterval: 15_000` em `apps/web/src/features/dashboard/useInbox.ts` e `apps/web/src/features/matching/useAssessment.ts`. Isso equivale a 4 chamadas/minuto ou 240/h por instância ativa, além da carga inicial; não é rastreamento de runtime e não implica que ambos os hooks estejam na mesma página. No bloco de buscas salvas, Overview faz uma chamada da lista mais uma chamada de contagem por busca: 21 chamadas para 20 buscas (lista + 20 counts), excluídas outras queries da página. Esse número também é observação estática do padrão, não medição de uma sessão real.

`OverviewPage.tsx` busca a lista de saved searches e faz uma chamada `GET /saved-searches/:id/new-count` por busca; com 20 buscas, esse bloco resulta em 21 chamadas (1 lista + 20 counts), sem incluir outras queries da página. `SourceMetricsSection` e `AnalysisSupport` fazem chamadas distintas, embora `queryKey` compartilhada possa deduplicar transporte. Contar chamadas HTTP, não invocações de hooks. A busca da Inbox só ocorre após envio explícito; manter esse comportamento sem debounce supérfluo. `InboxPage.tsx` mostra `workMode` e `seniority` crus em `:179`, e o filtro de senioridade usa `label:value` em inglês em `:709`; o detalhe já possui mapas em português e explicações de elegibilidade/fatores. Reutilizar os rótulos existentes, sem presumir que as explicações de detalhe estejam ausentes.

Antes de fixar orçamento, executar matriz em fixture isolada no mesmo SHA: cold/warm cache; 0, 5 e 20 buscas salvas; navegação, filtro, envio explícito, página, mutação, cinco minutos ocioso, background/retorno, reconexão e sessão expirada; respostas 401, 403, 422, 429 e 5xx. Contar chamadas API bem-sucedidas, falhas, canceladas e retries; separar OPTIONS, Clerk e `/session`. Registrar método e endpoint normalizado sem query string, credenciais ou dados pessoais, bytes, p50/p95 por rota e tempo/contagem SQL separadamente. Não executar benchmark com DB real nesta fase.

Metas provisórias, sujeitas à confirmação pela baseline: zero chamadas periódicas em cinco minutos para Inbox, detalhe de empresa e avaliação estáveis; revisita dentro do TTL sem GET de dados inalterados; Overview com no máximo 5 GETs independentes de N para 0/5/20 buscas; Inbox até 2, detalhe até 4, Pipeline até 1. Excluir bootstrap Clerk, `/session` e OPTIONS do orçamento principal, mas reportá-los em separado. Uma submissão explícita deve fazer 1 GET. Mutação deve fazer 1 escrita e no máximo 1 GET por chave ativa afetada; definir o total após inventariar invalidações reais.

## Arquivos e responsabilidade esperada

Os caminhos abaixo são pontos iniciais encontrados em `origin/main`; confirmar a base e os callers na worktree antes de editar. Alguns ainda não existem no checkout observado. Mudanças adicionais exigem justificar o proprietário no diff.

| Responsabilidade | Arquivos principais |
| --- | --- |
| Regras de domínio e normalização | `src/opportunity_radar/opportunities/regions.py`, `role_family.py`, `service.py`, `models.py`; `src/opportunity_radar/acquisition/jobposting.py`; testes `tests/backend/opportunities/test_regions.py`, `test_measure_seniority_titles.py`, `test_domain.py` e `tests/backend/acquisition/test_target_area_share.py`, `test_filtered_presence.py` |
| Presença e fechamento de ocorrências | `src/opportunity_radar/opportunities/service.py`; `tests/backend/opportunities/test_run_closures.py` e `tests/backend/acquisition/test_filtered_presence.py` |
| Contagem agregada por busca salva | `src/opportunity_radar/presentation/http/dashboard.py` (`SavedSearchResponse`, rotas); `src/opportunity_radar/dashboard/saved_searches.py`; `tests/backend/dashboard/test_saved_searches.py`, `test_tenancy.py` |
| Cache, polling e transporte | `apps/web/src/features/dashboard/useInbox.ts`, `features/matching/useAssessment.ts`, `features/saved-searches/useSavedSearches.ts`, `features/saved-searches/api.ts`, `features/dashboard/useOverview.ts`, `apps/web/src/app/WebApplication.tsx`, `apps/web/src/lib/api.ts` e seus testes |
| Fluxos de interface | `apps/web/src/routes/InboxPage.tsx`, `OpportunityDetailPage.tsx`, `PipelinePage.tsx`, `OverviewPage.tsx`, `StatusPage.tsx`; testes homônimos `*.test.tsx`; wrappers existentes e `DESIGN.md` |
| Evidência isolada e CI | runner existente em `docs/54-baseline` / `docs/54-final`; `.github/workflows/pipeline.yml` se uma nova verificação repetível for necessária |

## Sequência de trabalho

### Tarefa 1 — Reconciliar base e registrar baseline reproduzível

**Responsabilidade:** Terra para harness/medição; coordenação read-only para reconciliação. Nenhum benchmark operacional.

**Passos:**

- [ ] Confirmar o HEAD e a origem remota atual; revisar status, commits não publicados e worktrees `.worktrees/r55-e1-e3-ingest` e `.worktrees/r55-e5-e6`; reutilizar a mais adequada ou criar worktree isolada somente se necessário.
- [ ] Mapear os `queryKey`, `refetchInterval`, `staleTime`, retries, invalidações de mutação, listeners de foco/reconexão e o caminho `queryFn → API → privateFetch` para os fluxos desta proposta.
- [ ] Adaptar o runner existente com fixture de sessão autenticada disponível somente no ambiente de teste; contar tentativas HTTP normalizadas sem DB nesse harness. Não inserir bypass de auth em produção, não abrir `TENANCY_OWNER_API_READY` e não usar issuer real.
- [ ] Fixar cenários cold/warm, 0/5/20 buscas e fluxo de cinco minutos ocioso; salvar JSON curto com SHA, configuração do runner, coorte e resultados. Não incluir URLs privadas, tokens nem PII.
- [ ] Testar que OPTIONS, Clerk e `/session` são classificados à parte; testar que respostas 401/403/422/429/5xx e cancelamentos entram no contador correto.

**Aceite:** Baseline repetível no mesmo SHA; contagens e denominadores claros; nenhuma chamada externa ou banco operacional; orçamento provisório confirmado ou revisado com evidência. A fixture não modifica auth de produção nem substitui teste autenticado real autorizado.

### Tarefa 2 — Fechar a matriz de regras R55 para país e senioridade

**Responsabilidade:** Terra para domínio/backend e testes; mudanças limitadas aos módulos existentes de matching/coleta e seus testes.

**Passos:**

- [ ] Escrever tabela estrita de decisão para país, área, localização remota e senioridade baseada em campos estruturados e evidência observável. Localização de escritório não prova restrição de residência; dado incerto ou desconhecido deve ir para revisão, não descarte.
- [ ] Antes de alterar filtros pré-persistência, formar coorte de falsos negativos em fixtures rotuladas e exigir decisão de produto para cada regra de exclusão. Não usar IA/inferência para descarte silencioso.
- [ ] Adicionar testes de domínio para país/área explicitamente compatível, explicitamente excluído e incerto; remoto sem alcance declarado e campo ausente devem ir para revisão sem inferir incompatibilidade.
- [ ] Adicionar testes de evidência de senioridade Junior, Pleno/Intermediate/Mid e Senior, incluindo texto conflitante ou ausente; confirmar que a justificativa exibida concorda com o resultado.
- [ ] Implementar a menor mudança nos pontos de regra existentes. Não alterar pesos de pontuação sem matriz aprovada e testes de regressão explícitos.
- [ ] Validar que matching determinístico dá o mesmo resultado com IA habilitada/desabilitada para os mesmos dados, salvo enriquecimento consultivo claramente separado.

**Aceite:** Casos positivos, negativos e desconhecidos cobertos; nenhum descarte por campo ausente; IA não altera score/veredito determinístico; suite focada de matching e coleta passa.

### Tarefa 3 — Tornar estados desconhecidos e encerramentos explicáveis

**Responsabilidade:** Terra para domínio e API; UX pode consumir somente campos aprovados pela regra.

**Passos:**

- [ ] Definir representação explícita para desconhecido, neutro, compatível e incompatível; não usar um booleano ambíguo quando o domínio precisa preservar incerteza.
- [ ] Testar D2 com ausência de evidência e contradição explícita, incluindo a apresentação de “revisar” sem classificar automaticamente como elegível.
- [ ] Testar D5 contra a política existente: duas execuções completas consecutivas podem fechar ocorrência; execução parcial, `skipped_stale` ou ingestão incompleta nunca contam como ausência nem como execução completa; ocorrência ativa equivalente mantém a oportunidade aberta.
- [ ] Manter idade de observação/retention separada do ciclo de vida CLOSED: limite de sete dias é retenção, não sinal de fechamento de negócio.
- [ ] Preservar conflitos de aplicação/manual merge e trilha humana; validar tenant e ocorrência cruzada nos testes de dashboard/tenancy aplicáveis.
- [ ] Expor razão de encerramento baseada em evidência persistida, sem texto inventado nem alteração de estado por falha de detalhe.

**Aceite:** Estados e razões persistem e são auditáveis; casos de execução parcial/ocorrência ativa não fecham; testes de tenancy e de fechamento focados passam.

### Tarefa 4 — Prototipar os fluxos F de UX antes de alterar páginas

**Responsabilidade:** Executor de UX prepara protótipos revisáveis; implementação fica condicionada ao aceite visual explícito do usuário.

**Passos:**

- [ ] Priorizar Inbox → detalhe da oportunidade → Pipeline → Overview, preservando identidade petróleo/ardósia e wrappers definidos em `DESIGN.md`.
- [ ] Para cada tela, mostrar de onde vem a recomendação, evidência, itens desconhecidos, atualização/frescor e a próxima ação humana já disponível no produto.
- [ ] Desenhar estados de carregamento, erro, vazio e dados desatualizados; eliminar apresentações técnicas como `[object Object]` e estado desabilitado falso durante carregamento.
- [ ] Reutilizar os mapas em português do detalhe para substituir enums crus de modalidade e senioridade na Inbox e no filtro, preservando valores internos e contratos.
- [ ] Corrigir o fallback textual de IA que aparece como “Desligada” antes do estado pending. Auditar o eyebrow de ambiente em Status e exibir o ambiente real usando a configuração existente, com fallback explícito; não presumir runtime atual a partir do rótulo. O piloto cloud foi documentado, portanto não fixar o texto “Ambiente local”.
- [ ] Preparar protótipos nos viewports 360, 768 e 1440 px, com navegação por teclado, foco visível, alvos de toque de pelo menos 44 px e contraste AA a validar.
- [ ] Manter português, deep links, URL e estado dos filtros; não propor biblioteca nova, dark mode ou redesenho integral.
- [ ] Registrar revisão e aprovação dos protótipos antes de alterar componentes visuais.

**Aceite:** Protótipos cobrem os fluxos e estados declarados; ações são reais e manuais; aprovação visual registrada; nenhum novo componente externo ou mudança de score.

### Tarefa 5 — Aplicar política de frescor e retry sem polling constante

**Responsabilidade:** Luna para mudança simples de frontend; Terra se for necessário alterar contratos de transporte. Arquivos de query/client e testes próprios.

**Passos:**

- [ ] Após baseline, remover intervalos de 15 s dos hooks de Inbox e avaliação, mantendo atualização no mount e retorno/reconexão conforme estado stale e ação explícita de atualizar.
- [ ] Configurar frescor inicial: listas/detalhes 60 s, perfil/referências 300 s, métricas 60 s; invalidar as chaves corretas após mutação. Ajustar somente com evidência da baseline.
- [ ] Revisar defaults de `WebApplication.tsx`; preservar `retry: 1` somente para GET idempotente e erro transitório. Não repetir auth, validação, conflito ou escrita; 429 exige respeito a `Retry-After` ou retry manual, sem repetição automática prematura.
- [ ] Propagar `AbortSignal` de TanStack Query até `privateFetch` para GET obsoleto; garantir que abort não interrompe ou perde mutação confirmada.
- [ ] Testar fake timers em cinco minutos ociosos, montagens/revisitas, foco/reconexão, teto de retry, abort, resposta antiga tardia e troca de identidade com cache limpo.
- [ ] Inventariar invalidações compartilhadas `['inbox']` e `['overview']` antes de restringir qualquer chave; confirmar que a mutação atualiza toda superfície visível.

**Aceite:** Nenhum timer de 15 s nas telas estáveis; frescor conforme política; retries obedecem classe de erro; cache isolado por identidade; mutações e invalidações seguem corretas.

### Tarefa 6 — Eliminar N+1 de contagem de saved searches

**Responsabilidade:** Terra para API/consulta/testes; Luna para consumo frontend/teste. Contrato aditivo, mantendo endpoints atuais.

**Interface proposta:** `GET /saved-searches/summary` retorna uma lista ordenada de itens com os campos atuais de `SavedSearchResponse` (`id`, `name`, `term`, `filters`, `last_opened_at`, `created_at`) e `new_count: int` com `Field(ge=0)`. Reutilizar os campos/modelo atual em um modelo de resposta específico do summary; não adicionar campo obrigatório à resposta das rotas atuais. A listagem atual ordena `created_at DESC, id ASC`; preservar essa ordenação. Hoje não há colisão por método: rotas de `/{saved_search_id}` são PATCH/DELETE e as rotas GET usam caminho mais longo `/.../new-count`. Ainda assim, registrar `/summary` antes de qualquer futura rota GET genérica `/{saved_search_id}`.

**Passos:**

- [ ] Testar resposta para zero, uma e vinte buscas e confirmar igualdade dos totais com `GET /saved-searches/:id/new-count` atual.
- [ ] Testar isolamento entre identidades/tenants e usuário sem autorização; nenhum count de outra identidade pode vazar.
- [ ] Implementar agregação na camada de dashboard existente. Medir query count/tempo em teste ou benchmark com banco isolado `_test`, separado do harness HTTP frontend sem DB; mocks podem provar equivalência de contrato, mas não contam como evidência de custo SQL.
- [ ] Migrar Overview para uma única chamada summary e preservar estados vazios, erros e conteúdo mostrado.
- [ ] Manter endpoints antigos para callers existentes e comparar a matriz cold 0/5/20 com o mesmo harness.

**Aceite:** Overview não faz N chamadas de count; dados equivalentes e isolados; orçamento HTTP confirmado; query count/tempo SQL possui evidência do banco `_test`, ou fica explicitamente sem conclusão se só houve mocks.

### Tarefa 7 — Implementar UX aprovada nos fluxos prioritários

**Responsabilidade:** Luna para componentes/rotas, com revisão de domínio read-only; dividir arquivos por fluxo se houver mais de um executor.

**Passos:**

- [ ] Implementar primeiro os estados de Inbox e detalhe da oportunidade aprovados; usar apenas dados e ações existentes, com explicações humanas para elegibilidade, prioridade, desconhecidos, frescor e fechamento.
- [ ] Implementar Pipeline e Overview aprovados após Tarefa 6, mantendo filtros, paginação, URL e aplicação manual.
- [ ] Cobrir D6: transformar erros de objeto bruto, falha carregando e erro de API em rótulos úteis com caminho de recuperação, sem ocultar a causa nos logs estruturados.
- [ ] Adicionar testes de componentes/rotas para todos os estados (loading/error/empty/stale), labels e ações; verificar teclado/foco e alvos móveis nos viewports definidos.
- [ ] Reexecutar runner isolado e comparar capturas/erros/overflow com evidência existente, identificando explicitamente o SHA e as limitações da simulação.

**Aceite:** Fluxos aprovados cobertos sem ações automáticas; sem regressão de navegação ou contratos; acessibilidade e responsividade verificadas pelas ferramentas disponíveis, com limites manuais registrados.

### Tarefa 8 — Fechar métricas, CI e rollback local

**Responsabilidade:** Terra para harness/CI, Luna para frontend; revisão final read-only de bug e requisitos.

**Passos:**

- [ ] Rodar a mesma matriz da Tarefa 1 depois das mudanças e anexar resultado local JSON com SHA, método, endpoint normalizado, chamadas/erros/cancelamentos/retries, bytes e p50/p95 por rota.
- [ ] Confirmar budgets cold: Overview ≤5 chamadas independentes de N; Inbox ≤2; detalhe ≤4; Pipeline ≤1; revisit warm sem GET inalterado dentro do TTL; política de mutação respeitada.
- [ ] Incorporar os testes/harness repetíveis ao pipeline CI sem dependência de Clerk real, serviço externo, banco operacional ou telemetria de produção.
- [ ] Rodar testes focados de frontend (`rtk npm --prefix apps/web run test -- src/routes/InboxPage.test.tsx src/routes/OpportunityDetailPage.test.tsx src/routes/PipelinePage.test.tsx src/routes/OverviewPage.test.tsx src/routes/StatusPage.test.tsx src/lib/api.test.ts`) e `rtk npm --prefix apps/web run check` quando aplicável.
- [ ] Rodar backend sem rebuild: `rtk proxy docker compose -p or_plan_20261016 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/opportunities/test_regions.py tests/backend/opportunities/test_measure_seniority_titles.py tests/backend/opportunities/test_run_closures.py tests/backend/acquisition/test_target_area_share.py tests/backend/acquisition/test_filtered_presence.py tests/backend/dashboard/test_saved_searches.py tests/backend/dashboard/test_tenancy.py`. Só reconstruir se mudar Dockerfile ou `requirements*.txt`.
- [ ] Se qualquer teste de integração de DB for necessário, usar somente base isolada `_test` com `RUN_DATABASE_INTEGRATION=1`, `DATABASE_INTEGRATION_ISOLATED=1` e `DATABASE_URL` isolada; executá-lo uma vez ao final.
- [ ] Documentar rollback por commit/reversão local e limites de evidência. Não publicar, fazer merge, deploy, migração operacional ou operação de cloud neste plano.

**Aceite final:** Todos os ACs de regra, UX e tráfego possuem teste e evidência antes/depois comparável; contagem não mascara retries/cancelamentos; nenhum critério de produção é inferido de fixture; aprovação do protótipo e autorização de release permanecem gates separados.

### Asserts mínimos por fluxo

Use estes asserts como contrato de aceite; os nomes concretos dos testes devem seguir a convenção existente nos módulos.

| Fluxo | Asserts positivos | Asserts negativos / fronteiras |
| --- | --- | --- |
| País e área | Campo estruturado explícito compatível conserva a oportunidade e cita a evidência | Campo ausente, área incerta, escritório em país diferente ou texto de IA isolado não causa descarte; status vai para revisão |
| Senioridade | Evidência de nível reconhecido explica a classificação | Ausência/conflito de evidência não inventa nível; explicação não contradiz resultado |
| Fechamento | Duas execuções completas consecutivas sem ocorrência permitem fechamento conforme regra existente | `skipped_stale`, parcial, falha, detalhe indisponível ou outra ocorrência ativa não conta como ausência |
| Inbox e detalhe | Labels em português, fatores e próxima ação existente aparecem com dados carregados | Enum não traduzido, `[object Object]`, score alterado pela IA ou ação automática falha o teste |
| Cache e retry | Mount e retorno após stale recuperam dados; retry transitório GET respeita teto | Cinco minutos estáveis geram zero timer GET; auth/validação/conflito/429/escrita não repetem automaticamente |
| Identidade e cancelamento | Após mudança de usuário, só dados da identidade corrente aparecem | Resposta tardia do usuário anterior não substitui tela; abort de GET não cancela mutação confirmada |
| Resumo de buscas salvas | 0/1/20 totais iguais ao contrato antigo em uma requisição summary | Identidade não autorizada não vê contagens; regressão SQL é relatada mesmo se HTTP cair |
| Estado visual | Loading, erro, vazio e stale orientam próximo passo real | Erro não vira vazio silencioso; stale não é descrito como atualizado; foco não some ao filtrar |

### Evidência de usabilidade e proteção contra regressão

- Propor ao usuário tarefas observáveis: localizar motivo de prioridade, encontrar lacuna de evidência, revisar oportunidade com geografia incerta e localizar próxima ação manual. Registrar tempo, sucesso, erro e pedido de ajuda por tarefa.
- Antes/depois deve usar mesma tarefa, viewport, dados e instruções. Se não houver participantes ou amostra comparável, registrar apenas avaliação qualitativa e não declarar ganho percentual.
- Confirmar URLs diretas e navegação com filtros ativos; voltar/avançar do navegador deve preservar o estado já previsto pela rota.
- Conferir que busca da Inbox continua disparando somente no submit e que paginação continua sendo server-side nas opções 10/25/50/100.
- Revisar captura do fluxo principal a 360/768/1440 px, erro de rede, lista vazia e conteúdo longo traduzido; registrar overflow, clipping, foco e ação de recuperação.
- Falha de harness, rede externa inesperada ou resposta fixture não cadastrada invalida aquela execução; não converter falha em contagem zero.
- Guardar resultados locais pequenos com commit/hash e configuração sanitizada; excluir segredos, conteúdo pessoal, cache, `.worktrees` e dados privados de commits.

## Definição de concluído

- Regras aprovadas incluem matriz de exemplos, explicações e testes positivos/negativos/desconhecidos; nenhum campo ausente vira descarte automático.
- UX implementada corresponde a protótipo explicitamente aprovado, preserva fluxos e ações manuais, e registra resultados de teclado, foco, responsividade e contraste com limites claros.
- Volume de chamadas e latência comparados antes/depois na mesma fixture/coorte, com sucesso, erro, cancelamento e retry discriminados; budgets atendidos ou revistos com justificativa mensurável.
- Saved-search summary reduz o fan-out de HTTP e sua query é medida; não há alegação de custo SQL constante sem evidência.
- Testes focados e checks aplicáveis têm saídas literais registradas; nenhuma validação não executada é alegada.
- Benchmark de usabilidade com participantes pode propor meta exploratória de 20% menos tempo para localizar justificativa e próxima ação; não é promessa nem gate até protocolo, amostra e tarefa serem aprovados.
- Nenhuma publicação, merge, deploy, operação de cloud ou validação em banco operacional ocorre como parte desta execução.

## Incertezas que exigem decisão/evidência antes de codificar

- Matriz final de países, exceções remotas, níveis de senioridade e efeitos permitidos no score.
- Esquema final do summary, custo real da agregação SQL e comportamento de N buscas no dataset representativo.
- Budgets HTTP/latência após captura real de baseline no novo SHA; a estimativa dos polls e chamadas estática não substitui runtime.
- Conteúdo e aceite visual dos protótipos F, além de validação manual de leitor de tela, zoom, reduced motion, contraste final e dispositivos físicos.
- Branch remoto atual e estado das worktrees precisam ser verificados no início; os valores registrados refletem apenas inspeção local sem fetch.

## Evidência desta revisão documental

Nesta rodada houve somente inspeção estática de arquivos, branches/worktrees e árvore local de `origin/main`, além de revisão documental das referências TanStack Query citadas. Não foram executados testes, builds, benchmarks, medições de runtime, consultas de banco ou validações de integração. As frequências 240/h por instância e 21 chamadas para o bloco de lista + contagens com 20 buscas são cálculos do código estático, não medições operacionais.

