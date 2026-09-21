# CARD F10-06 — Ação manual e gate E2E do ciclo

- **Status:** In progress
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

- [ ] **Avaliar agora** está disponível no detalhe e cria ou retorna assessment
      sem duplicá-lo.
- [ ] O cenário E2E inicia com as três pré-condições atendidas.
- [ ] Fonte habilitada e agendada executa sozinha; fonte sem schedule não.
- [ ] `RawItem`, Opportunity normalizada e assessment aparecem sem terminal.
- [ ] Inbox mostra a vaga com score.
- [ ] Análise é anexada ou é exibida como estado degradado explícito.
- [ ] Falha de fonte não interrompe os outros jobs.
- [ ] Cada rodada é rastreável por correlation id.
- [ ] Histórico expõe `execution_trigger` sem confundir `CollectionMode`.
- [ ] Reinício do worker não duplica assessment nem análise concluída.

## Verificação

Adicionar testes de componente e API para a ação manual, e estender o cenário
Compose/E2E para o ciclo autônomo, incluindo Ollama indisponível, reinício do
worker, fonte sem schedule e falha isolada de fonte.

## Arquivos prováveis

- `apps/web/src/routes/OpportunityDetailPage.tsx`
- `apps/web/src/features/matching/api.ts`
- `apps/web/src/features/matching/useAssessment.ts`
- `src/opportunity_radar/presentation/http/matching.py`
- `.github/workflows/pipeline.yml`
- `compose.yaml`
- `tests/` de HTTP, web e E2E
