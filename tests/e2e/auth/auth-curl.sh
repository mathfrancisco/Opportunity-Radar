#!/usr/bin/env bash
# curl wrapper for the Compose CI stack (test-only): sends a bearer from a fixture header
# file over TLS pinned to the ephemeral CA, and never prints the token.
#
#   auth-curl.sh [curl arguments...]            owner persona (default)
#   AUTH_PERSONA=non-owner auth-curl.sh ...     other persona
#   AUTH_CASE=expired|wrong-issuer|wrong-azp|unknown-kid auth-curl.sh ...   negative token
#   auth-curl.sh --refresh                      only (re)mint the header, print nothing
#
# Requires CI_AUTH_DIR (absolute, outside the checkout). The header is re-minted through the
# one-shot `auth-tools` Compose service when under 60 s of validity remain. curl's exit
# status and body are passed through untouched.
set -euo pipefail

: "${CI_AUTH_DIR:?CI_AUTH_DIR must point at the ephemeral fixture directory}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
persona="${AUTH_PERSONA:-owner}"
case_name="${AUTH_CASE:-valid}"
name="$persona"
if [ "$case_name" != "valid" ]; then name="$persona-$case_name"; fi
header_file="$CI_AUTH_DIR/tokens/$name.header"
exp_file="$CI_AUTH_DIR/tokens/$name.exp"

mint() {
  (cd "$root" && MSYS_NO_PATHCONV=1 docker compose -f compose.yaml -f compose.ci.yaml run --rm --no-deps -T \
    auth-tools mint --directory /fixtures --persona "$persona" --case "$case_name" \
    --header-file "/fixtures/tokens/$name.header" >/dev/null 2>&1)
}

needs_mint() {
  if [ ! -s "$header_file" ] || [ ! -s "$exp_file" ]; then return 0; fi
  # Negative tokens are minted once; only valid ones are kept alive.
  if [ "$case_name" != "valid" ]; then return 1; fi
  [ "$(($(tr -d '[:space:]' <"$exp_file") - $(date +%s)))" -lt 60 ]
}

if needs_mint; then mint; fi
if [ "${1:-}" = "--refresh" ]; then exit 0; fi

# Schannel (Windows curl) insists on a revocation check an ephemeral CA cannot answer; the
# chain and host name are still verified.
extra=()
if curl --version | grep -q Schannel; then extra=(--ssl-no-revoke); fi

# The bearer must only ever reach the pinned loopback origin: refuse any other URL.
for arg in "$@"; do
  case "$arg" in
    http://* | https://*)
      case "$arg" in
        https://127.0.0.1:8443 | https://127.0.0.1:8443/*) ;;
        *) echo "auth-curl.sh: refusing to send a bearer to a URL outside https://127.0.0.1:8443" >&2; exit 2 ;;
      esac
      ;;
  esac
done

exec curl "${extra[@]}" --cacert "$CI_AUTH_DIR/public/ca.pem" --header "@$header_file" "$@"
