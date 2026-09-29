# CARD F20-47 — Percurso E2E no navegador com falhas injetadas

- **Status:** Feito
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** F — Encerramento
- **Depende de:** F20-17, F20-39, F20-40, F20-25
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-09](../../40-roadmap-varredura-produtiva/fase-18/f18-09-prova-do-fluxo-e-produtividade.md)

## Resultado

O ciclo perfil → preferência → coleta → busca → análise → candidatura roda no navegador do CI com falhas injetadas, sem perda nem encerramento indevido.

## Contexto

O job `e2e` do `.github/workflows/pipeline.yml` sobe `api`, `worker` e `frontend` com `compose.ci.yaml` e hoje só verifica health e modo degradado. `tests/e2e/fake_job_board.py` e `fake_groq.py` (F20-17) são os servidores falsos.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `tests/e2e/browser/` | teste Playwright do percurso |
| Alterar | `tests/e2e/fake_groq.py` | modo de falha por variável (`FAKE_GROQ_MODE=429|500|invalid|ok`) |
| Alterar | `tests/e2e/fake_job_board.py` | paginação parcial e 304 por variável |
| Alterar | `.github/workflows/pipeline.yml` | passo do navegador e upload de evidências |

## Passos

1. Escrever o percurso feliz no navegador: preencher perfil, editar preferência, disparar coleta, buscar, abrir vaga, analisar, criar candidatura.
2. Adicionar cenários: paginação parcial, 304, Groq 429, Groq 500, Groq inválido, restart do `worker` no meio da coleta.
3. Em cada cenário, verificar: nenhuma vaga duplicada, nenhuma vaga ativa marcada como encerrada, Inbox mostra a vaga sem comentário quando a IA falha.
4. Anexar screenshots e trace como artefato do CI.

## Não fazer

- Não chamar Groq nem boards reais.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [x] Percurso completo passa sem terminal. Evidência: `tests/e2e/browser/specs/01-happy-path.spec.ts`
      (perfil → preferência → coleta → busca → análise → candidatura, tudo pela UI), verde
      localmente na pilha isolada `-p f20e2e47`. Ver `docs/44-roadmap-fase-20/evidencias/e2e-falhas-injetadas-2026-09-27.md`.
- [x] Todos os cenários de falha passam. Evidência: `tests/e2e/browser/specs/02-failure-scenarios.spec.ts`
      (Groq 429/500/inválido, paginação parcial, 304, restart do worker no meio da coleta),
      6/6 verdes na mesma pilha. O prefixo numérico dos dois arquivos (`01-`/`02-`) não é
      cosmético: o breaker de circuito da IA é estado por processo, não por teste, e o
      percurso feliz precisa da sua análise real antes de qualquer cenário abrir o breaker
      — ver §1 da evidência.
- [x] Evidências anexadas no CI. Passo "Upload the browser journey's screenshots and traces"
      em `pipeline.yml` (`actions/upload-artifact`, `screenshot: 'on'` e `trace: 'retain-on-failure'`
      em `playwright.config.ts`); confirmação de que o job `e2e` publica o artefato ainda depende
      do push do coordenador.

## Testes

- Os próprios testes de navegador: `tests/e2e/browser/specs/01-happy-path.spec.ts`,
  `tests/e2e/browser/specs/02-failure-scenarios.spec.ts`.

## Pronto quando

Job `e2e` verde no CI com os cenários e artefatos. Local: verde na pilha isolada `-p f20e2e47`
(ver evidência); a confirmação do CI real chega depois do push do coordenador.

## Nota fora da lista "Arquivos"

- `.gitignore`: duas linhas para `tests/e2e/browser/test-results/` e `tests/e2e/browser/report/`
  (saída do Playwright, não um artefato do build). Sem isso o `git status` do novo projeto
  Node ficaria sujo depois de qualquer corrida local.

## Follow-up (correção de CI, run 36342824454)

A primeira corrida real em CI (após o merge em `feature/f20-groq-e-consolidacao`, commit
4fbd6dc) quebrou em dois pontos: um `getByRole('link', ...)` resolveu 2 elementos e uma
asserção de "1 oportunidade encontrada." falhou. Causa: `pipeline.yml` já cria, em passos
anteriores do mesmo job, duas outras oportunidades tituladas "Senior Python Engineer"
(aquisição manual e o ciclo autônomo com o board fixo `radar-ci`) antes da suite de
navegador rodar — colisão de título, não um bug de UI. Corrigido tornando o board de cada
`seedEnabledGreenhouseSource` único por chamada (`e2e-<token>`, título embutido), então o
termo de busca de cada teste é garantidamente único. Reproduzido localmente rodando as
etapas reais do pipeline antes da suite (repro de 2 oportunidades "Senior Python Engineer"
confirmado) e revalidado 7/7 verde duas vezes depois da correção. Ver §6 da evidência.