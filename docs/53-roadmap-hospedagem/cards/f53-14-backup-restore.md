# F53-14 — backup e restore

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-04, F53-06.

## Objetivo

Produzir dump consistente, criptografado fora da VM e restaurá-lo em destino
isolado. Backup existe quando o restore compara manifesto, checksum, migração,
extensões, contagens e relações; produzir arquivo não basta.

## Procedimento futuro

1. Depois de F53-04 aplicar Terraform/Resource Manager, preparar o bucket OCI
   privado no compartment de backup explicitado no state e nos outputs, com IAM
   mínimo,
   criptografia e limite inicial de 20 GB/50 mil requests; guardar cópia
   independente criptografada sob controle do dono, fora da conta operacional.
2. Antes de executar em host cloud, adaptar os scripts para que credenciais não
   apareçam em argv de `pg_dump`/`pg_restore`, por exemplo com `PGPASSFILE` ou
   `PGSERVICE`. Provar por lista de processos e logs redigidos; até isso existir,
   não rodar backup/restore naquele host.
3. Executar o comando futuro com retenção desativada no primeiro ciclo:
   `python scripts/backup.py --output-dir <DIRETORIO_SEGURO> --prune-days 0`.
   Não informar `--label`: o timestamp UTC padrão evita substituir dump e
   manifesto existentes. O script usa snapshot e produz dump, manifesto e SHA-256.
4. Criptografar a cópia independente **antes** do upload, transferir por canal
   aprovado e verificar checksum no destino. Só aplicar retenção após restore
   válido; preservar a geração anterior se upload ou restore falhar.
5. Em servidor/compartment isolado, com privilégios `CREATEDB` e URL base que
   não aponte para produção, executar
   `python scripts/restore_check.py --dump <DUMP> --backup-dir <DIRETORIO>`.
   Não usar `--allow-missing-manifest`: ele reduz prova a legibilidade.
6. Deixar o scratch apenas para diagnóstico com `--keep` aprovado; de outro
   modo confirmar que o script o remove. `_test` no nome não basta se o servidor
   é o mesmo de produção.
7. Testar dump corrompido, manifesto ausente e permissão `CREATEDB` negada.
   Cada um deve falhar antes de promover backup ou tocar produção.

## Aceite

| ID | Positivo | Negativo/operacional |
| --- | --- | --- |
| AC01 | dump tem manifesto/checksum e cópia externa | arquivo sem manifesto é rejeitado |
| AC02 | restore isolado compara revision, extensões e relações | checksum divergente falha |
| AC03 | scratch não toca produção e é removido | URL/servidor de produção bloqueia execução |
| AC04 | retenção ocorre após restore e cópia do dono | falha de cópia preserva geração anterior |

Arquivar somente hash, data, bytes, status, destino mascarado e relatório de
restore. Nunca versionar dump, manifesto com dados, chave de criptografia ou
URL. Executar exercício periódico com owner e prazo de recuperação.

## Rollback e gate

Não apagar a geração anterior até AC01–AC04. Para incidente, parar escritores,
restaurar primeiro em isolado, comparar e obter aprovação antes de qualquer
promoção. F53-13, F53-16, F53-17 e F53-18 exigem essa prova.

## Pré-flight, diagnóstico e política posterior

Antes do primeiro dump, confirmar que a adaptação de credenciais fora de argv
foi revisada, que o diretório não é versionado, há espaço para duas gerações e
que o alvo isolado não compartilha servidor com produção. O processo de teste
deve mostrar comando sem DSN/senha; qualquer exposição exige rotação e limpeza
do log antes de retomar.

Depois de AC01–AC04, propor retenção separadamente com `--prune-days <DIAS>` e
dry-run/revisão da geração que será removida. Falha de upload, criptografia,
checksum, `pg_dump`, `pg_restore`, permissão ou comparação preserva as cópias
existentes e abre incidente; nunca executar prune como recuperação de espaço.

O restore-check esperado cria scratch, confirma versão/contagens/extensões e o
remove. Se ele não remover, investigar e limpar apenas o nome de scratch
confirmado no destino isolado. Essa limpeza não é autorização para remover
banco, bucket ou snapshot de produção.

## Contrato operacional de credencial e cópia

Executar no host de backup, nunca em Pages ou runner público. Antes de adaptar
os scripts, criar PGPASSFILE temporário 0600 ou entrada PGSERVICE administrada
pelo cofre; validar com `ps` e logs redigidos que argv não contém URL, usuário
ou senha. A implementação futura deve passar esse mecanismo a pg_dump e
pg_restore; o código atual ainda monta DSN no argv e portanto não passa este
gate cloud.

Gerar dump sem prune e preservar o `.manifest.json` adjacente. Cifrar ambos
juntos, ou cifrar cada um com pares identificáveis, usando chave do dono fora da
VM; calcular SHA-256 do ciphertext e só então enviar ao bucket privado por
cliente OCI configurado fora do repositório. Registrar data, bytes, hash e
versão da chave, nunca chave nem caminho sensível. Baixar uma cópia para
diretório isolado, validar checksum, descriptografar com permissões restritas e
rodar restore-check sobre dump e manifesto adjacentes; limpar plaintext depois.
Upload com hash errado, perda de cópia, manifesto ausente ou DSN visível aborta
e preserva gerações anteriores.
