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

- `items_announced` é total declarado independentemente pela API, quando houver;
  total inferido da lista/páginas é reportado separadamente. Não inventar total
  oficial para provedores que não o expõem.
- `SourceRun.complete` exige sucesso, paginação esgotada comprovada, nenhum limite
  atingido, cursor sem loop e contagem de ids únicos compatível com o total.
- Persistir escopo/configuração da coleta e conjunto observado por execução,
  incluindo itens já conhecidos. `last_seen_at` nunca retrocede.
- Duas ausências completas comparáveis encerram a ocorrência, não diretamente
  a oportunidade agregada. Parcial/falha não contam; presença interrompe a ausência.
- Encerrar automaticamente a oportunidade apenas quando todas as ocorrências
  autoritativas de board estiverem encerradas e nenhuma outra tiver presença
  posterior. Sem fonte autoritativa, sinalizar desatualizada/desconhecida.
- Guardar ids das execuções e motivo; mudança de board/filtro invalida comparação.
- Reaparecimento reativa ocorrência e só desfaz fechamento automático. Preservar
  descarte/arquivamento/fechamento manual e estágio de candidatura; avisar no pipeline.
- Coletas filtradas/manual/Remotive não provam ausência. Checkpoint de retomada
  não converte trecho restante do board em nova varredura completa.
- Intervalos básicos por prioridade respeitam política da fonte; adaptação por
  rendimento e orçamento agregado do host ficam em F18-04.

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
- [ ] Duas ausências comparáveis encerram ocorrência; outra fonte ativa impede
      encerramento agregado.
- [ ] Execução parcial ou falha nunca encerra vaga.
- [ ] Reaparecimento desfaz apenas encerramento automático.
- [ ] Mudança de escopo, loop de cursor e limite atingido nunca provam ausência.
- [ ] Itens repetidos registram presença sem duplicar evidência/conteúdo.

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
