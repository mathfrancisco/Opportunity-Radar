# CARD F13-02 — Alertas e recovery de fontes

- **Status:** Concluído em 2026-09-22
- **Fase:** 13 — Operação contínua
- **Depende de:** F13-01
- **Bloqueia:** F13-06
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§24–26

## Resultado

Uma fonte que falha três vezes consecutivas abre um incidente, envia um único
webhook e envia uma recuperação no primeiro sucesso posterior.

## Contexto

A Overview exige abertura manual. O alerta deve ser deduplicado por incidente e não
deve impedir a coleta quando o webhook estiver ausente ou indisponível.

## Escopo

- Contar falhas consecutivas por fonte a partir de `SourceRun`.
- Abrir incidente no limiar de três falhas e registrar seu envio.
- Não reenviar alertas durante o mesmo incidente.
- Enviar recovery no primeiro sucesso e liberar nova sequência de alertas.
- Registrar em log estruturado e expor ao `doctor` quando não houver webhook.

## Fora de escopo

- Pager, múltiplos provedores de notificação, escalonamento humano e retries
  infinitos do webhook.

## Notas de implementação

Configure o webhook por ambiente. O envio é best-effort: falha no canal não altera o
resultado da fonte nem bloqueia outros collectors. Persista a identidade do incidente
e os marcos de alerta/recovery para que reinícios não dupliquem mensagens.

## Critérios de aceite

- [x] Três falhas consecutivas enviam um único alerta com webhook configurado.
- [x] Quarta e demais falhas do incidente não reenviam o alerta.
- [x] Primeiro sucesso envia recovery e encerra o incidente.
- [x] Nova sequência de três falhas abre novo incidente.
- [x] Sem webhook, o caso aparece em log estruturado e no `doctor`.
- [x] Falha do webhook não aborta a coleta nem outras fontes.

## Verificação

Use uma fonte controlada para simular três falhas, sucesso e três novas falhas;
confirme uma mensagem de alerta por incidente e uma de recovery. Repita sem webhook.

## Arquivos prováveis

- `src/opportunity_radar/acquisition/service.py`
- `src/opportunity_radar/acquisition/models.py`
- `src/opportunity_radar/settings.py`
- `src/opportunity_radar/doctor.py`
