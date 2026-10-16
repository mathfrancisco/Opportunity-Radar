# F53-14 — backup e restore

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-04, F53-06.

## Objetivo

Produzir dump consistente, criptografado fora da VM e restaurá-lo em destino
isolado. Backup existe quando o restore compara manifesto, checksum, migração,
extensões, contagens e relações; produzir arquivo não basta.

## Procedimento futuro

Pré-condição vinculante: usar somente recursos cuja cobrança total comprovada
seja zero. Não habilitar bucket, armazenamento, chaves, transferência,
requisições, restore, upgrade, assinatura ou overage cobrados. A existência de
free tier ou cota anunciada não é prova de custo zero; confirmar plano, saldo de
quota, billing e limite de cobrança antes de cada operação. Se não houver uma
opção gratuita já aprovada para cópia externa cifrada, manter AC01 bloqueado e
não substituir por serviço pago.

1. Depois de F53-04 aplicar Terraform/Resource Manager, preparar o bucket OCI
   privado no compartment de backup explicitado no state e nos outputs, com IAM
   mínimo e criptografia somente se quota, armazenamento, requests, chaves e
   transferência estiverem confirmados como custo zero sem overage; guardar
   cópia independente criptografada sob controle do dono, fora da conta
   operacional. Caso contrário, não criar o bucket nem avançar AC01.
2. Os scripts já evitam passar DSN/senha em argv: `pgpassfile_for_url` cria um
   `PGPASSFILE` temporário com permissão `0600`, e `postgres_tool_environment`
   remove configurações libpq herdadas antes de chamar `pg_dump`/`pg_restore`.
   [`test_restore_check_safety.py`](../../../tests/backend/test_restore_check_safety.py)
   cobre permissões/limpeza, ausência de DSN e senha em argv, isolamento e
   redaction. Antes do uso cloud, ainda verificar a lista de processos e logs
   redigidos no host real.
3. Executar o comando futuro com retenção desativada no primeiro ciclo:
   `python scripts/backup.py --output-dir <DIRETORIO_SEGURO> --prune-days 0`.
   Escolher uma geração UTC única no `--label` operacional (o timestamp padrão
   tem resolução de segundos e também pode colidir). `_reserve_generation`
   reserva o nome com criação exclusiva de `.lock` e recusa dump, manifesto,
   temporários ou symlinks já existentes; colisão falha sem sobrescrever. O
   script usa snapshot e produz dump, manifesto e SHA-256.
   Se `.lock` já existir, interromper e diagnosticar manualmente o processo e a
   geração antes de decidir qualquer recuperação. Nunca remover lock
   automaticamente nem presumir que é obsoleto.
4. Criptografar a cópia independente **antes** do upload, transferir por canal
   aprovado e verificar checksum no destino; verificar antes que cifragem,
   tráfego, armazenamento e requests custem zero e não habilitem overage. Só
   aplicar retenção após restore válido; preservar a geração anterior se upload
   ou restore falhar.
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

Antes do primeiro dump, confirmar que o uso de PGPASSFILE e a remoção das
variáveis libpq herdadas foram revisados, que o diretório não é versionado, há
espaço para duas gerações e que o alvo isolado não compartilha servidor com
produção. O teste local cobre segredo fora de argv; confirmar também o processo
e os logs redigidos no host real. Qualquer exposição exige rotação e limpeza do
log antes de retomar. Colisão de geração deve falhar fechada; lock existente
requer diagnóstico manual, sem remoção automática.

Depois de AC01–AC04, propor retenção separadamente com `--prune-days <DIAS>` e
dry-run/revisão da geração que será removida. Falha de upload, criptografia,
checksum, `pg_dump`, `pg_restore`, permissão ou comparação preserva as cópias
existentes e abre incidente; nunca executar prune como recuperação de espaço.

O restore-check esperado cria scratch, confirma versão/contagens/extensões e o
remove. Se ele não remover, investigar e limpar apenas o nome de scratch
confirmado no destino isolado. Essa limpeza não é autorização para remover
banco, bucket ou snapshot de produção.

## Contrato operacional de credencial e cópia

Executar no host de backup, nunca em Pages ou runner público. O código atual
usa PGPASSFILE temporário `0600` e limpa o ambiente libpq herdado antes de
executar as ferramentas; testes verificam que argv não contém URL/senha, que
as variáveis sensíveis não são herdadas e que o arquivo é removido. Confirmar
com `ps` e logs redigidos no host real antes do primeiro backup cloud; esse
teste operacional ainda está pendente.

Gerar dump sem prune e preservar o `.manifest.json` adjacente. Cifrar ambos
juntos, ou cifrar cada um com pares identificáveis, usando chave do dono fora da
VM; calcular SHA-256 do ciphertext e só então enviar ao bucket privado por
cliente OCI configurado fora do repositório. Registrar data, bytes, hash e
versão da chave, nunca chave nem caminho sensível. Baixar uma cópia para
diretório isolado, validar checksum, descriptografar com permissões restritas e
rodar restore-check sobre dump e manifesto adjacentes; limpar plaintext depois.
Upload com hash errado, perda de cópia, manifesto ausente ou credencial visível
aborta e preserva gerações anteriores. O lock reserva exclusivamente a
geração; não há remoção automática de lock abandonado, que exige diagnóstico
manual antes de qualquer limpeza. Provas locais de segurança não substituem o
backup, a cópia cifrada externa nem o restore operacional, todos ainda pendentes.
