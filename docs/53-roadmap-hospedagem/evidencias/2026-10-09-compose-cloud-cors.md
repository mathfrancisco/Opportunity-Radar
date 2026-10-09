# F53-05/F53-09 — preparo local de Compose cloud e CORS

Data: 2026-10-09.

Implementação local preparada:

- `compose.cloud.yaml` contém somente `migrate`, `api`, `worker` finito e `proxy`;
  não declara PostgreSQL, Redis, frontend, volume de banco ou porta publicada da API.
- Imagens, banco, identidade, owner do worker, deadline e paths dos certificados são
  referências obrigatórias de ambiente; nenhum valor ou certificado foi criado.
- O proxy redireciona 80 para HTTPS e usa certificados montados read-only. A API só é
  acessível na rede Compose e seu healthcheck chama `/health/live` a cada 30 segundos.
- O proxy só aceita `PUBLIC_HOSTNAME`: o virtual host padrão de HTTP e HTTPS devolve
  `444`, o redirecionamento usa o hostname configurado (não o cabeçalho `Host`) e o
  upstream recebe esse mesmo hostname. A imagem oficial do nginx expande o template
  montado em `/etc/nginx/templates/` no startup.
- `FRONTEND_ORIGIN` é uma origem HTTP(S) única sem caminho/wildcard. CORS permite
  apenas métodos explícitos e `Authorization`, `Content-Type` e `X-Correlation-ID`.
  A factory de produção exige HTTPS; a factory explícita de desenvolvimento ainda
  permite `http://localhost`.
- Antes de uma execução cloud, `scripts/validate_cloud_images.py` exige para API,
  worker e proxy uma referência `image@sha256:<64 hex>` e um JSON de manifest salvo
  que declare `linux/arm64`. Ele não faz build nem consulta registry.

Não executado nesta etapa: build ARM64, `docker compose` cloud, TLS/DNS, conexão Neon,
e qualquer deploy. Esses itens exigem imagens publicadas, paths de certificado e contas
externas; não são evidência de hospedagem validada.

Validação local, usando a imagem já presente `f53-recovery-20261008-api:latest` com o
checkout montado, sem rebuild:

```text
6 passed, 2 warnings in 8.54s
All checks passed!
git diff --check: exit 0
```

O teste foi executado diretamente com a imagem existente
`f53-recovery-20261008-api:latest` e o checkout montado, sem banco, build ou cloud:

```text
rtk proxy docker run --rm --mount type=bind,src=C:\Users\mathf\Documents\GitHub\Opportunity-Radar,dst=/app -w /app f53-recovery-20261008-api:latest pytest -q tests/backend/test_cloud_compose_contract.py
```

O Ruff focado em arquivos Python devolveu `All checks passed!`. O venv local não tinha
PyJWT, portanto não foi usado como evidência do teste HTTP.
