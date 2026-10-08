# F53-16 — aceite pós-deploy

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-08, F53-09, F53-11, F53-12, F53-14 e F53-15.

## Smoke executável de piloto

```bash
export PILOT_API='https://api-pilot.<DOMINIO>'
export PILOT_FRONT='https://app-pilot.<DOMINIO>'
umask 077
BODY=$(mktemp); OWNER_HEADER=$(mktemp); OTHER_HEADER=$(mktemp); EXPIRED_HEADER=$(mktemp)
trap 'rm -f "$BODY" "$OWNER_HEADER" "$OTHER_HEADER" "$EXPIRED_HEADER"' EXIT
read -rs -p 'Token do dono: ' token; printf '\n'; printf 'Authorization: Bearer %s\n' "$token" >"$OWNER_HEADER"; unset token
read -rs -p 'Token de outro sub: ' token; printf '\n'; printf 'Authorization: Bearer %s\n' "$token" >"$OTHER_HEADER"; unset token
read -rs -p 'Token expirado: ' token; printf '\n'; printf 'Authorization: Bearer %s\n' "$token" >"$EXPIRED_HEADER"; unset token
chmod 600 "$OWNER_HEADER" "$OTHER_HEADER" "$EXPIRED_HEADER"
status() { curl --silent --output "$BODY" --write-out '%{http_code}' "$@"; }
assert_status() { test "$1" = "$2" || exit 1; }
assert_status "$(status "$PILOT_API/health/live")" 200
assert_status "$(status "$PILOT_API/companies")" 401
```

Fixtures JWT/JWKS offline de CI não funcionam no Clerk cloud. Para piloto, obter sessão real localmente por DevTools e escrever somente headers temporários; nunca passar JWT em argv.

```bash
for case in owner other expired; do
  case "$case" in
    owner) header=$OWNER_HEADER; expected=200 ;;
    other) header=$OTHER_HEADER; expected=403 ;;
    expired) header=$EXPIRED_HEADER; expected=401 ;;
  esac
  code=$(status --header "@$header" "$PILOT_API/companies")
  assert_status "$code" "$expected"; printf '%s=%s\n' "$case" "$code"
done
```

Esperado: live 200, anônimo/expirado 401, outro sub 403 e owner 200. Resultado diferente bloqueia piloto.

## TLS, CORS, Pages e operação

```bash
openssl s_client -connect "${PILOT_API#https://}:443" -servername "${PILOT_API#https://}" -verify_hostname "${PILOT_API#https://}" -verify_return_error </dev/null 2>&1 | grep 'Verify return code: 0'
curl --silent --show-error --fail --head "$PILOT_FRONT/"
curl --silent --include --request OPTIONS "$PILOT_API/companies" --header "Origin: $PILOT_FRONT" --header 'Access-Control-Request-Method: GET' --header 'Access-Control-Request-Headers: Authorization'
```

Repetir OPTIONS com origin inválido e confirmar ausência de CORS permitido. No navegador, recarregar SPA profunda, login/logout Clerk, ação do owner e negação de outro usuário; não capturar token.

## Job, Neon, backup e aceite

compose.cloud.yaml e scripts/run_pipeline_once.py são futuros. Após F53-10/F53-11, executar janela única com deadline e timer desligado. Registrar run ID, estágio, contagens e saída. Após requests, medir no painel Neon conexões, CU-h e bytes até idle F53-12; live não abre DB. Executar backup/restore isolado por F53-14 sem DSN em argv.

| ID | Passo | Evidência sanitizada |
| --- | --- | --- |
| AC01 | live, anônimo e loop JWT | rota, status, revisão e UTC |
| AC02 | TLS, CORS, assets e SPA | build ID e resultado |
| AC03 | job finito e Neon idle | run mascarado, duração, CU-h |
| AC04 | backup/restore | hash, bytes e status |
| AC05 | CI isolada/ARM | referência F53-15 |

## Rollback e gate

Salvar em evidencias/f53-16-aceite-<data>.md após execução, redigindo host, usuário, corpo e token. Falha desabilita timer e reverte somente Pages/digest/record de piloto. Escrita real congela writers e segue F53-18.
