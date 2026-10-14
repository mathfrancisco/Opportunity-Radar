# F53 P1 dashboard — evidência local (2026-10-09)

Escopo validado localmente: ownership do Inbox, overview e saved searches; correção de
perfil explícito em `_latest_assessments`; e compatibilidade dos callers de Inbox que
agora exigem `owner_sub`.

## Ambiente

- Projeto Compose isolado: `f53-recovery-20261008`.
- Banco efêmero isolado com nome terminado em `_test`; guards
  `RUN_DATABASE_INTEGRATION=1` e `DATABASE_INTEGRATION_ISOLATED=1` confirmados antes
  de conectar.
- Migration chegou a `20261008_0069` nesse banco isolado.
- O módulo `matching/currency.py` foi montado a partir de `HEAD`, somente leitura, para
  demonstrar que este pacote não depende da edição concorrente do worker.

## Resultados

- `pytest -q` para oito arquivos de dashboard e dois de regressão matching: `61 passed`
  em `13.89s`.
- Ruff nos arquivos do pacote: `All checks passed!`.
- `git diff --check` limitado ao pacote: sem erro de whitespace.

Os avisos do pytest foram deprecações já existentes de `TestClient` e cache não gravável
no bind mount de testes. Nenhuma credencial, Clerk real, banco operacional, deploy ou
aceite hospedado foi usado.

## Cobertura observada

- `test_tenancy.py` compara assessments, applications e overview entre owners A/B e
  confirma que o resumo de membro não expõe diagnósticos operacionais.
- `test_saved_searches.py` cobre UUID estrangeiro para rename/open/delete e confirma
  preservação da linha de A; o teste direto de `new_count` confirma o repasse de cada
  owner sintético para a query Inbox.
- `test_inbox_pointer.py` aceita a lookup necessária para ownership, mas rejeita plano
  que ordene ou faça ranking do histórico de `match_assessment`.
