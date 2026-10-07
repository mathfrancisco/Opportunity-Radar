# F51-10 — fila IA justa, retry, defer e progresso

- **Status:** Planejado
- **Prioridade:** P1
- **Esforço estimado:** M
- **Risco:** alto para justiça da fila e custo externo; retry precisa respeitar quota global e não pode duplicar chamadas sob concorrência.
- **Dependências:** F51-09 (telemetria IA completa).

## Problema e evidência

`candidates_needing_suggestion` em `opportunities/suggestions.py` busca `limit * 5` por `created_at` e depois filtra em Python registros com sugestões da versão atual. Assim, uma página de 100 itens antigos já resolvidos pode ocupar a janela antes de três candidatos novos; o risco de starvation é estrutural, mas repetição/impacto ainda não foi medido. `suggest_fields` absorve `ProviderError` e pode devolver outcome vazio; worker precisa distinguir falha de lote de sucesso vazio. Esta fila é consultiva: falha não atualiza oportunidade canônica.

## Objetivo e limites

Selecionar candidatos pendentes com ordem justa e estável, persistir defer/retry por conteúdo e tornar progresso/falhas observáveis. Não contornar breaker, cooldown ou quota global, não prometer segunda tentativa depois de quota global esgotada e não converter sugestões em alterações canônicas sem aprovação humana. Evitar chamada duplicada por worker concorrente com claim/lease atômico se o modo de execução admitir concorrência; hoje o agendador usa `max_instances=1`, mas isso não cobre outro processo.

## Arquivos existentes

- [`suggestions.py`](../../../src/opportunity_radar/opportunities/suggestions.py): `candidates_needing_suggestion`, `suggest_fields`, `SuggestionOutcome` e sugestão por versão/campo.
- [`worker.py`](../../../src/opportunity_radar/worker.py): `suggest_fields_pending` e configuração do agendamento.
- [`breaker.py`](../../../src/opportunity_radar/platform/ai/breaker.py), [`quota.py`](../../../src/opportunity_radar/platform/ai/quota.py) e [`router.py`](../../../src/opportunity_radar/platform/ai/router.py): circuit breaker, reserva/consumo e chamadas provider.
- [`test_suggestions.py`](../../../tests/backend/opportunities/test_suggestions.py): elegibilidade, chamada e persistência atuais.

## Tarefas executáveis

1. Medir baseline sem provider: criar 100 oportunidades antigas cujos campos desconhecidos já têm sugestão para a versão vigente e 3 candidatas novas. Registrar quantas janelas até as novas serem selecionadas.
2. Substituir over-fetch-before-filter por query elegível no SQL, preferindo `NOT EXISTS` por oportunidade/versão/campo pendente. Ordenar por `(created_at, id)` e paginação keyset com cursor composto, para desempatar datas iguais e evitar saltos/repetições. Se schema/modelos atuais não permitirem filtro correto, documentar extensão mínima antes de criar migration.
3. Persistir defer/retry com `content_version` ou hash estável do conteúdo submetido, `next_attempt_at`, tentativas, razão categorizada e versão do prompt. Mudança de conteúdo cria elegibilidade nova; conteúdo igual respeita cooldown.
4. Classificar `ProviderError`: quota global/breaker aberto => batch defer sem chamada adicional e `next_attempt_at` vindo da disponibilidade real; timeout/transiente => retry após cooldown; schema/saída inválida => falha específica com evidência e sem alterar oportunidade. Não executar fallback que ignore o breaker/quota. Se quota compartilhada ficou esgotada, terminar lote e registrar restantes como deferred, sem outra chamada.
5. Tornar resultado do lote explícito: selecionados, chamados, cache/defer, sucesso, falha por categoria e restantes; evitar chamar lote “bem-sucedido” se todos os selecionados falharam.
6. Caso múltiplos workers possam processar a mesma linha, adquirir claim com dono/expiração antes do HTTP; claim falha significa skip, sem chamada. Expiração só recupera linha sem tentativa ativa confirmada.

## Critérios de aceite

| ID | Critério mensurável | Given / When / Then | Teste proposto e evidência |
| --- | --- | --- | --- |
| AC01 | Candidatas novas não ficam atrás das 100 antigas resolvidas. | Dadas 100 linhas antigas com todos os campos já sugeridos e 3 novas elegíveis, quando limit=3, então query retorna as 3 novas sem sobrebuscar as antigas. | `test_suggestion_sql_queue_skips_resolved_before_limit` (proposto em `tests/backend/opportunities/test_suggestions.py`); SQL/resultados e contagem de candidatos. |
| AC02 | Paginação é estável para timestamps iguais e não repete itens. | Dadas candidatas com `created_at` igual e UUIDs distintos, quando duas páginas seguem cursor `(created_at,id)`, então cada item aparece uma vez e ordem é determinística. | `test_suggestion_keyset_cursor_is_stable` (proposto); IDs e cursor antes/depois. |
| AC03 | Erro em item não interrompe o restante antes do esgotamento global. | Dado primeiro item com falha de schema e segundo elegível com quota disponível, quando lote roda, então primeiro recebe falha classificada e segundo é processado; resumo conta ambos corretamente. | `test_suggestion_schema_failure_does_not_hide_next_candidate` (proposto); duas respostas fake e resumo do lote. |
| AC04 | Quota global esgotada não dispara uma segunda chamada. | Dado provider sinalizando quota diária esgotada no primeiro item, quando existem mais candidatos, então nenhum outro HTTP ocorre, todos recebem defer coerente e próxima execução é posterior à disponibilidade. | `test_global_quota_exhaustion_defers_rest_of_batch` (proposto); exatamente 1 request fake, fila persistida e `next_attempt_at`. |
| AC05 | Conteúdo alterado permite nova avaliação; conteúdo igual respeita defer. | Dado defer para hash H até t+1h, quando H roda antes do vencimento, então zero HTTP; conteúdo hash H2 pode ser selecionado separadamente. | `test_suggestion_defer_is_scoped_to_content_version` (proposto); estados por hash e requests. |
| AC06 | Concorrência não duplica request do mesmo item. | Dado dois workers concorrendo pela mesma candidata, quando ambos tentam claim, então apenas o dono recebe claim e inicia HTTP. | `test_suggestion_claim_prevents_duplicate_provider_call` (proposto, se paralelismo multi-processo for suportado); uma chamada e um claim ativo. |

## Falhas, rollout e reversão

Falha de provider, quota, schema, lease e configuração aparecem em categorias distintas; nenhuma é sucesso vazio. Primeiro publicar métricas em shadow, depois aplicar seleção SQL sem alterar o provedor nem a regra de sugestão. Rollback pode voltar à consulta anterior mantendo defer e registros; se a consulta antiga reintroduzir starvation, suspender batch ao invés de elevar chamadas. Testes mutáveis ficam em `_test`, com provider falso. Entregáveis: baseline reproduzível, query/cursor, contrato de defer, claim se necessário, resumo da fila e testes. O risco estrutural está observado; incidência de starvation ainda não está medida.

## Conferência dos critérios contra os testes (2026-10-07, sexta sessão)

Conferido critério por critério, lendo o corpo de cada teste. Caminhos relativos a
`tests/backend/`. "banco" é teste de integração com PostgreSQL real
(`RUN_DATABASE_INTEGRATION=1`); "unidade" usa dublês. Os marcados com PR #70 foram
escritos nesta sessão, sem mudança em `src`.

| AC | Teste | Tipo | Observação |
| --- | --- | --- | --- |
| AC01 | `opportunities/test_suggestions.py::test_suggestion_queue_filters_before_limit_and_pages_stably` | banco | Confere o resultado, não o SQL |
| AC02 | o mesmo teste do AC01 | banco |  |
| AC03 | `opportunities/test_suggestions.py::test_a_failed_suggestion_does_not_hide_the_next_candidate` | banco | A falha do teste é corpo que não é JSON, não schema |
| AC04 | `opportunities/test_suggestions.py::test_quota_exhaustion_persists_one_coherent_defer_and_a_rerun_waits_for_availability` (PR #70); `::test_global_quota_exhaustion_defers_rest_of_batch` | banco | **Diferença do card:** só o candidato que encontrou o saldo esgotado ganha linha de adiamento; os seguintes ficam como não tentados, sem linha. O card diz que todos recebem adiamento |
| AC05 | `opportunities/test_suggestions.py::test_a_defer_is_scoped_to_its_content_hash_and_changed_content_is_selectable` (PR #70) | banco |  |
| AC06 | `opportunities/test_suggestions.py::test_suggestion_claim_prevents_duplicate_provider_call` | banco | Duas sessões no mesmo processo |

Os nomes propostos no card (`test_suggestion_sql_queue_skips_resolved_before_limit`, `test_suggestion_keyset_cursor_is_stable`, `test_suggestion_schema_failure_does_not_hide_next_candidate`, `test_suggestion_defer_is_scoped_to_content_version`) não existem; os testes reais são os da tabela. Todos os critérios têm teste. **Decisão pendente do dono no AC04:** aceitar o comportamento (um adiamento, o resto não tentado) ou pedir adiamento para todos. O fechamento depende disso e da janela do F51-18.
