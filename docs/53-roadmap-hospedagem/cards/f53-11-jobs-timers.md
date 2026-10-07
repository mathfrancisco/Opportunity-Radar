# F53-11 — jobs e timers

**Prioridade:** P1. **Estado:** planejado. **Depende de:** F53-10.

## Objetivo

Agendar janelas finitas sem manter scheduler, conexão PostgreSQL ou probe
acordados 24x7. O estado atual não comprova timer cloud, heartbeat nem métrica
adequada para este modelo.

## Pré-requisitos e desenho futuro

Use um mecanismo único de timer da OCI ou sistema operacional da VM, escolhido
e registrado pelo operador. O timer inicia o comando finito; ele não chama a
API pública nem substitui claim no banco. A API e o proxy permanecem separados
do processo de job.

1. Definir horários, duração máxima, timezone UTC, proprietário e regra de
   manutenção para cada estágio: coleta, normalização e avaliações autorizadas.
2. Configurar unidade/job com `TimeoutStartSec` ou deadline equivalente menor
   que a janela e política de não sobreposição. O comando futuro recebe
   `<RUN_ID>`, `<DEADLINE_UTC>` e ambiente de cofre.
3. Emitir logs estruturados de agendamento, início, claim, progresso, saída,
   duração e próximo horário. Heartbeat é log/métrica enquanto o job existe,
   não linha periódica no banco quando ele não existe.
4. Expor indicador de último sucesso, último erro e atraso esperado. Alertar
   apenas depois de uma janela perdida definida, evitando alarmes por suspensão
   normal do Neon fora da janela.
5. Testar reboot da VM, timer perdido, execução duplicada e cancelamento. Após
   reboot, o timer só agenda a próxima janela ou aplica regra explícita de
   catch-up; não executa uma avalanche de runs vencidos.

## Unidade e timer futuros na VM

Executar estes passos no shell administrativo da VM piloto, após F53-05 e
F53-10; os arquivos abaixo ainda não existem e são contrato de implementação.
Criar `/etc/systemd/system/opportunity-radar-pipeline.service` com usuário sem
login, diretório de trabalho da aplicação, `EnvironmentFile` de permissão 0600,
`Type=oneshot` e `ExecStart=/usr/local/sbin/run-opportunity-radar-window`,
`TimeoutStartSec=<SEGUNDOS>`
e `Restart=no`. Não colocar Neon, Clerk ou outros segredos na unit.

Criar `/etc/systemd/system/opportunity-radar-pipeline.timer` com `OnCalendar=`
em UTC, `Persistent=false`, `RandomizedDelaySec=<JANELA>` e `Unit=` apontando ao
service. Rodar `sudo systemctl daemon-reload`, `sudo systemctl enable --now
opportunity-radar-pipeline.timer`, `systemctl list-timers`, `systemctl status
opportunity-radar-pipeline.timer` e `journalctl -u opportunity-radar-pipeline.service
--since <INICIO_UTC>`. Redigir env, host e run IDs antes de arquivar saída.

O wrapper futuro calcula a cada ativação um `RUN_ID` e `DEADLINE_UTC` como UTC
atual mais duração aprovada, então chama o worker com esse deadline. Não gravar
instante absoluto na unit: a segunda janela receberia deadline passado.

Para parar com segurança, executar `sudo systemctl disable --now
opportunity-radar-pipeline.timer`, aguardar o service terminar até deadline e
confirmar `systemctl is-active` como inativo. Não usar kill -9: SIGTERM é a
prova de parada graciosa de F53-10.

## Resultado, erro e remediação

Espera-se zero conexões Neon entre janelas por timer, healthcheck ou scheduler.
Se o timer iniciar duas vezes, claim deve permitir no máximo um run útil; se
falhar antes do claim, registrar o erro e alertar. Não habilitar retry contínuo
nem usar carga artificial para impedir suspensão do banco.

## Aceite

| ID | Teste | Saída esperada |
| --- | --- | --- |
| AC01 | observar uma janela completa | um início, uma saída e métricas correlacionadas |
| AC02 | reiniciar VM antes da janela | próximo horário preservado, sem duplicação |
| AC03 | simular job lento/timeout | deadline encerra e reporta falha |
| AC04 | observar intervalo ocioso | Neon fica sem probe/scheduler DB |
| AC05 | simular janela perdida | alerta tem run ID, fase e instrução de resposta |

Arquivar status do timer, logs redigidos e série temporal de conexões. Não usar
logs de container ou `inspect` que possam expor ambiente.

## Rollback e gate

Desabilitar timer e confirmar que não há processo pendente antes de alterar
agenda. F53-16 e F53-17 exigem os ACs; F53-18 não usa catch-up automático.
