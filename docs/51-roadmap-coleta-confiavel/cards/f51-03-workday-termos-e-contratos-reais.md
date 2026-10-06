# F51-03 — Workday: termos e contrato real por fonte

- **Status:** Planejado
- **Prioridade:** P0
- **Esforço estimado:** P
- **Risco:** alto para conformidade e integridade de conteúdo; limitar a uma fonte piloto, com decisão humana e detalhe opt-in.
- **Dependências:** F51-01; continuidade F50-03.

## Problema, fatos e hipótese

**Fatos observados:** no snapshot operacional de 2026-10-05 17:51 UTC havia 18 fontes Workday habilitadas, nenhuma com `fetch_detail=true`; uma consulta posterior encontrou 19 fontes, ainda sem detalhe ativo. A fixture de detalhe existente é sintética e a revisão de termos permanece pendente. Workday continua participando da coleta de listagem; este card trata apenas da chamada adicional de detalhe.

**Hipótese:** para uma fonte cuja política e termos sejam aprovados por uma pessoa responsável, a resposta pública real poderá fornecer uma descrição útil sem mudar identidade, presença ou estado da vaga. Isso ainda precisa ser comprovado; os números de ocorrências sem descrição motivam a investigação, não autorizam expansão.

## Objetivo e limites

Registrar decisão permitida/adiada/recusada por fonte e validar termos e contrato real mínimo, com amostra pública sanitizada e reproduzível quando autorizada. Não aprovar termos automaticamente, ativar fontes neste card, contornar autenticação/robots, elevar orçamento, nem usar resposta de detalhe como prova de inventário completo. Ativação operacional e piloto de três runs pertencem ao F51-05, após os controles do F51-04. Ausência, erro ou descrição curta não deve virar conteúdo inventado.

## Arquivos e referências existentes

- [`workday.py`](../../../src/opportunity_radar/acquisition/workday.py): coleta de listagem e caminho de `_with_detail`.
- [`domain.py`](../../../src/opportunity_radar/acquisition/domain.py): `CollectionRequest` e flag de detalhe.
- [`service.py`](../../../src/opportunity_radar/acquisition/service.py): construção da requisição por fonte.
- [`test_workday_collector.py`](../../../tests/backend/acquisition/test_workday_collector.py) e [`test_service.py`](../../../tests/backend/acquisition/test_service.py).
- Fixtures existentes `tests/fixtures/workday_jobs.json` e `tests/fixtures/workday_job_detail.json`; validar proveniência antes de tratá-las como amostra real.

## Execução

1. Escolher uma fonte e registrar owner, hostname, URL pública, data da revisão, termos/limites consultados e decisão humana assinada ou identificada. Sem decisão afirmativa, nenhum request de detalhe.
2. Com autorização explícita, coletar uma resposta pública mínima sem credenciais, sanitizar identificadores pessoais ou segredos e registrar URL/modelo de resposta e timestamp. Não versionar cookies, headers sensíveis ou dados privados.
3. Comparar resposta com o contrato usado por `_with_detail`: chave/URL da vaga, correspondência com o item de listagem, título/localidade e corpo da descrição. Persistir fixture redigida com proveniência verificável; se a resposta não puder ser compartilhada, documentar campos observáveis e manter fixture sintética identificada como tal.
4. Testar sucesso, campo ausente, URL incompatível, status 403/429, timeout e JSON/schema inesperado. Em todos os erros, preservar o resultado de listagem e registrar motivo; não tratar falha de detalhe como ausência de vaga.
5. Manter `fetch_detail=false` para todas as fontes durante este card. Entregar decisão e evidência para F51-05; somente ali, depois de F51-04, avaliar ativação piloto com autorização própria.

## Critérios de aceite

| ID | Critério | Given / When / Then | Teste proposto e artefato esperado |
| --- | --- | --- | --- |
| AC01 | Termos têm decisão humana rastreável por fonte. | Dada fonte sem decisão aprovada, quando o piloto prepara a chamada, então nenhuma chamada de detalhe ocorre e a decisão fica “adiada”. | `test_workday_detail_requires_explicit_source_approval` (proposto); registro com fonte, owner, data e decisão. |
| AC02 | Contrato é conferido contra resposta pública real sanitizada. | Dada resposta aprovada, quando fixture é criada, então identidade/URL/título e corpo são comparados ao item da lista e cada campo ausente é declarado. | `test_real_workday_detail_fixture_matches_list_identity` (proposto); fixture redigida e matriz campo-origem. |
| AC03 | Flag desligada preserva comportamento de listagem. | Dada fonte com detalhe off, quando coleta roda, então não há request adicional e itens/listagem mantêm identidade. | `test_workday_detail_off_does_not_issue_request` (proposto); contador HTTP do fake e itens resultantes. |
| AC04 | Erro de detalhe não apaga vaga listada. | Dado item listado e detalhe com 429, quando a execução termina, então item continua presente, run não ganha completude por detalhe e motivo é registrado. | `test_workday_detail_429_preserves_listing` (proposto); resultado e telemetria por fonte/run. |
| AC05 | Validação de amostra não ativa coleta operacional. | Dada amostra/fixture válida e termos revisados, quando este card termina, então nenhuma fonte tem `fetch_detail` habilitado; ativação fica pendente de F51-04 e da decisão operacional do F51-05. | `test_workday_detail_contract_validation_does_not_enable_source` (proposto); configuração permanece inalterada e decisão entregue ao próximo card. |

## Falhas, rollout e rollback

403, 429, timeout, schema divergente ou dúvida sobre termos encerram a validação da amostra; coleta de listagem conserva seu resultado independente. Testes usam HTTP falso e fixture, sem rede externa; qualquer integração mutável usa banco `_test`. Este card não tem rollout de ativação: mantém `fetch_detail=false`. Entregáveis: decisão de termos, amostra/fixture redigida com proveniência, matriz de contrato e evidência entregue a F51-05. Não houve teste de implementação neste trabalho documental.
