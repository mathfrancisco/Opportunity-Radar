# CARD F10-06 — Ação manual e gate E2E do ciclo

- **Status:** Done
- **Fase:** 10 — Ciclo autônomo
- **Depende de:** F10-01, F10-02, F10-03, F10-04, F10-05
- **Bloqueia:** Fases 11 e 12
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§11–13; milestone I

## Resultado

O detalhe da oportunidade permite avaliar agora, e um gate E2E prova o ciclo
autônomo completo em ambiente inicializado.

## Contexto

Automação cobre o percurso normal, mas operadores precisam forçar avaliação ao
depurar regras, conferir resultados ou reavaliar após corrigir dados. O Compose
não cria perfil, importa catálogo nem aceita termos: esses são pré-requisitos
explícitos do gate.

## Escopo

- Adicionar a ação **Avaliar agora** no detalhe da oportunidade e conectá-la ao
  endpoint de avaliação existente.
- Mostrar sucesso, erro e atualização de assessment sem esconder falhas.
- Fazer a ação conviver com as claims de F10-02 quando uma análise for iniciada.
- Acrescentar cenário E2E do ciclo após `docker compose up -d`, com pré-condições
  documentadas: migrations aplicadas, ProfileVersion ativa e fonte homologada,
  habilitada e agendada.
- Verificar coleta, normalização, score na Inbox, análise concluída ou degradação
  explícita, e rastreabilidade por correlation id.

## Fora de escopo

- Bootstrap automático de catálogo, termos ou perfil.
- Reavaliação por mudança de perfil (Fase 11).
- Automação de candidatura.

## Notas de implementação

A ação manual reutiliza a regra de matching de F10-01 e não cria um caminho de
score alternativo. O gate aceita indisponibilidade de Ollama somente quando ela
fica explicitamente visível; não pode mascará-la como sucesso.

## Critérios de aceite

- [x] **Avaliar agora** está disponível no detalhe e cria ou retorna assessment
      sem duplicá-lo.
- [x] O cenário E2E inicia com as três pré-condições atendidas.
- [x] Fonte habilitada e agendada executa sozinha; fonte sem schedule não.
- [x] `RawItem`, Opportunity normalizada e assessment aparecem sem terminal.
- [x] Inbox mostra a vaga com score.
- [x] Análise é anexada ou é exibida como estado degradado explícito.
- [x] Falha de fonte não interrompe os outros jobs.
- [x] Cada rodada é rastreável por correlation id.
- [x] Histórico expõe `execution_trigger` sem confundir `CollectionMode`.
- [x] Reinício do worker não duplica assessment nem análise concluída.

## Verificação

Adicionar testes de componente e API para a ação manual, e estender o cenário
Compose/E2E para o ciclo autônomo, incluindo Ollama indisponível, reinício do
worker, fonte sem schedule e falha isolada de fonte.

O gate está em `.github/workflows/pipeline.yml`, no job `e2e`, passos
"Verify the autonomous cycle without a terminal" e "Verify the kill switches
reach the worker". Ele roda depois de `docker compose up -d` e confere, sem
nenhum comando de terminal no meio: coleta agendada com `execution_trigger`
`SCHEDULED`, fonte sem schedule parada, falha isolada de fonte, normalização,
score na Inbox, análise concluída ou degradação explícita, rastreabilidade por
correlation id e ausência de duplicata após reiniciar o worker.

## Decisões de implementação

O gate coleta de um board local (`tests/e2e/fake_job_board.py`, serviço
`jobboard` no `compose.ci.yaml`), com `GREENHOUSE_BASE_URL` apontado para ele.
Provar que o worker coleta sozinho exige uma fonte que ele consiga alcançar, e
um gate que depende de terceiro não é um gate.

As pré-condições continuam explícitas e não são criadas pelo Compose: migrations
aplicadas, `ProfileVersion` ativa e fonte homologada, habilitada e agendada. O
gate as afirma antes de seguir.

A ação manual de análise agora pode responder 409 quando o job detém a claim do
F10-02. O gate e o cliente web tratam isso como "tente de novo", não como falha:
devolver a análise anterior apresentaria estado velho como resposta da chamada.

## Arquivos prováveis

- `apps/web/src/routes/OpportunityDetailPage.tsx`
- `apps/web/src/features/matching/api.ts`
- `apps/web/src/features/matching/useAssessment.ts`
- `src/opportunity_radar/presentation/http/matching.py`
- `.github/workflows/pipeline.yml`
- `compose.yaml`
- `tests/` de HTTP, web e E2E
