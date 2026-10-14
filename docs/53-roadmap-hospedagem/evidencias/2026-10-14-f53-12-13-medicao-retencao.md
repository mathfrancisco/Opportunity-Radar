# F53-12/13 — medição de recursos e retenção

Data: 2026-10-14 (UTC). PR #84, merge `cbdf45c`.

## Validação local

Comando executado no checkout baseado em `origin/main`, com imagem
`python:3.12-slim` e cache de pip:

```sh
MSYS_NO_PATHCONV=1 docker run --rm -v "<checkout-origin-main>:/src:ro" -v or-pip-cache:/root/.cache/pip python:3.12-slim sh -c "cp -r /src /w && cd /w && pip install -q -r requirements-dev.txt 2>/dev/null && pip install -q --no-deps . 2>/dev/null && pytest -q -p no:cacheprovider tests/backend/test_measure_host_resources.py tests/backend/test_retention_report.py"
```

Saída literal:

```text
3 passed, 1 skipped in 0.28s
```

Custos e quotas não medidos. A execução valida contratos locais; não acessa
VM, OCI, Neon ou dados de produção.

## Checks do PR

`gh pr checks 84 --repo mathfrancisco/Opportunity-Radar`:

- `Publish / ${{ matrix.image }}`: skipped
- `Compose / smoke E2E and persistence`: pass
- `Workers Builds: opportunity-radar`: pass
- `Backend / lint and types`: pass
- `Backend / tests and migrations`: pass
- `Frontend / lint, types, tests and build`: pass
- `GitGuardian Security Checks`: pass

Nenhum segredo foi impresso.
