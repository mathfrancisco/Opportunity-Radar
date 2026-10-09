# F53-14 — hardening local de backup e restore

Data: 2026-10-09. Escopo: preparação local; nenhum backup, restore, upload,
credencial ou recurso externo foi executado.

## Implementado

- `pg_dump` e `pg_restore` recebem host, porta, usuário, base e TLS por ambiente;
  uma senha presente na URL fica somente em `PGPASSFILE` temporário, removido ao
  sair do contexto.
- O argv não recebe DSN nem senha, e falhas de subprocesso são redigidas.
- `restore_check.py` exige antes de conectar: `RUN_DATABASE_INTEGRATION=1`,
  `DATABASE_INTEGRATION_ISOLATED=1`, base terminada em `_test` e scratch seguro
  terminado em `_test`. Não há `RESTORE_CHECK_UNSAFE_HOST` nem outro bypass.
- Retenção agora só lista candidatos no ciclo de backup; não remove dumps ou
  manifestos depois de um dump. A remoção programática requer `apply=True`, que
  não é exposto pelo comando de backup.

## Checks executados

```text
rtk proxy .\.venv\Scripts\python.exe -m pytest -q tests\backend\test_backup.py tests\backend\test_restore_check_safety.py
31 passed, 3 skipped in 0.38s
```

```text
rtk proxy .\.venv\Scripts\python.exe -m ruff check scripts\backup.py scripts\restore_check.py src\opportunity_radar\platform\backup.py tests\backend\test_backup.py tests\backend\test_restore_check_safety.py
All checks passed!
```

```text
git diff --check
exit 0
```

## Ainda não provado

Não há prova de restore hospedado, cópia cifrada externa, permissões de bucket,
lista de processos em host cloud ou retenção operacional após um restore válido.
Esses atos exigem credenciais, destino isolado demonstrável e autorização de
operação; F53-14 permanece em andamento.
