# Checkpoint de implementação — 5 de outubro de 2026

> Atualização de 2026-10-06 (terceira sessão, PRs #48 e #49): o dono aprovou as duas
> propostas de rótulo em bloco. O PR #48 faz os leitores de gold lerem a sugestão de um caso
> assinado sem rótulo próprio (decisão do agente, registrada no F51-11); suíte completa num
> banco novo `_test`: `1921 passed, 17 skipped`, `ruff` e `mypy` sem erros. O PR #49 grava
> `revisado_por` em 300 e 1.104 entradas, sem mudar valor. Com o gold confirmado: precisão do
> título de 95,3% (F52-01 e F52-02 concluídos) e portão do F51-11 sem nenhuma regra aprovada,
> por falta de emissões (0 a 8 por regra, mínimo 20). `GATED_RULES` não mudou; F52-03 e
> F52-07 seguem bloqueados. A medição de uso de IA está no card F51-12. Nenhum outro card da
> SPEC 51 foi tocado e a janela de sete dias continua fechada. O projeto Docker `or-f5111a`
> foi removido.

> Atualização de 2026-10-06 (segunda sessão, PRs #44 a #46): na SPEC 51 só o F51-04 avançou.
> O PR #45 traz o teste do AC02: dois workers, cada um com a própria sessão, disputam a
> última unidade do orçamento de um host; exatamente um reserva e o consumo persistido fica
> igual ao teto. `reserve_host_request` já era um UPSERT condicional e passou sem mudança. A
> suíte completa rodou num banco novo `_test`: `1914 passed, 17 skipped`. Os outros critérios
> do F51-04 não foram conferidos contra os testes existentes. F51-05 a F51-10, F51-12, F51-13
> e F51-17 não foram tocados; a janela de sete dias continua fechada e as propostas de rótulo
> continuam sem `revisado_por`. Os PRs #44 (`skills-v5`) e #46 (`matching-v5`) são da SPEC 52.

> Atualização de 2026-10-06 (sessão das SPECs 51 e 52, PRs #40 a #42): na SPEC 51 só o
> F51-11 avançou. O PR #41 trouxe a amostra de 368 vagas, a proposta de rótulos do modelo
> (não é rótulo) e o leitor do gold que só conta casos com `revisado_por`; o comando do portão
> roda e bloqueia com `gold_jobs: 0`. O desvio dos dois revisores e os adiamentos de F51-14 a
> F51-16 estão na SPEC 51 §8.1 e no README do roadmap. Nenhum outro card foi tocado: o estado
> de partida descrito abaixo e no README ("Estado por card") continua valendo, e a janela de
> sete dias não foi aberta. O projeto Docker `or-f50-suite-1005` foi removido; `orf51terra`
> não foi, porque o banco dele se chama `opportunity_radar` e não termina em `_test`.

> Atualização de 2026-10-06 (integração no PR #37): a branch recebeu `main` (PRs #32 e #33) e
> os PRs #34, #35 e #36. Pela primeira vez rodaram os checks globais, num projeto Compose
> descartável com banco `_test`: `ruff check .` e `mypy` sem erros; migrações `0065` a `0067`
> em `upgrade head`, `downgrade base`, `upgrade head`; suíte completa com integração,
> `1843 passed, 10 skipped`. Para chegar a isso foram corrigidos: o `downgrade` da `0066`
> (precedência de `||` sobre `->>`, que falhava em qualquer banco); a sonda de orçamento do
> worker em `analyze_pending`, que tinha sido removida e fazia um teto esgotado gravar
> `AI_FAILED` (contratos F20-24 e F48-02); o manifesto de backup, sem as tabelas
> `ai_operation_record` e `ai_suggestion_defer`; a tentativa em andamento num modelo da Token
> Harbor, gravada como `groq`; e testes que ainda esperavam a chave antiga de orçamento do
> Workday ou tinham dados de preparação errados. Nenhum card foi continuado. O estado por
> card continua o descrito abaixo: nenhum concluído.

> Atualização Terra: três tentativas Luna parciais falharam por capacidade e o usuário
> autorizou fallback Terra. Esta fatia corrigiu o retorno de `measure()` e registrou F51-17
> warm (10 repetições/query, bruto, p50/p95); cold fica N/D sem cinco resets reais de cache
> em ambiente isolado. 48 testes focados passaram; Ruff/mypy globais, suite completa e DB
> isolado não foram executados. Gold humano, aprovações reais e sete dias de runtime faltam.

## Estado

Branch: `feat/f51-coleta-confiavel`. A fatia inicial adiciona baseline somente
leitura, métricas de qualidade por fonte e benchmark FTS com manifesto congelado.
Arquivos de roadmap staged e alterações concorrentes foram preservados. Nenhum
card está concluído e nenhuma alteração foi commitada.

O benchmark exige dois julgamentos humanos concordantes por par consulta/coorte;
gold incompleto não produz métrica. Também valida elegibilidade, revisores, IDs,
duplicatas e corpus. Seu hash de consulta inclui filtros, versão e hash do código
de consulta. Os relatórios guardam versão do coletor e snapshot PostgreSQL.

O baseline conta `DISTINCT opportunity_id` por fonte via ocorrências. Esses totais
se sobrepõem quando uma oportunidade tem mais de uma fonte e não podem ser somados.
O `query_hash` inclui versão, filtros e hash da implementação Python do coletor e
regras de classificação. É um hash de implementação, não do SQL compilado literal.
O CLI inicia `REPEATABLE READ, READ ONLY` antes das consultas e obtém
`txid_current_snapshot()` na mesma transação; a consistência está garantida pelo
isolamento PostgreSQL configurado, mas não foi verificada numa execução de banco
nesta rodada.

## Evidência

O coordenador reportou F51-06: `72 passed` em
`tests/backend/acquisition/test_service.py` e `tests/backend/test_worker.py`, e
suíte IA: `49 passed, 17 skipped`. F51-06 AC03 (disputa de duas execuções) e AC04
(integração DB) seguem pendentes segundo a revisão Terra; esses testes não fecham
tais critérios.

## Lacunas e dependências

- F51-01 ainda não tem três execuções completas nem contagem operacional de
  descrições úteis.
- F51-02 calcula frescor, recall humano e degradação de orçamento por host no
  relatório CLI. Recall segue sem amostra humana; a janela operacional de sete dias
  ainda não foi observada.
- O CLI reutiliza `_budget_host_for_source` e `HostBudgetState` para ler o estado
  de host sem executar serviço ou alterar cooldown. Cooldown/orçamento esgotado
  degradam fontes habilitadas e as mantêm no denominador. Fontes desabilitadas saem
  do denominador ativo, mas o esquema não identifica se a desativação é permanente;
  essa razão permanece não classificada.
- F51-03 aguarda aprovação humana de fontes/termos, resposta real e evidência de
  elegibilidade. F51-17 aguarda gold independente e revisores humanos reais.
- F51-04, F51-07, F51-08 e F51-11 a F51-13 seguem pendentes. F51-14 a F51-16 são
  condicionais e permanecem adiados até evidência de necessidade e fonte aprovada.
- A suíte integral isolada e validação em banco não foram executadas nesta rodada;
  não houve escrita nem integração com banco operacional.

## F51-11 e F51-18 — validação offline

O leitor de gold preserva compatibilidade com o formato F50 legado e mostra estados
`applicable` / `inapplicable` / `unknown`; desconhecidos e inaplicáveis ficam fora da
precisão, emissões excluídas são contadas à parte e FN sem atribuição humana fica em
`<field>:no_emission`. Rótulos legados continuam reportáveis e bloqueiam o gate. O
gold F50-01 existente tem 39 casos sem `source_type`/julgamento explícito; nenhum
rótulo humano foi criado, e F11 continua no-go. `GATED_RULES` e flags seguem inalterados.

O validador F18 exige janela de pelo menos sete dias completos, sem datas futuras, coorte/hash
e versões congelados, SHA e digest CI/runtime compatíveis, três runs `SUCCEEDED` completos
distintos por fonte dentro da janela (backfill excluído),
descrição útil e recall ≥95%, frescor ≤7 dias, IA terminal 100%, restore/rollback declarado
em `_test` e aprovação assinada declarada. N/D/denominador zero bloqueia. Ele é offline,
não autentica assinaturas ou observações e não executa restore, rollback ou operação; não há
pacote preenchido nem decisão real nesta rodada. F14-F16 ficam adiados sem bloquear o núcleo.

F51-02 agora inclui a última tentativa por fonte (`id`, `status`, `complete`, itens vistos/
persistidos, inválidos e `error_code`) sem confundi-la com o último inventário completo; campos
ausentes permanecem nulos. A contagem ativa usa fontes habilitadas, não há classificação
persistida de desativação permanente e isso não prova aprovação humana para listar a fonte.

Nesta fatia: `31 passed`; Ruff `All checks passed!`; mypy `Success: no issues found in 4 source files`.
Os casos usam fixtures e não validam integração com banco, operação, assinatura humana,
restore ou rollback real. Reclassificação seletiva ainda não emite evento
persistido explícito contendo regra/versão/motivo em formato próprio; essa prova permanece
pendente para teste isolado.

F51-17 segue aberto: o cálculo auxiliar p50/p95 não implementa os grupos cold ≥5 / warm ≥10,
relatório A/B pareado nem evidencia latências operacionais. Nenhum cache de banco foi limpo e
nenhum resultado de performance foi fabricado.
