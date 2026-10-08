# F53-04 — Terraform, rede e VM

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-02, F53-03.

## Objetivo e estado atual

Descrever uma infraestrutura OCI mínima, revisável e reversível: A1 ARM, rede,
regras de entrada, boot de 50 GB e bucket privado de backup. Não existe Terraform OCI nem VM deste
serviço no repositório atual.

## Implementação futura

1. Criar, após F53-03, `infra/terraform/oci/` com `providers.tf`, `versions.tf`,
   `variables.tf`, `network.tf`, `compute.tf`, `storage.tf`, `iam.tf`, `outputs.tf` e exemplo
   de variável sem segredo. Fixar versões e validar formato antes de plan.
2. Declarar compartment, VCN, subnet, NSG, instância A1 e bucket privado de
   backup no mesmo state/plan. O bucket não recebe acesso público ou segredo em
   output; F53-14 só o usa depois do Apply aprovado. Declarar A1 de 2 OCPUs/12
   GB, iniciar boot em 50 GB e não instalar PostgreSQL.
3. Permitir apenas 80/443 publicamente e 22 do `<CIDR_ADMIN>`; bloquear banco,
   Redis, API interna e portas de containers da Internet.
4. Gerar chave SSH fora de Terraform e informar só chave pública. Nunca usar
   senha, chave privada, URL Neon ou segredo Clerk em `cloud-init`.
5. Executar `terraform fmt -check` e `terraform validate` localmente ou na CI
   antes de empacotar o diretório. Criar então job **Plan** no Resource Manager;
   ele usa a stack/state/lock e não substitui format/validate locais. Revisar
   criação, região, shape, CIDRs, disco e custo no plano gerenciado.
6. Aplicar apenas em piloto aprovado; anotar OCID mascarado, IP mascarado, job
   e horário. Capacidade ARM indisponível é gate, não convite para escolher VM
   paga ou outra região.

## Resultado e falhas

Espera-se um plan que só crie recursos previstos. Diferença de region, shape,
regra `0.0.0.0/0` em SSH ou disco acima de 50 GB exige corrigir código e gerar
novo plan. `Out of host capacity` exige aguardar ou replanejar com o dono; não
refazer indefinidamente nem criar carga artificial contra reclaim de inatividade.

## Aceite

| ID | Positivo | Negativo e prova operacional |
| --- | --- | --- |
| AC01 | plan cria A1 2/12 e boot 50 GB | plan com shape/disco diverso falha revisão |
| AC02 | somente 80/443 públicos e SSH no CIDR | varredura externa não encontra 5432/6379 |
| AC03 | state não mostra segredo | revisão redigida do plan e inputs |
| AC04 | VM responde por SSH administrativo | evidência registra chave pública e acesso, nunca chave privada |

Arquivar plan redigido, matriz de portas e identificação de job. Não usar
`terraform apply` local fora da trilha de state/lock de F53-03.

## HCL, plan e inspeção

F53-04 cria HCL versionado para VCN, subnet, internet gateway, route table,
NSG, boot volume e instância A1. Não use console para criar recursos paralelos:
o Resource Manager deve aplicar a mesma fonte revisada.

1. Defina variáveis públicas para compartment, região, CIDR administrativo e
   imagem ARM; mantenha segredo fora de `tfvars` e outputs.
2. Rode `terraform fmt -check -recursive`, `init -backend=false` e `validate`
   no PowerShell após F53-03 criar o root.
3. Crie Plan no Resource Manager, revise cada resource e confirme que não há
   regra 22 aberta a `0.0.0.0/0`, porta 5432 ou endereço de banco local.
4. Aplique uma vez na janela e confira no console IP, NSG, volume de 50 GB,
   arquitetura ARM e quota restante.
5. Conecte por SSH com chave pública e confirme que nenhuma senha ou secret foi
   colocado em metadata/user-data.

Teste negativo: origem fora do CIDR não alcança SSH; Internet não alcança porta
da API interna nem PostgreSQL. Se plan pedir recurso pago ou shape diferente,
cancele antes de Apply e replaneje.

## Inputs públicos, HCL futuro e plan legível

O exemplo pertence ao futuro `infra/terraform/oci/`. Não o execute nem crie
arquivo até F53-03 aprovar state, IAM e a revisão do root. Ele expõe valores que
devem aparecer no plan, sem chave privada ou DSN.

```hcl
# terraform.tfvars.example — valores ilustrativos, não credenciais
compartment_id      = "<ocid-do-compartment-piloto>"
availability_domain = "<AD-da-regiao>"
vcn_cidr            = "10.53.0.0/16"
public_subnet_cidr   = "10.53.10.0/24"
admin_cidr           = "203.0.113.0/24"
instance_shape       = "VM.Standard.A1.Flex"
shape_ocpus          = 2
shape_memory_in_gbs  = 12
boot_volume_size_gbs = 50
```

```hcl
# Recurso futuro de NSG: SSH só do CIDR administrativo.
resource "oci_core_network_security_group_security_rule" "ssh_admin" {
  network_security_group_id = oci_core_network_security_group.api.id
  direction                 = "INGRESS"
  source_type               = "CIDR_BLOCK"
  source                    = var.admin_cidr
  protocol                  = "6" # TCP
  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}
```

No PowerShell, depois de criar e revisar o diretório, rode apenas checks locais
sem backend e sem Apply:

```powershell
Set-Location infra/terraform/oci
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

1. Confirme que `fmt` não altera arquivos e `validate` não pede credencial.
2. No Resource Manager, gere Plan e confira `10.53.0.0/16`, subnet `/24`, A1,
   `2`, `12` e `50` no diff antes de qualquer Apply.
3. Confirme que só 80/443 têm source público; 22 deve mostrar o `admin_cidr`.
4. Registre região, CIDRs, shape e custo/limite como saída redigida. Pare se o
   plan criar serviço pago, abrir 22 ao mundo ou trocar o shape.

`terraform validate` verde não prova capacidade A1 ou autorização OCI; o Plan
gerenciado e inspeção de console fornecem essas provas.

## Rollback e gate

Se piloto não atingir AC01–AC04, destruir somente os recursos do piloto pelo
mesmo stack, depois de confirmar targets no plan de destroy. F53-05 e F53-09
exigem esta prova; DNS continua sem apontamento até então.
