# CARD F17-07 — Coleta completa, alerta de paginação e vaga encerrada

- **Status:** Backlog
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** Nenhum
- **Bloqueia:** Milestone P
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §8

## Resultado

Cada execução sabe se leu o board inteiro, alerta quando não leu, e a vaga que sumiu do
board é marcada como encerrada com a execução que a viu por último como evidência.

## Contexto

Hoje o radar não compara o que o board anuncia com o que foi lido, então paginação
quebrada passa despercebida. E uma vaga que a empresa tirou do ar continua aberta na
Inbox para sempre, poluindo a precisão com vagas mortas.

## Escopo

- **`items_announced`** em `SourceRun`, quando a API informa o total: Greenhouse
  (`meta.total`), Lever (contagem das páginas), Ashby (tamanho da lista `jobs`). Sem total
  informado, `null`.
- **Execução completa:** `SUCCEEDED`, sem `max_items`, sem erro de paginação e com
  `items_seen ≥ items_announced` quando houver total. Marcada em `SourceRun.complete`.
- **Alerta de paginação:** execução com `items_seen < items_announced` gera incidente no
  canal de alertas existente (`SourceAlertService`), com os dois números.
- **Última vez vista:** `SourceOccurrence.last_seen_run_id` e `last_seen_at` atualizados a
  cada execução completa que vê a vaga.
- **Encerramento:** vaga cuja ocorrência não aparece em **duas execuções completas
  seguidas** da mesma fonte passa a `CLOSED`, com evidência (ids das duas execuções).
  Execução parcial ou falha nunca encerra.
- **Reabertura:** vaga encerrada que reaparece volta ao estado anterior, com evidência.
- **Frequência por prioridade:** o agendamento padrão de fonte de empresa de prioridade
  alta é mais curto que o de prioridade baixa, sempre dentro do intervalo mínimo da
  política de rede.

## Fora de escopo

- Detectar encerramento em fontes sem board completo (Remotive, manual).
- Notificar o operador de vagas encerradas.

## Notas de implementação

- O encerramento respeita as transições de ciclo de vida existentes
  (`opportunities/domain.py`); vaga com candidatura ativa não é encerrada em silêncio —
  a candidatura ganha um aviso no pipeline.
- A marca `complete` é o que impede que uma falha de rede encerre metade do board.

## Critérios de aceite

- [ ] Cada execução registra anunciados × lidos quando a API informa.
- [ ] Paginação incompleta gera alerta com os números.
- [ ] Vaga ausente em duas execuções completas seguidas vira `CLOSED`, com evidência.
- [ ] Execução parcial ou falha nunca encerra vaga.
- [ ] Vaga que reaparece é reaberta.

## Verificação

- **CI:** testes dos coletores com fixtures paginadas e totais; teste de integração do
  encerramento (duas completas, uma parcial no meio, reaparecimento); E2E com o board
  falso servindo menos vagas numa segunda coleta.

## Arquivos prováveis

- `src/opportunity_radar/acquisition/greenhouse.py`, `lever.py`, `ashby.py`,
  `service.py`, `models.py`, `alerts.py`
- `src/opportunity_radar/opportunities/service.py`, `models.py`
- `migrations/versions/*_run_completeness_and_last_seen.py`
- `tests/e2e/fake_job_board.py`
