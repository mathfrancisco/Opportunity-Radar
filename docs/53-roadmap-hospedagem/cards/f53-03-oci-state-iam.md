# F53-03 — state OCI e IAM mínimo

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-01.

## Objetivo e estado conhecido

Preparar state com lock e uma identidade de operação de menor privilégio antes
de Terraform criar rede ou VM. Nenhum diretório `infra/terraform/oci/`, stack
Resource Manager ou principal OCI foi confirmado como implementado hoje.

## Estrutura futura e procedimento

Após aprovação, o root futuro é `infra/terraform/oci/`, com state gerenciado
por OCI Resource Manager, não AWS S3. O bootstrap é deliberadamente manual
porque Terraform não pode gerir com segurança o próprio acesso inicial.

1. Criar manualmente compartment, grupo ou principal de operação e políticas
   mínimas para rede, compute, bucket de backup e Resource Manager daquele
   compartment; separar leitura de state de administração de tenancy.
2. Criar uma stack Resource Manager apontando para o diretório versionado e
   confirmar state gerenciado e lock de uma execução por stack no console.
3. Revisar que variável sensível não aparece em input, output, plano, state,
   user-data ou log. Usar cofre/provedor em tempo de execução no futuro.
4. Executar somente um plan de ensaio aprovado; arquivar ID de job e sumário
   redigido, nunca o state bruto.
5. Tentar segundo plan concorrente, confirmar bloqueio/lock e aguardar o job
   original terminar ou ser cancelado de forma explícita.
6. Parar se a conta não oferecer o comportamento de state/lock esperado ou se
   a política precisar de permissão ampla de tenancy.

## Resultado e recuperação

O resultado esperado é uma stack com state protegido e operador limitado ao
compartment. Se um job falhar, cancelar o job, revisar eventos e só então
liberar lock conforme procedimento OCI; não apagar state para "destravar".
Se o backend não for viável, registrar alternativa local criptografada e sua
limitação de ausência de lock colaborativo antes de mudar a arquitetura.

## Aceite, testes e provas

| ID | Teste | Evidência redigida |
| --- | --- | --- |
| AC01 | principal limitado não administra outro compartment | política revisada e teste de acesso negado |
| AC02 | dois jobs concorrentes não escrevem state simultaneamente | IDs e estado de lock, sem state |
| AC03 | plan não contém segredo | busca manual do artefato com valores mascarados |
| AC04 | state permanece recuperável após job cancelado | execução controlada e procedimento registrado |

Falhas típicas: `NotAuthorizedOrNotFound` indica política/compartment incorreto;
lock ativo exige identificar job, não forçar concorrência. Arquivar política,
IDs mascarados e data em `evidencias/` somente após execução.

## Execução local e console Resource Manager

Depois que o root Terraform existir, execute no PowerShell dentro dele:

```powershell
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

Esses comandos validam fonte; não criam recursos nem substituem state remoto.
No OCI, use **Developer Services > Resource Manager > Stacks** para criar stack
do repositório revisado. Rode **Plan** primeiro, reveja diff e variáveis
mascaradas, depois use **Apply** no mesmo stack somente em janela autorizada.
Registre job ID, commit e resultado, não o state.

Teste negativo: principal do piloto tenta alterar compartment vizinho e recebe
negação. Se o plan exigir permissão não justificada, interrompa e revise IAM.

## Política mínima e opções da stack

Escreva políticas OCI no console só após substituir placeholders e revisar o
compartment. O bloco é modelo de revisão, não política pronta:

```text
Allow group <GRUPO_INFRA_PILOTO> to manage virtual-network-family in compartment <COMPARTMENT_PILOTO>
Allow group <GRUPO_INFRA_PILOTO> to manage instance-family in compartment <COMPARTMENT_PILOTO>
Allow group <GRUPO_INFRA_PILOTO> to manage volume-family in compartment <COMPARTMENT_PILOTO>
Allow group <GRUPO_INFRA_PILOTO> to manage object-family in compartment <COMPARTMENT_PILOTO>
Allow group <GRUPO_INFRA_PILOTO> to manage resource-manager-family in compartment <COMPARTMENT_PILOTO>
```

1. Confirme que cada nome é do compartment piloto, nunca tenancy root.
2. Remova IAM administrativo, recursos de banco e permissões fora do state.
3. Em **Developer Services > Resource Manager > Stacks**, escolha **Create
   stack**, informe compartment e diretório Terraform, sem secret em variável.
4. Em **Jobs**, crie **Plan**, revise inputs públicos e resumo redigido.
5. Crie **Apply** só a partir do plan aprovado e nunca concorra com Apply local.

O resultado esperado mostra um job por vez e state gerenciado. `NotAuthorizedOrNotFound`
indica escopo errado; `manage all-resources` não é correção aceitável.

## Rollback e gate

### Handoff operacional

Anexe ao próximo card somente o commit do root, ID de plan mascarado, política
revisada e resultado do teste de negação. Não compartilhe state, chave de API ou
arquivo de variáveis. A revisão deve confirmar que não há job ativo antes de
F53-04 iniciar novo plan.

Remover apenas principal, política e stack criados para o piloto depois de
preservar a evidência, por console e com aprovação do dono. F53-04 exige os
quatro ACs; não há apply de infraestrutura antes disso.
