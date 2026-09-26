# CARD F18-05 — Delta, presença e retomada

- **Status:** Backlog
- **Fase:** 18 — Varredura produtiva
- **Depende de:** F18-04, F17-07, F17-06
- **Bloqueia:** F18-06, F18-09
- **Origem:** [SPEC 39](../../39-spec-varredura-produtiva.md), §8

## Resultado

Revisitar confirma presença sem duplicar conteúdo ou IA; queda de execução retoma sem perda e sem encerramento incorreto.

## Escopo

- Persistir observação por run/item mesmo quando dedupe reaproveita RawItem. Separar hash bruto e hash semântico versionado.
- Hash semântico remove só ruído definido; mudança material invalida derivados, mudança cosmética não obriga inferência.
- 304 só reutiliza inventário completo persistido se toda a representação/manifest de páginas foi revalidada no mesmo escopo; resto fica parcial/desconhecido.
- Commit atômico de evidência, observações e checkpoint. Cursores de retomada, rotação de termos e watermark são distintos.
- Nova rodada completa começa do início; replay antigo não regride last_seen/content e payload expirado permanece explicitamente indisponível.

## Fora de escopo

- Ampliar para serviços distribuídos, IA remota ou coleta autenticada.
- Executar testes, migrações ou coletas reais nesta revisão documental.

## Critérios de aceite

- [ ] Duas visitas iguais atualizam presença sem conteúdo/IA duplicados.
- [ ] 304 não fecha vaga nem mascara inventário incompleto.
- [ ] Quedas antes/depois do commit retomam idempotentemente.
- [ ] Mudança material reprocessa; alteração cosmética não gera onda de análise.

## Verificação

- **CI:** Falhas injetadas entre fetch/commit, cursor repetido, 304 parcial/completo, dedupe, replay fora de ordem e retenção.
- **Máquina de referência:** Medir proporção de bytes, normalizações e inferências evitadas, preservando recall amostral.
- Conforme AGENTS.md, validação local depende de pedido explícito.

## Arquivos prováveis

`acquisition/service.py`, repository/models, opportunities/service.py, migrations de observações e fixtures.
