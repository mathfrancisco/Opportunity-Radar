# SPEC 54 — redesign completo do frontend

**Status:** planejamento condicionado. Implementação somente depois que F53 for
aceita com evidência operacional e que o aceite visual desta SPEC esteja
registrado. Documentação ou configuração pronta, isoladamente, não satisfaz F53.

**Data:** 2026-10-07.

## 1. Decisão e gates

A direção selecionada é um **workspace claro e sóbrio**, centrado nas vagas e
na organização da busca. Não é um painel administrativo genérico, nem uma
composição editorial exagerada. A identidade detalhada e os protótipos ainda
dependem de aceite visual.

| Gate | Evidência antes de implementar |
| --- | --- |
| Visual | aceite dos três protótipos da seção 7 |
| F53 | hospedagem, Clerk, testes isolados, backup/restore, cutover e baseline aceitos |
| Contratos | rotas, respostas, ações e permissões atuais inventariadas |
| Baseline | mesmas jornadas, fixtures anonimizados, requisições, bundle e capturas registrados |
| Segurança | Clerk real confirmado; sem bypass, token real ou endpoint inferido |

O escopo é interface: composição, componentes, responsividade, acessibilidade,
testes e release. Estão fora de escopo backend, jobs, banco, endpoints, coleta,
infraestrutura, custo e polling. A interface não deve introduzir consultas
recorrentes que mantenham o Neon ativo.

F53 será considerada aceita somente após concluir os critérios de aceite e
evidências de [seu plano e roadmap](53-plano-hospedagem-cloudflare-oracle-neon-clerk.md),
incluindo os gates de backup/restauração, isolamento de testes, autenticação,
cutover e smoke operacional. Uma checklist ou pipeline definido sem execução e
evidência não libera esta SPEC.

## 2. Resultado esperado

O primeiro olhar responde quais vagas pedem decisão, o que está aguardando e em
que etapa está cada candidatura. Visão geral, Inbox e Pipeline têm prioridade
sobre fontes, homologação e status. A navegação pode mudar visualmente; URLs,
deep links, contratos, regras de domínio e ações existentes não.

O workspace oferece contexto sem competir com a decisão, comparação de vagas
legível, formulários inequívocos, incerteza explícita e uma identidade própria
em azul-petróleo, slate e tinta. Não deve herdar a aparência padrão do kit que
eventualmente fornecer primitives.

## 3. Base atual confirmada

O aplicativo usa React 19, Vite 8, Tailwind 4, React Router 7 e TanStack Query
5. `Inter Variable` já é local. `DESIGN.md` continua normativo até uma fase
aprovada alterá-lo junto do CSS; esta SPEC não o altera.

`AppShell` já fornece sidebar desktop, gaveta mobile, skip link, Escape para
fechar a gaveta e retorno de foco ao botão de menu. O redesign preserva esses
comportamentos ou prova uma alternativa acessível equivalente.

### 3.1 Rotas e deep links

| URL | Objetivo preservado | Prioridade |
| --- | --- | --- |
| `/` | Visão geral, métricas e atividade | 1 |
| `/inbox` | Triagem e buscas salvas | 1 |
| `/opportunities/:opportunityId` | Evidências, análise e ação sobre vaga | 2 |
| `/applications` | Pipeline de candidaturas | 1 |
| `/companies` | Pesquisa de empresas | 3 |
| `/companies/:companyId` | Contexto e fontes de empresa | 3 |
| `/sources` | Fontes, controles e entrada manual | 4 |
| `/sources/homologation-queue` | Fila de homologação | 4 |
| `/profile` | Perfil e versões de matching | 4 |
| `/status` | Saúde e prontidão | 4 |
| `*` | hoje renderiza Visão geral | preservar; 404 exige escopo aprovado |

Esta SPEC não cria redirect, callback ou endpoint. Depois de F53, login, logout,
sessão expirada, `forbidden` e owner serão desenhados contra o Clerk realmente
entregue, sem assumir fluxo de autenticação ausente hoje.

### 3.2 Componentes e features

| Área | Inventário a auditar | Regra do redesign |
| --- | --- | --- |
| Estrutura | `AppShell`, `Sidebar`, `PageHeader`, `PageShell` | preservar landmarks, skip link e foco |
| Ações | `Button`, `Field`, `SearchInput`, filtros e toolbar | variantes por intenção, sem ação nova |
| Dados | `DataTable`, paginação, células e `Chip` | comparação desktop e alternativa mobile |
| Estados | skeletons, `Unavailable`, `StatusBadge` | contrato visual consistente |
| Painéis/forms | application, intake, empresa, fonte e controles | edição, validação e confirmação inequívocas |
| Features | oportunidades, pipeline, empresas, fontes, matching, perfil e buscas salvas | consultas e decisões de domínio preservadas |

O inventário de implementação deve partir do conjunto completo atual de
componentes em `apps/web/src/components/`, incluindo `AnalysisPanel`,
`ApplicationPanel`, `CompanyForm`, `CompanySourceForm`, `DataTable`, `FilterBar`,
`FilterPill`, `HomologationQueue`, `ManualIntakePanel`, `PageSizeSelect`,
`Pagination`, `SearchInput`, `SourceControlsPanel` e `SourceCreateForm`, além de
ícones, células, skeletons e estados. Antes de migrar cada rota, registrar seus
imports, dependências de domínio, exports usados e testes. A lista é um piso:
conferir todos os arquivos com `rg --files apps/web/src/components` para não
deixar componente ativo fora da auditoria.

Primitives visuais terão wrappers da aplicação em `components/ui/`; componentes
que carregam comportamento de domínio continuam em módulos de feature/domínio.
Evitar imports de biblioteca espalhados por rotas e formulários: a troca de
primitive deve permanecer localizada no wrapper e preservar contratos acessíveis.

## 4. Diferenças concretas da SPEC 46

A SPEC 46 é o baseline já implementado. A SPEC 54 substitui as decisões abaixo
somente depois dos gates; não é apenas troca de cores.

| SPEC 46 atual | Proposta SPEC 54 | Preservação |
| --- | --- | --- |
| painel administrativo claro, neutro e compacto | workspace de carreira sóbrio, focado em decisão | dados, URLs e ações |
| acento laranja e marca lima | azul-petróleo para orientação; estados continuam semânticos | contraste medido |
| sidebar como inventário de áreas | grupos Decidir, Pesquisar e Operar | gaveta e teclado |
| tabela dominante | tabela para comparação; cards/resumo em largura estreita | filtros e paginação |
| sem biblioteca além de D3 | spike controlado de primitives | dependências só com evidência |
| status com peso de operação principal | operação menos proeminente | status continua acessível |

Segurança, ausência de mudança de domínio e acessibilidade da SPEC 46 permanecem.
Se SPEC 46, `DESIGN.md`, CSS e código divergirem, WP0 registra a divergência;
o implementador não escolhe em silêncio.

## 5. Sistema visual

### 5.1 Hierarquia e navegação

A sidebar fica nesta ordem visual: **Decidir** (Visão geral, Inbox, Pipeline),
**Pesquisar** (vaga por deep link e Empresas) e **Operar** (Fontes,
Homologação, Perfil, Status). É só reorganização visual: os endereços permanecem.

Cada página tem pergunta principal no cabeçalho, uma ação primária somente quando
ela já existir e contexto opcional. A área de decisão aparece antes; filtros e
operações auxiliares ficam com a lista que alteram, sem segunda navegação.

### 5.2 Tokens candidatos

Os valores são linguagem de protótipo, não tokens aprovados. Antes de entrar no
CSS, cada par texto/fundo e cada contorno passa WCAG 2.2 AA aplicável.

| Papel | Proposta | Uso |
| --- | --- | --- |
| canvas | slate muito claro | fundo externo |
| surface | branco suave | painéis, forms e tabelas |
| ink | slate quase preto | títulos e foco |
| muted | slate médio | metadados; nunca sinal exclusivo |
| accent | azul-petróleo escuro | ação primária, links e item atual |
| accent soft | azul-petróleo claro | seleção e contexto |
| cores de estado | success/warning/danger/info | significado, não marca |

Inter Variable permanece inicial. Título de página: 24–28 px; seção: 18–20 px;
corpo: 14–16 px; metadados: 12–14 px. A escala final usa tokens por papel,
line-height legível e números tabulares em métricas. Espaçamento usa 4 px; 16–24
px em decisão e 8–12 px em listas densas. Painéis usam borda sutil e elevação
apenas em sobreposição real.

Foco visível terá contorno de ao menos 3 px com offset. Motion é curta e respeita
`prefers-reduced-motion`. Light é o baseline; dark mode fica fora até aceite,
contraste e inventário próprios.

O objetivo é WCAG 2.2 AA: texto com contraste mínimo 4.5:1, componentes e
contornos visuais 3:1, alvos de toque de pelo menos 24 CSS px (WCAG 2.2 AA),
preferencialmente 44 px em jornadas móveis conforme padrão do projeto. Esses
valores são requisitos a medir na implementação, não resultados já verificados.

## 6. Primitives: escolha após spike

| Alternativa | Vantagem | Pergunta do spike |
| --- | --- | --- |
| shadcn customizado com Radix ou Base UI | gera apenas o usado e permite identidade própria | uma família de primitives, licença, React 19, Vite 8, Tailwind 4, teclado e bundle funcionam? |
| React Aria | primitives e modelo de acessibilidade fortes | estilos/Tailwind, bundle e componentes atuais se integram? |
| MUI | biblioteca completa e madura | peso e esforço para não parecer padrão são aceitáveis? |

A recomendação inicial é shadcn estilizado pela identidade desta SPEC, somente
para primitives necessárias. Não será instalado como kit padrão. O spike
descartável com botão, campo, dropdown, diálogo e tabela registra versões,
licenças, árvore de dependências, `npm run check`, build, gzip e teclado. Radix
ou Base UI é decidido por evidência, não por preferência.

Fontes: [shadcn com Vite](https://ui.shadcn.com/docs/installation/vite),
[componentes shadcn](https://ui.shadcn.com/docs/components),
[acessibilidade Radix](https://www.radix-ui.com/primitives/docs/overview/accessibility)
e [qualidade React Aria](https://react-aria.adobe.com/quality).

## 7. Aceite visual

O aceite exige protótipos navegáveis ou capturas estáticas em 1440, 768 e 360 px.
Aprovar uma paleta não basta. Os três protótipos obrigatórios são **Inbox,
Detalhe da vaga e Pipeline**; Visão geral é um protótipo adicional de coerência
de hierarquia e navegação.

1. **Inbox:** busca, filtros existentes, lista de vagas e vazio por filtro.
2. **Detalhe da vaga:** evidências, análise consultiva, decisão humana e estados
   de indisponibilidade sem inventar ações.
3. **Pipeline:** estágios existentes, cartões legíveis e alternativa acessível à
   leitura horizontal.
4. **Visão geral (adicional):** decisões e métricas que levam a ação; operação
   secundária.

O revisor confirma identidade sóbria, prioridade, foco, texto longo, viewport
estreito, status semântico e ausência de nova operação/filtro. Mudança posterior
ao aceite vira decisão registrada.

## 8. Estados e autenticação

| Estado | Aplicação | Contrato visual |
| --- | --- | --- |
| carregando | listas, detalhe e painéis | skeleton conserva geometria; não apresenta dado antigo como atual |
| vazio | Inbox, empresas, fontes, pipeline, buscas | distingue sem dados de filtro sem resultado; ação só se já existir |
| erro | consulta ou mutação | mensagem clara e retry apenas onde o fluxo atual permitir |
| stale | dado renderizado que atualiza | informa contexto/tempo sem bloquear ou criar polling |
| parcial | coleta, análise ou campo incompleto | expõe falta e proveniência |
| não autenticado | só após Clerk | entrada e retorno conforme contrato entregue |
| forbidden/owner | só após regra real | não revela dado e não simula owner |
| 409 | quando endpoint atual retornar | preserva edição local; orienta revisar/recarregar |

Fixtures não contêm token, chave ou conta real. Não criar estado de auth até F53
entregar bibliotecas, regras e rotas usadas de fato.

## 9. Matriz de telas, mobile e provas

| Tela | Desktop e objetivo | 320/360/768 | Fluxo/estado | Prova |
| --- | --- | --- | --- | --- |
| Visão geral | decisão acima de métricas/listas | uma coluna; ações sem corte | loading, parcial, erro | captura nas larguras |
| Inbox | filtros e lista comparável | filtros empilhados; cartões decisivos | vazio, paginação, buscas | filtros e detalhe |
| Detalhe vaga | evidências, análise, candidatura | blocos lineares; URLs quebram | parcial e análise indisponível | deep link e foco |
| Pipeline | estágios e cartões | lista por estágio, sem drag-and-drop novo | vazio, loading, falha | teclado e leitura |
| Empresas | busca e comparação | cards ou rolagem anunciada | vazio, paginação, erro | busca e detalhe |
| Detalhe empresa | contexto, fontes e forms | campos largura total | validação e mutação | form e deep link |
| Fontes | painéis de operação | uma coluna | parcial, falha, intake | cada painel |
| Homologação | fila com evidência | cartões com proveniência | vazio, erro, decisão | tabulação e ação |
| Perfil | versões e matching | campos lineares e labels | validação e salvo | teclado |
| Status | prontidão secundária | cartões de verificação | indisponível e stale | sem consulta extra |
| wildcard | Visão geral atual | como raiz | não mascara teste de rota | URL desconhecida |

Tabelas têm cabeçalhos e nome acessível. Em largura estreita, usar cards
equivalentes, detalhe expansível ou rolagem explicitamente indicada. Kanban tem
alternativa sem arrastar. Diálogos contêm foco, fecham por Escape quando seguro,
devolvem foco ao gatilho e possuem título/descrição. Campos mantêm `label` e
erro associado programaticamente.

O roteiro percorre 320, 360, 768, 1280 e 1440 px. WCAG 2.2 AA cobre contraste,
tabulação, skip link, foco, zoom, alvos de toque, tabela/cartão e leitor de tela.
O E2E já contém `tests/e2e/browser/specs/03-visual.spec.ts` com capturas em
1280/375 e overflow em 320; é baseline de evidência, não comparação pixel
automática, e deve ser preservado e estendido.

## 10. Desempenho e dados

Antes de trocar componentes, registrar no mesmo navegador e fixtures
anonimizados: jornadas, capturas, contagem de requisições por tela, JavaScript
gzip por build, ativos, cache e tempos observáveis. São baseline, não metas
inventadas. Cada fase repete o mesmo roteiro.

Lazy imports só entram onde profiling mostrar fronteira útil. Não introduzir
polling, retry recursivo, prefetch global ou health check de banco. Queries
mantêm chaves, invalidações e tratamento atual até mudança de contrato aprovada.

## 11. Pacotes de trabalho pós-gate

| Pacote | Passos | Aceite/evidência |
| --- | --- | --- |
| WP0 baseline | confirmar gates, contratos, capturas e medidas | checklist, fixtures anonimizados, artefatos datados |
| WP1 spike | comparar alternativas em página isolada | licença, compatibilidade, check, build, gzip, teclado e decisão |
| WP2 protótipos | Inbox, Detalhe da vaga e Pipeline; Overview adicional | aceite visual registrado antes da migração |
| WP3 sistema | atualizar `DESIGN.md`, CSS e wrappers juntos após aceite | tokens, contraste, foco, motion e primitives verificados |
| WP4 prioritárias | Overview, Inbox, Detalhe da vaga e Pipeline | estados, capturas, jornadas e contratos preservados |
| WP5 demais rotas | Companies, Company Detail, Sources, Homologation, Profile, Status e wildcard | ações atuais, forms e estados indisponíveis |
| WP6 auth/regressão | somente com F53 entregue, estados Clerk reais | fixtures offline; autorizado/anônimo/forbidden/owner conforme contrato |
| WP7 release | preview, smoke cloud autorizado, comparação e promoção | artefato anterior imutável e rollback frontend testado |

### 11.1 Execução detalhada dos pacotes

1. **WP0 — baseline e inventário:** após aceite de F53, registrar versões e
   verificar os refetchers de consultas que podem impedir o Neon de suspender:
   hoje `apps/web/src/features/dashboard/useInbox.ts` e
   `apps/web/src/features/matching/useAssessment.ts` definem `refetchInterval:
   15_000`. Confirmar se F53 os removeu ou limitou e provar o comportamento de
   idle antes de liberar implementação. Se polling ainda acordar o banco, bloquear
   a implementação até decisão/correção no escopo autorizado de F53. Preservar
   queries somente depois dos ajustes aceitos, sem aumentar chamadas ao serviço.
   exports do `apps/web/src/components`, mapa rota → componentes → queries e
   mutações → testes, fixtures anonimizados e capturas de Overview, Inbox,
   Detalhe, Pipeline e todas as rotas restantes. Medir requisições, bundle gzip,
   tempos observáveis e comportamento a 320/360/768/1280/1440 px. Confirmar
   endpoints, limites de autenticação/owner e contratos no estado pós-F53.
2. **WP1 — spike isolado:** usar o projeto existente em branch/rota de spike
   descartável. Não gerar outro Vite app. Não executar `init` automaticamente
   sobre CSS/config atuais. Testar alterações somente em branch descartável,
   preservando o baseline e revisando cada diff antes de integrar. Comparar React
   Aria, MUI e a opção
   shadcn com uma única família Radix ou Base UI. Fixar versão, licenças, lockfile,
   compatibilidade React/Vite/Tailwind, gzip, teclado, leitor de tela e
   `npm run check`; registrar decisão antes de integrar.
3. **WP2 — aceite dos protótipos:** produzir Inbox, Detalhe e Pipeline, mais
   Overview de coerência; mostrar viewports desktop e mobile, texto longo, vazio,
   carregamento e erro. Registrar aceite visual explícito antes da migração.
4. **WP3 — sistema e wrappers:** atualizar `DESIGN.md` e CSS no mesmo pacote;
   incluir tokens por papel, resultados de contraste medidos, foco e motion.
   Implementar primitives em `components/ui/` e wrappers de domínio onde
   necessários; manter os imports da biblioteca fora das páginas e forms.
5. **WP4 — telas prioritárias:** migrar Overview, Inbox, Detalhe da vaga e
   Pipeline em passos pequenos, reutilizando queries/mutações atuais. Preservar
   filtros, paginação, links, candidaturas manuais e estados. Cada tela compara
   capturas e jornada ao baseline antes de avançar.
6. **WP5 — demais rotas e forms:** migrar Companies, Company Detail, Sources,
   Homologation Queue, Profile, Status e wildcard. Migrar intake, forms de
   empresa/fonte, controles e painéis de análise; conferir exports e testes de
   cada componente antes de removê-lo ou consolidá-lo.
7. **WP6 — Clerk e regressão:** só usar SDK, middleware visual e estados que
   F53 tenha realmente entregue. Cobrir sessão ausente/expirada, login/logout,
   forbidden e owner conforme contrato verificável; manter testes offline com
   fixtures. Executar testes focados e `npm run check` em `apps/web`. Para E2E,
   usar ambiente isolado existente com `_test`, `RUN_DATABASE_INTEGRATION=1` e
   `DATABASE_INTEGRATION_ISOLATED=1`; nunca apontar testes ao banco operacional.
8. **WP7 — preview e release:** publicar preview somente no caminho autorizado
   após F53; verificar autenticação Clerk, abertura direta das 10 rotas, deep
   links, larguras e jornadas. Repetir baseline de performance e capturas. Manter
   artefato frontend anterior imutável e provar rollback sem migração/alteração
   de dados antes de promover.

### 11.2 Critérios de aceite rastreáveis

| ID | Requisito | Prova exigida |
| --- | --- | --- |
| AC54-01 | F53 operacional aceita e documentada | gates e evidências do plano/runbook revisados; Clerk real e backup/restore verificados |
| AC54-02 | identidade e hierarquia aprovadas | aceite explícito dos protótipos Inbox, Detalhe, Pipeline e coerência Overview |
| AC54-03 | biblioteca e versões selecionadas | decisão do spike, licenças, família única, lockfile e compatibilidade registradas |
| AC54-04 | componentes e tokens migrados sem regressão | inventário completo, wrappers, contraste/foco/motion medidos e testes unitários |
| AC54-05 | contratos e domínio preservados | testes focados de queries, filtros, scores, análise, forms e mutações existentes |
| AC54-06 | responsividade nas 10 rotas | E2E/capturas em 320/360/768/1280/1440 e abertura por URL direta |
| AC54-07 | acessibilidade WCAG 2.2 AA verificada | teclado, leitor de tela, foco, rótulos, contraste e zoom registrados |
| AC54-08 | auth corresponde ao Clerk entregue | testes offline e smoke autorizado para login, sessão expirada, forbidden/owner aplicáveis |
| AC54-09 | performance dentro do orçamento aceito | comparação antes/depois; bundle gzip inicial não cresce mais de 10% sem aceite explícito; sem aumento de requisições sem justificativa/aceite |
| AC54-10 | release e rollback demonstrados | preview aprovado, smoke das rotas/jornada e retorno ao artefato anterior provado |

Fechamento exige aceite explícito dos protótipos e evidência de todos os dez
critérios. Critério sem teste aplicável precisa de justificativa registrada e
aceite antes de ser considerado atendido; status planejado não equivale a aceite.

Em cada pacote, começar pelas rotas e testes afetados; usar fixtures anonimizados
e nunca banco operacional. O check confirmado é `npm run check` em `apps/web`.
O E2E está em `tests/e2e/browser`, configurado por
`tests/e2e/browser/playwright.config.ts`; o workflow executa `npx playwright test`
nesse diretório contra Compose preparado. Testes novos seguem esse caminho
e dados isolados; não criam segunda stack.

## 12. Cobertura e rollback

| Camada | Cobertura |
| --- | --- |
| Componentes | variantes, desabilitado/erro, labels, foco e motion reduzido |
| Rotas | dez rotas, parâmetros, wildcard e larguras da seção 9 |
| Fluxos | filtro/paginação, vaga, formulário, pipeline, homologação e disponibilidade |
| Autorização futura | anônimo, expirada, autorizado, forbidden e owner com fixture Clerk offline |
| Browser | jornadas e screenshots existentes, dados determinísticos |
| Performance | comparação antes/depois no mesmo fixture, com número medido |

Preview é revisado antes de promover. Smoke cloud só depois de F53 verifica
renderização, rota direta, autenticação existente e uma jornada de leitura. O
rollback seleciona artefato frontend imutável anterior; não executa migração,
limpeza ou alteração de dados.

As regras de domínio continuam sendo as verificadas no código e contratos
vigentes no momento da execução: matching determinístico, score e elegibilidade
calculados fora da IA, análise de IA apenas consultiva, adesão a termos antes de
habilitar fonte, homologação manual e CRM de candidatura sob decisão humana.
Nenhum redesenho pode transformar sugestão em veredito, alterar score, habilitar
fonte, aprovar candidato ou automatizar candidatura. Após F53, conferir de novo
autorização, owner imutável, respostas e estados reais antes de desenhar auth;
esta SPEC não afirma que esses controles de hospedagem já estejam implantados.

## 13. Decisões pendentes

1. Os três protótipos foram aceitos sem ampliar ações, filtros ou contratos?
2. Qual primitive venceu por licença, compatibilidade, acessibilidade e bundle?
4. Quais telas e mensagens Clerk existem de fato após F53?
5. Dark mode continua fora desta entrega?

## Referências de execução F53

- [Plano F53](53-plano-hospedagem-cloudflare-oracle-neon-clerk.md).
- [Roadmap e cards F53](53-roadmap-hospedagem/README.md), em especial
  [F53-07 Clerk/API](53-roadmap-hospedagem/cards/f53-07-clerk-autorizacao-api.md),
  [F53-08 Clerk/Pages](53-roadmap-hospedagem/cards/f53-08-clerk-pages-frontend.md),
  [F53-14 backup/restore](53-roadmap-hospedagem/cards/f53-14-backup-restore.md),
  [F53-15 testes isolados](53-roadmap-hospedagem/cards/f53-15-ci-testes-isolados.md),
  [F53-16 aceite pós-deploy](53-roadmap-hospedagem/cards/f53-16-aceite-pos-deploy.md)
  e [F53-18 cutover/rollback](53-roadmap-hospedagem/cards/f53-18-cutover-rollback-recuperacao.md).
- [Runbook](30-runbook.md), para operação e evidência de backup/restauração.

## Referências

- [DESIGN.md](../DESIGN.md), norma visual atual até fase aprovada.
- [SPEC 46](46-spec-redesign-ui.md), baseline e decisões anteriores.
- [shadcn com Vite](https://ui.shadcn.com/docs/installation/vite).
- [componentes shadcn](https://ui.shadcn.com/docs/components).
- [acessibilidade Radix](https://www.radix-ui.com/primitives/docs/overview/accessibility).
- [qualidade React Aria](https://react-aria.adobe.com/quality).
