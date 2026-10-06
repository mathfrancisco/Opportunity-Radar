# F51-05 — piloto Workday e backfill idempotente

- **Status:** Planejado
- **Prioridade:** P1
- **Esforço estimado:** M
- **Risco:** alto para sobrescrita de conteúdo e recuperação de dados; limitar fonte, lote e campos de escrita.
- **Dependências:** F51-02; F51-03; F51-04.

## Problema e evidência

No snapshot de 2026-10-05 17:51 UTC, 12.339 ocorrências Workday estavam sem descrição; isso mede ocorrências, não vagas únicas. Ainda não há piloto de detalhe real validado. Três runs completos foram indicados como evidência necessária para avaliar cobertura em catálogo; essa exigência não torna um lote de enriquecimento prova de inventário nem autoriza fechar ausências.

## Objetivo e exclusões

Após aprovação independente de F51-03 e controles de F51-04, executar um piloto limitado e, se houver decisão explícita, preencher backlog elegível por chave estável. Excluir processamento em massa, ativação automática, atualização de texto humano, substituição do raw original, duplicação de ocorrências e fechamento por run parcial. Ferramenta de dry-run/backfill não existe comprovadamente; deve ser proposta e revisada como artefato novo antes de uso.

## Arquivos e contratos existentes

- [`workday.py`](../../../src/opportunity_radar/acquisition/workday.py) e [`service.py`](../../../src/opportunity_radar/acquisition/service.py): coleta e conversão de detalhe.
- [`domain.py`](../../../src/opportunity_radar/acquisition/domain.py): contratos de ocorrência e run.
- [`repository.py`](../../../src/opportunity_radar/acquisition/repository.py): persistência; confirmar propriedade de cada campo antes de escrever.
- [`opportunities/service.py`](../../../src/opportunity_radar/opportunities/service.py): atualização de conteúdo e presença.
- [`test_delta_presence_resume.py`](../../../tests/backend/acquisition/test_delta_presence_resume.py): padrões existentes de idempotência/presença; backfill específico será coberto por teste proposto isolado.

## Procedimento operacional proposto

1. Definir `source_id` allowlist, hostname, limite de requests, duração, janela, responsável, parser version e critérios de parada. Capturar baseline por ocorrência e por oportunidade, reportando unidades distintas e texto atual; verificar que detalhe está autorizado.
2. Executar dry-run read-only que enumera alvos pela chave estável da ocorrência (fonte + external id/identidade já existente), apontando motivo de elegibilidade e conflitos. Alvo é descrição ausente ou explicitamente marcada como derivada desatualizada; comprimento acima de 200 caracteres, sozinho, não declara texto útil.
3. Antes de qualquer mutação, criar backup restaurável dos registros alvo, valores canônicos atuais, raw payload imutável, vínculos e versão. Fazer ensaio de restore em banco isolado e comprovar reconciliação; não usar DB operacional para testes.
4. Criar manifesto por execução com run id, source id, filtros, limites, cursor/chave inicial-final, versão do parser, hashes, totais previstos/aplicados/ignorados/conflitantes e backup associado. Gravar resultado derivado sem substituir o payload bruto original.
5. Aplicar em lotes pequenos apenas em campo de propriedade do coletor e somente se continuar vazio ou igual ao valor derivado anterior que aquele processo possui. Se conteúdo foi preenchido/editado por pessoa após dry-run, marcar conflito e pular. Reexecução retoma cursor e não duplica ocorrência.
6. Interromper no cooldown/429, limite, timeout, erro de identidade ou taxa de conflito acima do limite aprovado. Backfill não atualiza presença nem estado de vaga; apenas um inventário completo separado pode sustentar fechamento.

## Critérios de aceite

| ID | Critério | Given / When / Then | Teste proposto e artefato esperado |
| --- | --- | --- | --- |
| AC01 | Dry-run não altera DB e explica cada alvo. | Dada fonte e filtros fixos, quando dry-run é executado, então em `_test` os dados antes/depois são idênticos e cada ocorrência recebe motivo incluído/excluído. | `test_workday_backfill_dry_run_is_read_only_and_explains_targets` (proposto); manifesto preview e auditoria sem DML. |
| AC02 | Reexecução é idempotente e retoma cursor. | Dado lote interrompido após chave K, quando o mesmo manifesto é retomado e repetido, então cada chave tem no máximo uma escrita do mesmo parser version e nenhuma ocorrência duplicada. | `test_workday_backfill_resume_is_idempotent` (proposto); contagem e hashes por chave na fixture isolada. |
| AC03 | Texto humano e raw original sobrevivem ao enriquecimento. | Dado campo canônico não vazio/editado depois do backup, quando aplicação roda, então marca conflito e preserva bytes/valor; raw payload original permanece igual para todos os alvos. | `test_workday_backfill_preserves_human_text_and_raw_payload` (proposto); comparação em `_test`. |
| AC04 | Restore foi verificado antes da primeira escrita. | Dado backup do conjunto elegível, quando restore é ensaiado em banco isolado, então campos, vínculos e raw payload correspondem ao snapshot restaurado. | `test_workday_backfill_backup_restore_round_trip` (proposto); relatório de reconciliação assinado pelo operador. |
| AC05 | Backfill não altera timestamps, presença nem estado positivo/negativo; inventário parcial não fecha ausências. | Dada uma execução de backfill e, separadamente, um inventário parcial, quando cada operação termina, então backfill não muda qualquer estado de presença; inventário parcial preserva presenças positivas observadas e não fecha vagas ausentes. | `test_partial_workday_backfill_never_closes_absences` (proposto); diff de estado por operação/run em fixture. |
| AC06 | Expansão exige três inventários completos por fonte e meta de conteúdo útil na coorte fixa. | Dada coorte elegível e versão de regra congeladas, quando três inventários completos distintos da fonte piloto forem medidos, então relatório mostra taxa de descrição útil >=95%, denominador, N/D, skips e conflitos; backfill não conta como inventário. Se meta falhar, expansão fica bloqueada ou aberta com exceção explícita; não se troca denominador. | `test_workday_expansion_requires_three_complete_runs_and_fixed_cohort` (proposto); manifesto por fonte/coorte/versão e decisão go/no-go. |

## Rollout, rollback e entregáveis

Primeiro executar dry-run e backup/restore em `_test`; depois piloto de uma fonte e lote curto autorizado, com pausa e revisão humana entre preview e apply. Não habilitar backfill contínuo por padrão. Expansão requer AC06; limitação técnica da fonte só admite exceção documentada, com denominador original e estado ainda aberto até decisão. Rollback seleciona manifesto e parser/run version e restaura apenas campos cujo valor ainda coincide com o que aquela execução escreveu; alterações posteriores são conflitos, nunca apagadas. Proibido delete geral ou restauração cega de todas as ocorrências. Entregáveis: plano aprovado, ferramenta proposta, manifesto, backup verificável, evidência do piloto, comparação de qualidade e decisão de expandir/parar. Nenhuma mutação ou teste de aplicação foi feito nesta tarefa documental.
