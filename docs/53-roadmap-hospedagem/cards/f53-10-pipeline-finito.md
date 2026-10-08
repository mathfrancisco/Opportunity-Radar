# F53-10 — pipeline finito

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-05, F53-06.

## Objetivo

Executar coleta, normalização e estágios permitidos em uma janela finita, com
claim, deadline e parada graciosa. Não criar um worker 24x7 para manter Neon
ativo. `scripts/run_pipeline_once.py` é futuro e não existe agora.

## Procedimento futuro

1. Projetar `scripts/run_pipeline_once.py` após implementação para aceitar
   janela, deadline, correlação e modo dry-run; chamar `scripts/collect.py`
   somente para coleta onde o contrato permitir.
2. Reutilizar claims/idempotência existentes onde existirem, registrar início,
   estágio, contagens, erro e fim em logs/telemetria sem conteúdo de vaga ou
   segredo. Não fechar ausências a partir de run parcial.
3. Impor deadline antes de começar cada estágio e tratar SIGTERM: parar nova
   unidade, concluir/soltar claim conforme contrato e sair com status explícito.
4. Não iniciar IA, descoberta ou extração opcional automaticamente; cada uma
   segue sua própria autorização, quota e evidência.
5. Executar piloto com fixture ou fontes autorizadas, medir duração, conexões
   Neon e custo, e provar saída. Falha de estágio não dispara loop infinito.

### Ordem obrigatória do futuro runner

O contrato futuro executa `collect_enabled_sources`, que já pode chamar
`normalize_run`; em seguida executa `normalize_opportunities` somente para o
escopo ainda pendente, depois `evaluate_pending`. `analyze_pending` é opt-in e
fica desabilitado até quota/testes autorizados. Retenção de payload/assessment
também é opt-in e só ocorre após F53-13. Cada estágio imprime contagens de
entrada, concluído, falho, pulado e duração; ausência de flag/contrato bloqueia
o estágio, não o omite silenciosamente.

## Aceite

| ID | Positivo | Negativo/operacional |
| --- | --- | --- |
| AC01 | uma janela conclui ou reporta deadline | processo não permanece residente |
| AC02 | duas execuções disputam claim sem duplicar efeito | segunda respeita claim/lease |
| AC03 | SIGTERM encerra graciosamente | nenhuma unidade parcial é marcada concluída |
| AC04 | estágio falho preserva erro e permite retomada segura | não há retry infinito |
| AC05 | coleta não fecha ausência em run parcial | teste de interrupção confirma invariável |

Guardar log redigido por correlation ID, duração e relatório de conexões. Erro
de quota ou rede exige encerrar e agendar decisão humana, não manter processo
acordado.

## Pré-flight e diagnóstico

Antes de uma janela, verificar configuração, deadline UTC, espaço disponível,
conectividade autorizada e inexistência de execução em curso. O pre-flight não
deve iniciar coleta nem consultar fonte externa repetidamente. Saída esperada é
um run ID novo e estado de claim observável; claim ocupado é saída controlada,
não erro para retry apertado.

Erro transitório de fonte deve preservar tentativa, causa e estágio. Erro de
migração, autenticação do banco ou variável ausente bloqueia todas as etapas e
requer intervenção. Registrar contagens de itens iniciados/concluídos/falhos,
mas não payloads, URLs assinadas, headers ou credenciais.

## Arquivos futuros e testes

Após implementação, `scripts/run_pipeline_once.py` e testes de deadline,
SIGTERM, claim e run parcial devem existir antes do primeiro timer. Os nomes
são planejamento; não executar arquivo ausente. Provar com fixture que uma
interrupção não fecha presença/ausência nem duplica efeitos na retomada.

## Rollback e gate

Desabilitar o timer futuro e deixar API no digest anterior; revisar claims antes
de nova execução. F53-11, F53-12 e F53-16 dependem da prova dos ACs.
