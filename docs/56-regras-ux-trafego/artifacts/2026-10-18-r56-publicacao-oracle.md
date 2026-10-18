# Publicação Oracle R56 — evidência operacional

Data: 2026-10-18
Workflow: [#39171633133](https://github.com/mathfrancisco/Opportunity-Radar/actions/runs/39171633133)
Ref: `codex/r56-rules-ux-traffic`
Commit remoto confirmado: `79386260e724baa3a5dad4d8f34bfc2d267aa915`
PR: [#112](https://github.com/mathfrancisco/Opportunity-Radar/pull/112) (draft)

## Estado da publicação

O workflow foi disparado de forma autorizada com `publish=true` e terminou com `success` em
2026-10-18T22:37:12Z. Backend, frontend, lint/tipos, Terraform, E2E e os quatro jobs Publish
concluíram com sucesso.

| Imagem | Digest publicado | Manifesto conferido |
| --- | --- | --- |
| API | `sha256:c6019aa03a4107076ee02f6751d30c410142308a6fa32a44bdbc08a958400239` | `linux/amd64`, `linux/arm64` |
| Worker | `sha256:422940352bb7a8ff4d2f813c05c1072953a6071b4d5e9989d4b14c4827847961` | `linux/amd64`, `linux/arm64` |
| Proxy | `sha256:fc5b83b60f56e50f4fc0f80381e3bd660846971a04b4fa9003b39ae6daf7f902` | `linux/amd64`, `linux/arm64` |
| Frontend | `sha256:2ad7b7916566d1d0977ebfe0983093f70aa80c208d46fdb2cb8af8666fcb459d` | `linux/amd64` |

## Estado Oracle somente leitura

- A VM responde em `x86_64`.
- A API está saudável, com digest local pré-publicação
  `sha256:7442f2af124e6c3e11b35bdd8b377caaf82a104d7f9ffc09b78024bbcf9e109f`.
- O proxy está em execução, com digest local pré-publicação
  `sha256:f3fc3e0e4460c2d062357d39de7ea41715977af0a5ef1d24bff959e51cb19d5b`.
- O worker de execução finita não estava ativo; sua referência de rollback configurada é
  `sha256:872b8c1ef73d6a4f2f5b097a961a09127c03ae1d7755c196fc575a28f3d121b8`.
- `migrate_env_present=false`.
- O último container de migração observado terminou com exit 0. Seus logs confirmam Alembic em
  PostgreSQL, mas não registram a revisão 0072 nem 0073; a revisão do banco continua não
  confirmada.

Não foram executadas consultas de banco, deploy, criação de gatilho de migração, migração ou
alterações de ambiente. O procedimento de deploy permanece bloqueado até haver autorização
operacional explícita para qualquer migração necessária.

## Gate e rollback

`TENANCY_OWNER_API_READY` já estava aceito no GitHub em 2026-10-16, conforme
[evidência de tenancy](../../53-roadmap-hospedagem/evidencias/2026-10-15-f53-tenancy-local.md).
Nenhum gate foi alterado nesta etapa.

Se for necessário retorno após uma publicação posterior, o plano é restabelecer apenas imagens
por digest imutável, usando os digests pré-publicação acima como referência e sem downgrade
automático do banco. Não houve rollback executado.

## Pendências

1. Manter a VM inalterada até autorização explícita para qualquer migração 0073; a revisão live
   do banco não foi confirmada pelos logs disponíveis.
