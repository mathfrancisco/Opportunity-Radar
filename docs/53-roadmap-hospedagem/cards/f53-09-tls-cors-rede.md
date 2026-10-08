# F53-09 — TLS, CORS e rede

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-04, F53-05, F53-07.

## Objetivo

Expor somente `https://api.<DOMINIO>` por proxy TLS, limitar CORS ao app e
manter processo e banco privados. A validação de JWT não substitui TLS nem
segmentação de rede.

## Sequência futura

1. Configurar proxy HTTPS na VM para API interna e certificado válido para
   `api.<DOMINIO>`. Redirecionar HTTP para HTTPS; não expor porta da aplicação.
2. Permitir CORS apenas para `https://app.<DOMINIO>` e métodos/headers usados.
   Não usar `*` com credenciais, nem aceitar qualquer origin refletido.
3. Publicar `/health/live` sem consulta ao banco para liveness. Usar readiness
   que consulta DB somente no deploy, on-demand ou janela limitada; `routes.py`
   atual tem `/health/live` sem DB, enquanto `/health/ready` e `/health` usam DB.
4. No futuro `compose.cloud.yaml`, trocar healthcheck frequente de `/health`
   pelo `/health/live`; o `compose.yaml` atual faz `/health` a cada 10 segundos
   e impediria o Neon de dormir.
5. Verificar de fora TLS, redirecionamento, headers e portas e de dentro que API
   alcança Neon sem publicar 5432. Não cole saída que revele env ou certificados.
6. Testar origin permitido, origin estranho, HTTP e bearer ausente. Registrar
   códigos e headers permitidos redigidos.

## Aceite

| ID | Critério | Prova |
| --- | --- | --- |
| AC01 | HTTP redireciona e HTTPS tem certificado válido | teste externo datado |
| AC02 | CORS só aceita origin `app` | origin estranho não recebe ACAO |
| AC03 | banco e portas internas não são públicos | varredura de portas redigida |
| AC04 | liveness não abre conexão Neon | métrica Neon idle sem probes DB |
| AC05 | readiness é limitado e documentado | log de deploy/on-demand, não timer 10s |

Falha TLS, certificado vencido ou CORS amplo interrompe promoção. Se Neon registrar
conexões de healthcheck, corrigir caminho/Compose e repetir período idle.

## Configuração do proxy e validação externa

F53-09 cria configuração revisada de proxy, não uma exposição direta do Uvicorn.
O proxy é o único listener público; API fica na rede local/privada e Neon recebe
apenas conexão TLS de saída.

1. Emita/configure certificado para `api.<DOMINIO>` e registre expiração/dono.
2. Publique 443 e, se necessário para desafio, 80 com redirect HTTPS.
3. Defina `FRONTEND_ORIGIN=https://app.<DOMINIO>` sem wildcard.
4. Permita somente métodos e `Authorization` necessários no preflight.
5. De fora da OCI, confira certificado, hostname, redirect e portas expostas.
6. Do browser, teste origin permitido e origin com scheme/host/porta diferente.
7. Confirme que probe frequente é `/health/live`; readiness DB ocorre só em
   deploy, demanda ou janela limitada.

Resultados: origin permitido recebe headers CORS esperados; origin estranho não
recebe ACAO; HTTP não entrega dados; 5432 e porta Uvicorn não estão acessíveis.
Se certificado, CORS ou NSG falhar, restaure configuração de proxy/record
anterior e mantenha API privada. Não desative TLS ou autenticação para depurar.

## Sondas externas e preflight reproduzível

Após F53-09 implementar proxy e DNS de piloto, rode sondas de estação externa.
Substitua somente `<DOMINIO>`; não use bearer token e redija IPs/headers
sensíveis na evidência.

```powershell
curl.exe -I http://api.<DOMINIO>/health/live
curl.exe -I https://api.<DOMINIO>/health/live
curl.exe -sS -D - -o NUL -X OPTIONS https://api.<DOMINIO>/<ROTA_PRIVADA> `
  -H "Origin: https://app.<DOMINIO>" `
  -H "Access-Control-Request-Method: GET" `
  -H "Access-Control-Request-Headers: Authorization"
openssl s_client -connect api.<DOMINIO>:443 -servername api.<DOMINIO>
```

1. Espere redirect HTTP, certificado com hostname correto e `/health/live` sem
   detalhes de banco.
2. Confira que preflight permitido retorna somente origin, método e header
   configurados; registre status e nomes de headers, não cookies/tokens.
3. Repita OPTIONS com `Origin: https://estranho.example`; não pode receber
   `Access-Control-Allow-Origin` igual ao origin enviado.
4. Verifique de fora que 5432, 6379 e porta interna API não respondem; associe
   o resultado às regras NSG do plan aprovado.
5. Confirme no Neon uma janela sem conexões de `/health` frequentes.

Falha no `openssl` aponta DNS, certificado, listener ou cadeia. CORS amplo aponta
origem/regex incorreto; porta aberta exige corrigir Terraform e novo Plan. Não
abra banco para diagnóstico.

## Rollback e gate

Restaurar proxy/configuração anterior e remover record de piloto se necessário.
Não desabilitar autenticação ou TLS para diagnosticar. F53-16 e F53-17 dependem
de AC01–AC05.
