# F53-05/F53-09 — preparo local de Compose cloud e CORS

Data: 2026-10-09.

Implementação local preparada:

- `compose.cloud.yaml` contém somente `migrate`, `api`, `worker` finito e `proxy`;
  não declara PostgreSQL, Redis, frontend, volume de banco ou porta publicada da API.
- Imagens, banco, identidade, owner do worker, deadline e paths dos certificados são
  referências obrigatórias de ambiente; nenhum valor ou certificado foi criado.
- O proxy redireciona 80 para HTTPS e usa certificados montados read-only. A API só é
  acessível na rede Compose e seu healthcheck chama `/health/live` a cada 30 segundos.
- `FRONTEND_ORIGIN` é uma origem HTTP(S) única sem caminho/wildcard. CORS permite
  apenas métodos explícitos e `Authorization`, `Content-Type` e `X-Correlation-ID`.

Não executado nesta etapa: build ARM64, `docker compose` cloud, TLS/DNS, conexão Neon,
e qualquer deploy. Esses itens exigem imagens publicadas, paths de certificado e contas
externas; não são evidência de hospedagem validada.

Validação local, usando a imagem já presente `f53-recovery-20261008-api:latest` com o
checkout montado, sem rebuild:

```text
3 passed, 2 warnings in 6.42s
All checks passed!
git diff --check: exit 0
```

O primeiro Ruff no container não pôde criar `.ruff_cache` no mount (permissão negada);
a repetição com `--no-cache` produziu o resultado acima. O venv local não tinha PyJWT,
portanto não foi usado como evidência para o teste HTTP.
