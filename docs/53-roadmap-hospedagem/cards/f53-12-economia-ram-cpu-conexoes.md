# F53-12 — economia de RAM, CPU e conexões

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-05, F53-06, F53-10.

## Objetivo

Derivar limites de processo e pool de medições reais, não de suposições. A A1
tem alvo 2 OCPUs/12 GB, mas isso não autoriza todo serviço consumir o máximo.
Não introduzir modelo local, Redis ou processo residente sem dado que prove a
necessidade.

## Sequência futura

1. No piloto, medir pico e repouso de proxy, API e cada janela de job em CPU,
   RSS, reinícios, latência e conexões Neon. Marcar revisão, carga de fixture e
   duração da janela; não registrar dados de usuário.
2. Definir limites de memória/CPU e número de processos somente depois de três
   execuções comparáveis. Reservar margem operacional e registrar cálculo.
3. Medir conexões abertas antes, durante e depois de run. A API usa
   `pool_pre_ping=True`; confirmar efeito contra pool Neon e não tratar pre-ping
   como permissão para manter banco acordado.
4. Projetar, se necessário, limites futuros de pool/overflow e timeout de
   conexão. Não declarar variável de produção antes de código/teste que a leia.
5. Rodar liveness sem DB e observar Neon em repouso. Readiness é limitado a
   deploy/on-demand; `/health` a cada 10 s é proibido na composição cloud.
6. Comparar consumo mensal com meta <=80 CU-h; se janelas e conexões excederem,
   reduzir frequência/duração ou capacidade antes de ampliar dados reais.

## Diagnóstico

OOM/restart exige diminuir concorrência, corrigir leak ou aumentar apenas com
aprovação de custo. Pool exaurido exige observar consumidores e encerramento;
não aumentar indiscriminadamente. Conexões no período idle apontam healthcheck,
timer ou API mal configurada e bloqueiam aceitação.

## Aceite

| ID | Evidência positiva | Negativa/operacional |
| --- | --- | --- |
| AC01 | três runs mostram pico e margem por processo | limite sem medição é rejeitado |
| AC02 | conexões voltam a zero/idle após janela | probe 10s é detectado e bloqueia |
| AC03 | Neon projeta <=80 CU-h e <1 GB | 0,25 CU 24x7 (186 CU-h) falha |
| AC04 | sem Redis/modelo local no Compose cloud | serviço extra exige card e orçamento |

Guardar CSV ou captura redigida de métricas, parâmetros e cálculo. Nunca
coletar env, DSN, tokens ou SQL com dados pessoais como métrica.

## Rollback e gate

Voltar ao último conjunto de limites medido e parar jobs excessivos; não apagar
telemetria. F53-16 só começa após todos os ACs e uma janela idle demonstrada.

## Execução de medição no piloto

Na VM OCI, antes de uma janela, executar `free -h` e `df -h`; durante e depois,
executar `docker stats --no-stream` para proxy, API e job. Guardar somente CPU,
RSS, limite e timestamp. No painel Neon registrar conexões, CU-h e bytes antes,
após e uma janela idle; meta é <=80 CU-h/mês, <1 GB e nunca assumir que a quota
100 CU-h é orçamento. A composição futura usa `/health/live`; probe que abra DB
ou conexão persistente é falha. Limites de pool são futuros e só entram depois
de três medições: não inventar variável sem código que a consuma.

## Três janelas comparáveis e cálculo de orçamento

Na VM piloto, execute o bloco antes, durante e depois de cada uma das três
janelas com a mesma fonte fixture, revisão e duração. Use UTC e não redirecione
saída para arquivo que possa conter environment ou segredo.

```bash
date -u +%FT%TZ
free -h
df -h /
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}'
```

1. Registre timestamp, commit, estágio, CPU, RSS/memória, uso de disco e
   conexões Neon antes, pico e cinco minutos após terminar.
2. Repita três vezes sem mudar digest, número de fontes, cache, janela ou
   limite. Se houver mudança, reinicie a série e declare o motivo.
3. Calcule limite de cada processo como `max_peak × 1,3` em experimento e some
   API, proxy e job; mantenha `reserved_host` fora dessa soma. A soma deve caber
   no orçamento aprovado da VM de 12 GB antes de configurar qualquer limite.
4. Projete CU-h como `CU × tamanho_da_janela × execuções_mensais` e some demanda
   fora da janela. Meça cold start e janela idle de cinco minutos; não presuma
   suspensão se o dashboard ainda mostrar conexão/atividade.
5. Documente pool/concurrency apenas como proposta futura: entrada, teste de
   carga isolado, resultado, rollback e código que consome a configuração. Não
   invente env de runtime antes dessa implementação.

Resultado esperado: três séries comparáveis, uma margem explícita e Neon sem
query contínua no intervalo idle. Se conexões persistirem, confira timer, worker,
`pool_pre_ping` e healthcheck; não adicione keepalive periódico como "solução".
