# F53-17 — monitoramento e incidentes

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-09, F53-11 e F53-14.

## Objetivo, pré-requisitos e limite

Este card cria o procedimento futuro para detectar host, job, backup e custo sem
manter Neon acordado. Antes de configurar, confirmar conta OCI, compartment, região,
VM piloto, owner operacional, e permissões mínimas para Monitoring e Notifications.
Conferir no console as quotas e preço vigente de Monitoring/Notifications. Nenhuma
métrica Neon ou custom aparece automaticamente no OCI; não declarar alerta automático
até existir detector/timer implementado e testado.

## Criar contato de alerta no OCI

1. No console OCI, selecionar compartment e região do piloto.
2. Abrir **Developer Services**, **Notifications**, **Topics**, e criar tópico
   `opportunity-radar-pilot-alerts`; registrar OCID mascarado e owner.
3. Em **Subscriptions**, criar protocolo Email para `<EMAIL_DO_OWNER>`.
4. Confirmar o e-mail pelo link recebido e verificar estado **Active** no console.
5. Parar se a assinatura estiver Pending, o owner não receber confirmação ou a
   conta não tiver quota/preço aprovado. Não usar endereço pessoal sem recuperação.

## Criar alarmes de host

Na fonte oficial de criação de alarmes, abrir **Observability & Management** →
**Monitoring** → **Alarm Definitions** → **Create Alarm**. Selecionar namespace
**oci_computeagent**, métrica de CPU ou memória efetivamente emitida pela VM e
dimensão `resourceId=<OCID_DA_VM>`. Antes de salvar, confirmar no Metrics Explorer
que a série existe; métrica ausente exige instalar/configurar agente futuro, não um
alarme vazio. Selecionar o tópico criado, repetir notificação a cada 15 minutos,
habilitar o alarme e registrar a regra sem OCID ou e-mail.

Configurar inicialmente memória >=85% por 10 minutos. OOM é evento imediato se
o coletor futuro o produzir. Disco >=80% é warning e >=90% crítico. CPU deve ter
limiar aprovado após F53-12, não um valor inventado. Referência: [OCI Create Alarm](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/create-alarm-basic.htm).

## Teste controlado e reversão

1. No piloto, duplicar a definição ou reduzir temporariamente o limiar para um
   valor já observado, sem criar carga artificial, job extra ou tráfego.
2. Aguardar avaliação e confirmar no console transição **FIRING**.
3. Confirmar e-mail recebido, anotando UTC, nome mascarado, severidade e owner.
4. Restaurar limiar/duração aprovados e aguardar estado **OK**.
5. Se não disparar ou não entregar, desabilitar promoção, corrigir métrica/tópico
   e repetir o teste; não baixar limiar permanentemente para esconder falha.

## Neon, job e backup: rotina até automação

Uma vez por dia, o owner consulta manualmente o painel Neon e registra CU-h,
armazenamento e conexões. Calcular projeção mensal como `CU-h acumulada / dias
observados × dias do mês` e comparar também cenários das janelas previstas. Abrir
warning com 70 CU-h consumidos ou projeção >80; não esperar alcançar 80 para
agir. Storage usa baseline mais crescimento observado projetado: warning/crítico
entre 80–90% de 1 GB conforme risco aprovado. Idade do último backup é comparada
ao RPO acordado. Timer/detector futuro precisa emitir sucesso, falha e atraso de
job/backup antes de qualquer alerta automático ser declarado. Essa rotina não
usa query de keepalive, scheduler contínuo ou probe de readiness.

## Diagnóstico local sem segredos

Executar na VM somente durante incidente ou janela aprovada. Não usar docker
inspect, logs que revelem env, nem endpoint readiness como monitor contínuo.

```bash
sudo systemctl status opportunity-radar-pipeline.timer
sudo systemctl stop opportunity-radar-pipeline.timer
sudo journalctl -u opportunity-radar-pipeline.service --since '<INICIO_UTC>' --until '<FIM_UTC>'
free -h
df -h
docker stats --no-stream
curl --silent --show-error --max-time 10 --fail https://api.<DOMINIO>/health/live
```

Resultado esperado: timer é parado antes de contenção, journal identifica run e
estágio sem segredo, liveness responde sem abrir DB. Falha de liveness, OOM, disco
ou backup ativa o roteiro abaixo; conexão Neon persistente exige revisar F53-09/12.

## Sequência de incidente

1. Reconhecer alerta, registrar UTC, owner, severidade, revisão e run ID mascarado.
2. Conter: parar timer e writers; não apagar container, state, dump ou log.
3. Preservar métricas, journal redigido, estado do alarme e hash do último backup.
4. Diagnosticar host, job, TLS, quota ou backup com os comandos aprovados.
5. Para dados, restaurar primeiro em destino isolado por F53-14; nunca restaurar
   produção por reflexo.
6. Corrigir em piloto, executar smoke F53-16 e provar backup/idle/alerta.
7. Obter decisão do owner, reativar timer somente após evidência e observar a
   próxima janela; registrar causa, impacto e ação preventiva.

## Rollback e gate

Para reverter alarme, desabilitar somente a definição piloto confirmada, restaurar
limiar e destino anteriores e testar entrega; não remover tópico ou assinatura
antes de existir contato substituto. Falha em qualquer AC mantém o timer parado e
bloqueia F53-18.

## Aceite e evidência

| ID | Teste | Evidência redigida |
| --- | --- | --- |
| AC01 | tópico e e-mail Active | tópico mascarado, UTC e owner |
| AC02 | métrica resourceId emite e alarme FIRING | regra, dimensão mascarada e estado |
| AC03 | e-mail chega no teste controlado | UTC de FIRING/recebimento e severidade |
| AC04 | limite é restaurado e estado volta OK | antes/depois sem segredo |
| AC05 | exercício de incidente preserva backup e retoma janela | cronologia e smoke F53-16 |

Guardar apenas em `evidencias/f53-17-incidente-<data>.md` após execução. Redigir
OCID, e-mail, hosts, IDs, logs e qualquer credencial. F53-18 depende de todos os
ACs.
