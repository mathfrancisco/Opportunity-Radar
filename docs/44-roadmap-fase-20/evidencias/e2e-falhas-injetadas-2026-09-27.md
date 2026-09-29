# Percurso E2E no navegador com falhas injetadas — evidência local, 2026-09-27

Evidência de execução real para o card F20-47, branch `feature/f20-47-e2e`. Toda a
verificação rodou numa pilha Docker Compose isolada (`-p f20e2e47`, `compose.yaml` +
`compose.ci.yaml`, com um override local de portas só para evitar colisão com outros
projetos Compose já em uso na máquina — `18000:8000` e `13000:8080`). A pilha real
`opportunity-radar` (dados do usuário) não foi tocada, iniciada, parada nem sofreu `down -v`
em nenhum momento; confirmado com `docker ps -a` antes e depois.

## Resumo

| Critério | Veredito | Evidência |
| --- | --- | --- |
| Percurso completo passa sem terminal | **Passa** | `specs/01-happy-path.spec.ts`, §2 |
| Todos os cenários de falha passam | **Passa** — 6/6 | `specs/02-failure-scenarios.spec.ts`, §3 |
| Evidências anexadas no CI | **Implementado, não confirmado em CI real** | §4 |

## 0. O que foi construído

- `tests/e2e/browser/`: projeto Node/Playwright autônomo (`package.json`,
  `playwright.config.ts`, `tsconfig.json`), com `support/api.ts` (seed de perfil e fonte via
  API pública, iguais aos passos já existentes de `pipeline.yml`) e `support/compose.ts`
  (injeção de falha via `docker compose exec`, sem reiniciar os containers no meio do teste).
- `tests/e2e/fake_groq.py`: `FAKE_GROQ_MODE` (`ok`/`429`/`500`/`invalid`) como modo inicial,
  e um arquivo de controle (`/tmp/fake_groq_mode`) para trocar o modo em tempo real sem
  derrubar a conexão que um teste de navegador está usando.
- `tests/e2e/fake_job_board.py`: mesmo mecanismo para `ok`/`partial` (manifesto cujo
  `meta.total` é maior que os jobs devolvidos) e `304` (resposta condicional a
  `If-None-Match`).
- `.github/workflows/pipeline.yml`: o job `e2e` ganhou um passo que restaura a agenda normal
  do worker (o passo de kill switches, mais adiante no mesmo job, a desliga) e roda
  `npx playwright test` por último — depois de toda asserção de contagem fixa das etapas
  anteriores (`opportunities_total == 1`, etc.), porque o percurso do navegador semeia seu
  próprio perfil/fonte/oportunidade e quebraria essas asserções se rodasse antes delas.

## 1. Achado corrigido durante a verificação: ordem dos arquivos de teste

O breaker de circuito do roteador de IA (`platform/ai/breaker.py`) é estado em memória do
processo `api`/`worker`, não por teste: uma vez aberto por uma falha do Groq (429/500), toda
chamada real de análise responde `QUOTA_EXHAUSTED` por ~120s, mesmo depois do modo do
`fake_groq` voltar para `ok`. Como os dois arquivos de spec rodam no mesmo job/processo, a
ordem alfabética original (`failure-scenarios` antes de `happy-path`) fazia o percurso feliz
tentar sua análise real *depois* que os cenários de falha já tinham aberto o breaker — a
análise do percurso feliz sempre voltava degradada, mesmo com o Groq saudável de novo.
Corrigido renomeando os arquivos com prefixo numérico (`01-happy-path.spec.ts`,
`02-failure-scenarios.spec.ts`), documentado em `playwright.config.ts`. Depois da correção,
duas corridas limpas consecutivas (stack recriada do zero entre elas) fecharam 7/7 verde.

## 2. Percurso feliz (`01-happy-path.spec.ts`)

Um teste, cobrindo o ciclo completo pela UI:

1. `/profile` — perfil preenchido do zero (skills, país, modalidade, contrato) e salvo.
2. Preferência editada num segundo salvamento (nova versão ativa).
3. Fonte Greenhouse homologada semeada via API (`board_token: radar-ci`, o mesmo board
   falso que `pipeline.yml` já usa) — a homologação em si é outro fluxo, já coberto por
   outros cards; aqui só precisa existir e estar habilitada antes do teste abrir o
   navegador.
4. `/sources` — "Executar agora" na fonte semeada, dispara a coleta.
5. `/inbox?search=...` — a vaga aparece (normalização/avaliação automáticas do worker).
6. Abre a vaga, clica "Avaliar agora" (decisão determinística) e "Analisar com IA"
   (semântica), com retentativa em caso de 409 (a análise pode estar sob a claim do próprio
   job `analyze_pending` do worker no mesmo instante — 409 é "tente de novo", não falha; ver
   `analyzeAssessment` em `features/matching/api.ts`).
7. Painel de candidatura — "Registrar interesse", confirma o histórico.

Comando local:

```
docker compose -p f20e2e47 -f compose.yaml -f compose.ci.yaml -f <override-de-portas> \
  down --volumes --remove-orphans
docker compose -p f20e2e47 -f compose.yaml -f compose.ci.yaml -f <override-de-portas> \
  up --detach api worker frontend
cd tests/e2e/browser && npx playwright test specs/01-happy-path.spec.ts
```

Resultado: 1/1 passou, ~40-60s.

## 3. Cenários de falha (`02-failure-scenarios.spec.ts`)

Uma fonte e uma oportunidade semeadas uma vez (`beforeAll`), reaproveitadas por todos os
cenários (`test.describe.serial`, `workers: 1` no config — um cenário por vez, contra a
mesma pilha):

| Cenário | Injeção | Verificado |
| --- | --- | --- |
| Groq 429 | `setGroqMode('429')` | Banner "Camada semântica degradada", decisão determinística intacta (Filtros eliminatórios/Fatores do score seguem visíveis), Inbox mostra a vaga sem comentário de IA, sem duplicata, não encerrada |
| Groq 500 | `setGroqMode('500')` | Idem |
| Groq inválido | `setGroqMode('invalid')` (corpo JSON sem os campos do schema) | Idem |
| Paginação parcial | `setBoardMode('partial')` (`meta.total` maior que os jobs devolvidos) | Execução `SUCCEEDED`, sem duplicata, oportunidade não encerrada |
| 304 Not Modified | `setBoardMode('304')` | Execução `SUCCEEDED` (0 itens, conforme esperado), sem duplicata, oportunidade não encerrada |
| Restart do worker no meio da coleta | `docker compose restart worker` disparado em paralelo com o clique em "Executar agora" | Worker volta saudável (`/health/ready`), sem duplicata, oportunidade não encerrada |

Comando local: `npx playwright test specs/02-failure-scenarios.spec.ts`.

Resultado: 6/6 passaram, ~13-25s (depende de quanto o worker demora a reagendar).

## 4. Evidências no CI

`playwright.config.ts` grava `screenshot: 'on'` (toda corrida, não só falha) e
`trace: 'retain-on-failure'`; `pipeline.yml` adiciona um passo
`actions/upload-artifact` (`f20-47-browser-e2e-evidence`, `tests/e2e/browser/test-results/`
e `report/`, `if: always()`). Isto está implementado e testado localmente (os artefatos
aparecem em `tests/e2e/browser/test-results/` depois de cada corrida), mas **a confirmação
de que o job `e2e` publica esse artefato em CI real depende do push do coordenador** — não
foi possível rodar o GitHub Actions daqui.

## 5. Comandos de verificação rodados

```
cd apps/web && npm ci && npm run check
# lint, typecheck, 28 arquivos/145 testes, build — todos verdes

ruff check tests/e2e/fake_groq.py tests/e2e/fake_job_board.py
# All checks passed

cd tests/e2e/browser && npx tsc --noEmit -p tsconfig.json
# No errors found
```

`mypy` não roda sobre `tests/e2e/*.py`: o gate do projeto (`[tool.mypy].files` em
`pyproject.toml`) só cobre `src`, `apps` (Python) e `scripts/search_reference.py`. Nenhum
arquivo de `src/opportunity_radar` foi alterado por este card, então nenhum teste de backend
(`pytest`) precisou rodar — a mudança inteira é: dois servidores falsos de teste, um projeto
Node novo em `tests/e2e/browser/`, e o workflow de CI.

## 6. Falha real em CI (run 36342824454) e correcao

A primeira corrida em CI real (job e2e, run 36342824454, commit 4fbd6dc, apos o merge de
feature/f20-47-e2e em feature/f20-groq-e-consolidacao) falhou nos dois specs:

- 01-happy-path.spec.ts: getByRole link name Senior Python Engineer resolveu
  2 elementos (violacao de strict mode).
- 02-failure-scenarios.spec.ts (Groq 429): 1 oportunidade encontrada. nao encontrado.

Causa raiz: em CI, o job e2e roda as etapas do pipeline.yml antes da suite de
navegador, e duas delas ja criam uma oportunidade titulada exatamente
Senior Python Engineer: a etapa Verify manual acquisition through the public API
(empresa Example) e a etapa Verify the autonomous cycle without a terminal (fonte
Greenhouse board_token radar-ci, empresa Radar CI). Localmente eu tinha rodado a
suite contra uma pilha recem-criada, sem essas duas etapas antes - por isso nao vi a
colisao.

Reproduzido localmente rodando as etapas reais do pipeline (aquisicao manual, perfil,
ciclo autonomo, kill switches, restauracao do worker) contra a pilha isolada -p f20e2e47
antes de npx playwright test - confirmado: 2 oportunidades Senior Python Engineer antes
mesmo da suite abrir o navegador, reproduzindo a falha do CI byte a byte.

Correcao (sem afrouxar nenhuma assercao): fake_job_board.py passou a responder a qualquer
board com prefixo e2e- com um posto cujo titulo incorpora o proprio token
(Senior Python Engineer (e2e-token)), alem do board fixo radar-ci que os outros passos
do pipeline continuam usando sem mudanca. support/api.ts seedEnabledGreenhouseSource
agora gera um board_token unico por chamada (e2e-timestamp-random) e devolve searchTerm
ja com o titulo unico; os dois specs buscam por esse termo em vez de um texto fixo. Cada
corrida - e cada spec - passa a criar uma oportunidade com titulo garantidamente unico,
que nenhuma outra etapa do mesmo job de CI poderia ter criado.

Revalidado localmente com o repro completo da ordem do CI (aquisicao manual + ciclo
autonomo + kill switches + restauracao do worker, todos antes da suite): 7/7 verde, duas
corridas consecutivas.

## 7. Limitações conhecidas

- O board `radar-ci` continua servindo sempre o mesmo posto fixo (`Senior Python Engineer`, id 4242); o board dinamico `e2e-*` (secao 6) resolve a colisao de titulo, nao este ponto. Os
  cenários de "paginação parcial" e "304" são verificados pela forma da resposta HTTP
  (`meta.total` inflado, `304` condicional), não por um board com múltiplas páginas reais.
- "Restart do worker no meio da coleta" reinicia o container enquanto o clique de "Executar
  agora" está em voo; como a coleta desse board é praticamente instantânea, isto prova
  recuperação e ausência de duplicata através de um restart concorrente, não
  necessariamente um restart *no meio* de uma chamada HTTP de coleta em andamento.
