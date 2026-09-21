# Fase 11 — Reavaliação por mudança de versão

Esta fase faz a Inbox responder aos dados atuais sem reescrever assessments antigos.

## Ordem dos cards

| Card | Resultado | Depende de |
| --- | --- | --- |
| [F11-01](f11-01-identidade-de-atualidade.md) | Identidade objetiva de assessment atual | F10-01 |
| [F11-02](f11-02-reavaliacao-retomavel.md) | Reavaliação retomável por mudança de versão | F11-01, F10-01 |
| [F11-03](f11-03-contrato-da-inbox.md) | Contrato da Inbox com fallback e `is_stale` | F11-01 |
| [F11-04](f11-04-estado-desatualizado-na-ui.md) | Card da Inbox diferencia atual, antigo e ausente | F11-02, F11-03 |

## Gate da fase

A fase termina quando uma alteração controlada do perfil produz um novo assessment, o
assessment anterior permanece consultável e a Inbox mostra corretamente os estados antes,
durante e depois da reavaliação.

