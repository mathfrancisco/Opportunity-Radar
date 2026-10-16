# F53 — piloto online em 16/10 (workers.dev + OCI E5 + Neon + Clerk dev)

Evidência do piloto online publicado em 2026-10-16 (UTC). Os fatos abaixo foram
verificados pelo coordenador nessa data. O piloto roda com frontend no Cloudflare
Workers, API e worker em uma VM OCI, banco no Neon e autenticação no Clerk de
desenvolvimento. Esta evidência não fecha F53: as pendências listadas no fim
continuam abertas.

## Gate de tenancy

A revisão independente aceitou a faixa `ba27db0..c8a4cff`. A suíte preparada
terminou com 2662 testes aprovados. A variável `TENANCY_OWNER_API_READY=true`
foi definida somente depois de autorização explícita do dono.

## Publicação

A publicação foi feita pelo workflow `workflow_dispatch` com `publish=true`, na
branch `fix/f53-14-preserve`, no commit `0a64b5d`. A run `38837090283` terminou
com todos os jobs em `success` após um rerun.

A primeira tentativa falhou por flake em
`tests/backend/opportunities/test_suggestions.py`: um marcador numérico de 10
dígitos foi redigido como telefone. A correção foi feita no commit `37a98d3`.

## Imagens

As imagens foram publicadas por digest no GHCR, públicas, com manifest contendo
`linux/amd64` e `linux/arm64`:

- api: `sha256:9b2f970a04a564b924628bcb64e63678ef3df6f367189cd32e0c636a8b0b3761`
- worker: `sha256:9f9e1758fa093fb88689946ffc08b6250b4dc20f51cbdc0cf339f4a7f18c8168`
- proxy: `sha256:a4160ecbf7587d03da605829aa66db4ae4dcf2253bcf5cf662600562439d2aa0`

## VM OCI

A VM está na região `sa-saopaulo-1`, shape `VM.Standard.E5.Flex` com 1 OCPU e
8 GB de memória. Ela foi criada no Free Trial e é temporária. A migração para
A1 Always Free depende de capacidade do host, que já falhou em duas tentativas
registradas em `2026-10-15-f53-oci.md`.

Os arquivos de ambiente ficam em um diretório com permissão `0700`, com arquivos
`root:root` e modo `0600`. Nenhum ambiente de runtime contém
`OWNER_SUB_BACKFILL`. O arquivo `migrate.env` foi removido após a migração
terminar com sucesso.

## Banco Neon

O banco é Neon `free_v3`, PostgreSQL 18.6. A migração foi aplicada até
`20261008_0069`, com backfill aprovado. A conexão usa `sslmode=verify-full` e
um bundle de CA explícito.

Lições do ajuste:

- O DSN precisa do esquema `postgresql+psycopg`, porque `psycopg2` não existe na
  imagem.
- `sslrootcert=system` não funciona com a libpq do psycopg binário. O caminho
  que funcionou foi o bundle do sistema em `/etc/ssl/certs/ca-certificates.crt`.
- A query do DSN não deve ser percent-encodada, porque o Alembic lê a
  configuração com `configparser`.

## HTTPS

A API responde em `https://radar-api.163-176-11-135.sslip.io`. O certificado
Let's Encrypt é válido até 2027-01-14 e a verificação TLS passou.

Verificações feitas:

- HTTP porta 80 redireciona com 301 para HTTPS.
- `/health/live` retorna 200.
- `/session` sem token retorna 401.
- O preflight CORS para a origem `workers.dev` é permitido.
- Uma origem estranha recebe 400.

## Timers

Os timers `opportunity-radar-pipeline.timer` e `opportunity-radar-tls-renew.timer`
estão habilitados. A execução manual da janela do pipeline terminou com
`outcome success`, exit 0 e três estágios `completed` com 0 itens, porque o
banco é novo e ainda não tem fontes.

## Cloudflare Worker

O Worker `opportunity-radar` recebeu as variáveis de build
`VITE_CLERK_PUBLISHABLE_KEY` (chave `pk_test`) e `VITE_API_BASE_URL`. Um rebuild
manual de `main` (commit `02327963`, com frontend idêntico à branch) foi
publicado em `https://opportunity-radar.math-francisco2.workers.dev/`.

## Navegador

O dono fez login real no Clerk de desenvolvimento. Um `GET /session` com token
real retornou `is_owner=true`. As telas Visão geral e Perfil carregaram dados da
API sem erros no console.

## Backup

O `pg_dump` PostgreSQL 18 do Neon gerou 167872 bytes. O arquivo foi cifrado com
AES-256-GCM. A chave ficou fora da OCI. O checksum do ciphertext foi verificado.

Depois, o arquivo foi decifrado em diretório separado e o `restore_check`
estrito passou em PostgreSQL 18 com pgvector isolado, no banco `restore_test`.
As extensões `plpgsql`, `unaccent` e `vector` estão presentes.

## Pendências sem prova

Estes itens não têm prova ainda e impedem considerar F53 completa:

- Upload feito em 16/10: `f53-14/<label>.orbk` (174114 bytes) e `.orbk.sha256` no bucket privado, via instance principal com policy restrita a OBJECT_CREATE/OBJECT_INSPECT nesse bucket. A regra SSH foi trocada para o novo `/32` do dono direto no NSG (drift da stack: atualizar `admin_cidr`).
- Restore a partir da cópia baixada do bucket.
- Prova de reboot, timeout e alerta de janela perdida do timer (F53-11, AC01 a AC05).
- Medição de consumo e limites gratuitos ao longo do tempo.
- Ensaio de rollback para o digest anterior.
- `CLERK_AUDIENCE` não configurado. É opcional.
- Hardening `NoNewPrivileges` do serviço systemd. É opcional.

F53 não está completa.
