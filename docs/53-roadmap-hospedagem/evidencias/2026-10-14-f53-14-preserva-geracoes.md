# F53-14 — preservação de gerações locais

Data: 2026-10-14. Escopo: reparo local de `scripts/backup.py` e seus testes.
Nenhum banco operacional, dump real, restore, cópia cifrada, upload ou serviço
externo foi usado.

## Comportamento verificado localmente

- `--label` aceita somente nome simples antes de ler a configuração de banco.
- A execução cria exclusivamente `<nome>.dump.lock`; dump, manifesto e os dois
  temporários existentes recusam a geração sem sobrescrever bytes anteriores.
- Arquivo regular e symlink pendente para cada um desses quatro artefatos são
  recusados antes de `database_url`; o teste preserva o symlink pendente.
- Um lock existente, inclusive abandonado, falha fechado. A limpeza remove só
  um lock cujo token ainda pertence à própria execução.
- Uma execução cooperativa concorrente com o mesmo nome falha; uma execução
  normal ou uma falha simulada libera sua própria reserva.

## Check final

O comando abaixo usou imagem já existente, rede desabilitada e montagem de
código somente leitura:

```text
docker run --rm --network none -v 'C:\Users\mathf\Documents\GitHub\Opportunity-Radar\.worktrees\f53-14-preserve:/app:ro' -w /app -e PYTHONPATH=/app/src -e RUFF_CACHE_DIR=/tmp/ruff-cache opportunity-radar-dev-api:latest sh -c 'pytest -q -p no:cacheprovider tests/backend/test_backup.py tests/backend/test_restore_check_safety.py && ruff check --no-cache scripts/backup.py tests/backend/test_backup.py && ruff format --check --no-cache scripts/backup.py tests/backend/test_backup.py && mypy --cache-dir=/tmp/mypy scripts/backup.py'
........................................s.ss..........                   [100%]
51 passed, 3 skipped in 1.61s
All checks passed!
2 files already formatted
Success: no issues found in 1 source file
exit 0
```

Confirmação independente final do coordenador, com a mesma imagem, montagem
somente leitura, rede desabilitada e sem criar bytecode no código montado:

```text
docker run --rm --network none -v 'C:\Users\mathf\Documents\GitHub\Opportunity-Radar\.worktrees\f53-14-preserve:/app:ro' -w /app -e PYTHONPATH=/app/src -e PYTHONDONTWRITEBYTECODE=1 -e RUFF_CACHE_DIR=/tmp/ruff-cache opportunity-radar-dev-api:latest sh -c 'pytest -q -p no:cacheprovider tests/backend/test_backup.py tests/backend/test_restore_check_safety.py && ruff check --no-cache scripts/backup.py tests/backend/test_backup.py && ruff format --check --no-cache scripts/backup.py tests/backend/test_backup.py && mypy --cache-dir=/tmp/mypy scripts/backup.py'
51 passed, 3 skipped in 1.63s
All checks passed!
2 files already formatted
Success: no issues found in 1 source file
exit 0
```

```text
git -C .worktrees/f53-14-preserve diff --check
exit 0
```

## Formatação de base

Antes deste reparo, os conteúdos indexados em `HEAD` já retornavam `exit 1` em
`ruff format --check --diff`: duas diferenças em `scripts/backup.py` (a
mensagem de `pg_dump` e a quebra da mensagem de retenção) e uma em
`tests/backend/test_backup.py` (a compreensão de conjunto). O índice armazena
os dois arquivos em LF, mas as cópias de trabalho estavam em CRLF/mista; a nova
edição deixou linhas LF adicionais em `backup.py`.

Foi executado o formatter offline apenas nos arquivos deste slice:

```text
docker run --rm --network none -v 'C:\Users\mathf\Documents\GitHub\Opportunity-Radar\.worktrees\f53-14-preserve:/app' -w /app -e RUFF_CACHE_DIR=/tmp/ruff-cache opportunity-radar-dev-api:latest ruff format scripts/backup.py tests/backend/test_backup.py
2 files reformatted
exit 0
```

O check final confirma a formatação; `.gitattributes` não foi modificado.

## Recuperação e rollback

Um `.dump.lock` abandonado é uma interrupção segura, não autorização para
sobrescrever ou apagar geração. Conservar dump, manifesto, temporários e lock
como evidência; sem prova de que o processo anterior parou, usar outro
`--label` ou aguardar intervenção operacional aprovada. O script não remove
automaticamente lock existente.

Se este reparo precisar de rollback, reverter somente o código e preservar
todas as gerações já escritas. Não usar rollback para apagar dump, manifesto,
temporários ou lock. Recuperar uma geração exige restore isolado e autorização
operacional; esta evidência não prova backup externo, criptografia, restore
real ou recuperação em banco Neon.

## Limitações

Os três testes marcados como integração foram pulados porque exigem banco. O
acesso Docker sem escalonamento também falhou antes de criar container com
`permission denied while trying to connect to the docker API at
npipe:////./pipe/dockerDesktopLinuxEngine` e `exit 1`; o check final usou
acesso Docker autorizado, ainda sem rede. Nenhum resultado local substitui
prova operacional de AC01--AC04 de F53-14.
