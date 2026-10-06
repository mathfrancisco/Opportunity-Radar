# F51-16 — browser seletivo para fonte que exige JavaScript

- **Status:** Planejado/condicional
- **Prioridade:** P2
- **Esforço:** G
- **Risco:** crítico para SSRF, isolamento do host e processo órfão; browser não é fallback padrão.
- **Dependências:** F51-13; F51-15; fonte, termos e evidência JS revisados.

## Evidência e limites

Não há implementação de browser collector confirmada. `limited_discovery.py` já impõe limites e proteções para HTTP convencional, mas isso não cobre automaticamente Chromium, redirects, subrequests, DNS rebinding, WebSocket nem downloads. Este card propõe nova capacidade opt-in somente para uma fonte aprovada após demonstrar que API, JSON-LD e adapter HTML não entregam campo necessário por renderização JavaScript.

## Referências existentes

- [`limited_discovery.py`](../../../src/opportunity_radar/acquisition/limited_discovery.py) e [`probing.py`](../../../src/opportunity_radar/acquisition/probing.py): limites e sondagem convencional, não garantia para browser.
- [`registry.py`](../../../src/opportunity_radar/acquisition/registry.py) e [`service.py`](../../../src/opportunity_radar/acquisition/service.py): integração de collector e lifecycle.
- [`test_limited_discovery.py`](../../../tests/backend/acquisition/test_limited_discovery.py): casos SSRF/redirect HTTP existentes.
- Executor, container/runtime e `tests/backend/acquisition/test_browser_collector.py` são propostos; não alegar que já existem.

## Tarefas

1. Exigir relatório que reproduza campo ausente com API, JSON-LD e HTML fixture e demonstre que a página pública o renderiza somente após JS. Obter aprovação de owner/termos da fonte antes da navegação.
2. Definir flag por fonte (`enabled=false` default), limites configuráveis de tempo total, páginas, bytes, processos, memória, subrequests e concorrência 1 por host; bloquear downloads, service workers e protocolos desnecessários.
3. Validar URL inicial, cada redirect e cada request/subrequest, inclusive iframe, script, XHR/fetch, websocket e DNS resolvido imediatamente antes da conexão. Bloquear loopback, link-local, RFC1918, IPv6 local, metadata endpoints, portas/protocolos não permitidos e DNS que mude para endereço privado. Revalidar cada hop; não confiar no hostname inicial.
4. Usar processo/container isolado sem credenciais, diretório temporário descartável e egress allowlist por host aprovado. Capturar somente campos autorizados e metadados de request/status; sanitizar artefatos antes de fixture.
5. Implementar timeout que encerra page, browser context e processo; aguardar confirmação de término/cleanup antes de liberar claim/single-flight ou lançar execução substituta. Processo não encerrável mantém estado pendente e bloqueia novo browser para a fonte.
6. Não resolver login, CAPTCHA, paywall, consentimento restritivo ou bloqueio anti-bot; registrar `policy_blocked` e parar.

## Critérios de aceite

| ID | Critério | Given / When / Then | Teste proposto e evidência |
| --- | --- | --- | --- |
| AC01 | Execução só ocorre com prova JS e autorização por fonte. | Dada fonte sem relatório ou flag explícita, quando registry tenta execução, então zero browser process/request ocorre. | `test_browser_requires_source_flag_and_js_evidence` (proposto); fonte segue disabled e log de motivo. |
| AC02 | Subrequest privada ou redirect é bloqueado antes de conexão. | Dada página pública que tenta fetch para `127.0.0.1`, metadata IP, redirect privado ou DNS rebinding, quando browser navega, então request é interceptado e destino recebe zero conexão. | `test_browser_blocks_private_redirects_and_subrequests` (proposto); fake network/intercept log. |
| AC03 | Caps de tempo e recursos são aplicados e cleanup confirmado. | Dado page infinita ou excesso de bytes/requests, quando cap expira, então processo termina, contexto fecha e claim só libera após confirmação. | `test_browser_timeout_waits_for_process_cleanup` (proposto); timestamps e processo não vivo ao finalizar. |
| AC04 | Sem login ou bypass anti-bot. | Dada página com CAPTCHA/login, quando detectada, então coleta termina `policy_blocked`, sem tentativa de contorno. | `test_browser_does_not_bypass_login_or_captcha` (proposto); zero credenciais/retries. |
| AC05 | Browser opt-in não afeta fontes não elegíveis e parcial não fecha ausências. | Dado browser falho para uma fonte com listagem anterior, quando run persiste, então outras fontes seguem fluxo atual, run alvo é parcial e ausências não fecham. | `test_browser_failure_is_source_scoped_and_partial` (proposto em fixture `_test`); runs e presenças. |

## Rollout e reversão

Só permitir piloto isolado depois de F51-15 e revisão de segurança. Ativar uma fonte, concorrência por host 1 e caps pequenos; cada request conta no mesmo orçamento e telemetria. Rollback desliga flag, interrompe novos claims e termina browser/processos ativos com cleanup aguardado; não libera lease com processo vivo. Preservar artefato sanitizado e run parcial. Nenhum login/CAPTCHA bypass. O card pode ser adiado sem bloquear coleta API/HTML.
