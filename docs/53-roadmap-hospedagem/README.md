# Roadmap 53 — hospedagem econômica e recuperável

**Estado: piloto online desde 16 de outubro de 2026; ver [Estado em 2026-10-16](#estado-em-2026-10-16) (a tabela de 14/10 fica como histórico).** Este índice decompõe o [plano de hospedagem](../53-plano-hospedagem-cloudflare-oracle-neon-clerk.md).
Uma ação descrita aqui só começa após o respectivo gate; um plano não é prova de
deploy, custo, segurança, backup ou recuperação.

| Ordem | Card | Prioridade | Dependências | Saída verificável |
| --- | --- | --- | --- | --- |
| 1 | [F53-01](cards/f53-01-inventario-orcamento-baseline.md) | P0 | — | orçamento, inventário e baseline redigidos |
| 2 | [F53-02](cards/f53-02-contas-dominio-dns.md) | P0 | F53-01 | propriedade, domínio e DNS confirmados |
| 3 | [F53-03](cards/f53-03-oci-state-iam.md) | P0 | F53-01 | state gerenciado e IAM mínimo revisados |
| 4 | [F53-04](cards/f53-04-terraform-rede-vm.md) | P0 | F53-02, F53-03 | plano OCI revisado, sem apply automático |
| 5 | [F53-05](cards/f53-05-imagens-compose-arm.md) | P0 | F53-04 | imagens ARM e Compose separados provados |
| 6 | [F53-06](cards/f53-06-neon-compatibilidade-migracao.md) | P0 | F53-01 | compatibilidade Neon e restore seco isolado |
| 7 | [F53-07](cards/f53-07-clerk-autorizacao-api.md) | P0 | F53-02 | API valida JWT e dono imutável |
| 8 | [F53-08](cards/f53-08-clerk-pages-frontend.md) | P1 | F53-02, F53-07 | Pages e login de piloto confirmados |
| 9 | [F53-09](cards/f53-09-tls-cors-rede.md) | P0 | F53-04, F53-05, F53-07 | TLS, CORS e exposição mínima provados |
| 10 | [F53-10](cards/f53-10-pipeline-finito.md) | P0 | F53-05, F53-06 | pipeline finito com claim e deadline |
| 11 | [F53-11](cards/f53-11-jobs-timers.md) | P1 | F53-10 | timers observáveis, sem worker contínuo |
| 12 | [F53-12](cards/f53-12-economia-ram-cpu-conexoes.md) | P0 | F53-05, F53-06, F53-10 | limites derivados de medições |
| 13 | [F53-14](cards/f53-14-backup-restore.md) | P0 | F53-04, F53-06 | backup externo e restore isolado provados |
| 14 | [F53-13](cards/f53-13-economia-storage-retencao.md) | P1 | F53-06, F53-14 | retenção segura e custo medido |
| 15 | [F53-15](cards/f53-15-ci-testes-isolados.md) | P0 | F53-05, F53-06, F53-07 | CI isolado e bloqueios negativos |
| 16 | [F53-16](cards/f53-16-aceite-pos-deploy.md) | P0 | F53-08, F53-09, F53-11, F53-12, F53-14, F53-15 | piloto em fixture aceito |
| 17 | [F53-17](cards/f53-17-monitoramento-incidentes.md) | P0 | F53-09, F53-11, F53-14 | alertas e resposta exercitados |
| 18 | [F53-18](cards/f53-18-cutover-rollback-recuperacao.md) | P0 | F53-13, F53-16, F53-17 | cutover reversível ou recuperação provada |

## Caminho crítico e definição de pronto

Consulte também o [inventário de variáveis e runbooks](variaveis-e-runbooks.md)
antes de configurar GitHub, Cloudflare, Clerk, Neon ou a VM OCI.

O caminho crítico é F53-01 → F53-02/F53-03 → F53-04 → F53-05 → F53-09,
F53-06 → F53-14, F53-07 → F53-15, F53-10 → F53-11 → F53-16 → F53-17 →
F53-18. Autorização antes de expor a API, TLS antes de dados pessoais, testes
isolados antes de deploy e backup restaurável antes de retenção ou cutover são
gates P0. F53-16 usa somente fixture; F53-18 é a primeira janela para dados
reais.

Cada card só fica **concluído** com: alteração revisada, teste positivo e
negativo aplicável, prova operacional datada, artefato redigido e rollback
testado. Saída de comando, plano Terraform, captura de console ou painel sem
segredos é evidência; intenção, checklist marcado ou execução sem artefato não é.

## Limites comuns

- Não criar recursos, contas, domínio, chaves, commits ou deploys enquanto este
  roadmap é escrito.
- Usar placeholders como `<DOMINIO>`, `<NEON_URL>` e `<CLERK_ISSUER>`; nunca
  colocar credenciais em Markdown, `.tfvars`, state, imagem ou log.
- Registrar evidências em `docs/53-roadmap-hospedagem/evidencias/` somente após
  a implementação. O diretório ainda não existe neste plano.
- Consultar o runbook para decisões de produto e fontes oficiais. Cada card
  abaixo acrescenta procedimento e aceitação, não muda aquele contrato.

## Estado em 2026-10-14

"Código local pronto" não é "concluído": a definição acima exige prova operacional datada e rollback testado, que ainda não existem para nenhum card.

| Card | Estado | Critério | Evidência |
| --- | --- | --- | --- |
| F53-01 | bloqueado externo (responsáveis, teto/moeda e leitura de painéis) | orçamento, inventário e baseline redigidos | [f53-01-baseline-2026-10-08](evidencias/f53-01-baseline-2026-10-08.md) |
| F53-02 | bloqueado externo | contas de registrar, Cloudflare e Clerk ainda não criadas | — |
| F53-03 | bloqueado externo | state gerenciado e IAM mínimo revisados | [2026-10-09-f53-03-04-terraform-root](evidencias/2026-10-09-f53-03-04-terraform-root.md); [2026-10-14-f53-03-04-terraform-static](evidencias/2026-10-14-f53-03-04-terraform-static.md) |
| F53-04 | em andamento (validação estática local; plan/apply/SSH externos) | shape A1.Flex, ingress 80/443 e SSH só no `admin_cidr` | [2026-10-14-f53-03-04-terraform-static](evidencias/2026-10-14-f53-03-04-terraform-static.md); [2026-10-14-f53-04-08-contratos-locais](evidencias/2026-10-14-f53-04-08-contratos-locais.md) |
| F53-05 | em andamento (publish arm64 por digest pronto; publicação bloqueada por `TENANCY_OWNER_API_READY`, decisão do dono) | imagens arm64 publicadas por digest | [2026-10-14-f53-15-publish-arm64](evidencias/2026-10-14-f53-15-publish-arm64.md) |
| F53-06 | em andamento (timeout/pre_ping/restore_check local; Neon real externo; projeção local implementada; consumo real, evidência de storage, compatibilidade e comportamento ocioso continuam pendentes) | conexão e restore contra Neon real; código/testes locais: `src/opportunity_radar/platform/database.py` (`pool_pre_ping`, `statement_timeout`), `src/opportunity_radar/platform/config.py`, `tests/backend/platform/test_statement_timeout.py` | [2026-10-09-f53-14-local-backup-hardening](evidencias/2026-10-09-f53-14-local-backup-hardening.md); [f53-01-baseline-2026-10-08](evidencias/f53-01-baseline-2026-10-08.md); [2026-10-14-f53-06-12-projecao-offline](evidencias/2026-10-14-f53-06-12-projecao-offline.md) |
| F53-07 | código local pronto, aceite operacional pendente (chaves Clerk de produção) | validação de token com chaves de produção | [2026-10-14-f53-07-nbf-aud](evidencias/2026-10-14-f53-07-nbf-aud.md); [2026-10-09-owner-route-auth](evidencias/2026-10-09-owner-route-auth.md) |
| F53-08 | código local pronto, aceite operacional pendente (Pages/domínio/sessão real) | sessão real em Pages com domínio | [2026-10-14-f53-08-session](evidencias/2026-10-14-f53-08-session.md); [2026-10-14-f53-04-08-contratos-locais](evidencias/2026-10-14-f53-04-08-contratos-locais.md) |
| F53-09 | código local pronto (contratos de CORS, health e proxy testados), aceite operacional pendente (TLS, domínio e scan externo) | TLS, CORS e exposição mínima provados | [2026-10-09-compose-cloud-cors](evidencias/2026-10-09-compose-cloud-cors.md) |
| F53-10 | código local pronto, aceite operacional pendente (piloto em VM/Neon); AC05 mergeado em #87 (5163c3f) | piloto na VM com Neon | [2026-10-09-f53-10-pipeline-local](evidencias/2026-10-09-f53-10-pipeline-local.md); [2026-10-14-f53-10-ac05-run-parcial](evidencias/2026-10-14-f53-10-ac05-run-parcial.md) |
| F53-11 | código local pronto, aceite operacional pendente (execução na VM) | unit systemd executada na VM | [2026-10-14-f53-11-systemd](evidencias/2026-10-14-f53-11-systemd.md) |
| F53-12 | em andamento (projeção local implementada; consumo real, evidência de storage, compatibilidade e comportamento ocioso continuam pendentes) | limites de RAM/CPU/conexões derivados de medição e projeção Neon | [2026-10-14-f53-12-13-medicao-retencao](evidencias/2026-10-14-f53-12-13-medicao-retencao.md); [2026-10-14-f53-12-13-caminho-postgres](evidencias/2026-10-14-f53-12-13-caminho-postgres.md); [2026-10-14-f53-06-12-projecao-offline](evidencias/2026-10-14-f53-06-12-projecao-offline.md) |
| F53-13 | em andamento | retenção segura e storage medido | [2026-10-14-f53-12-13-caminho-postgres](evidencias/2026-10-14-f53-12-13-caminho-postgres.md) |
| F53-14 | em andamento (cópia externa cifrada e restore real; `restore_check` só aceita banco `*_test`) | backup cifrado externo e restore real | [2026-10-09-f53-14-local-backup-hardening](evidencias/2026-10-09-f53-14-local-backup-hardening.md) |
| F53-15 | código local pronto para AC01–AC04; AC05 em andamento (validação de manifest só roda no Publish com gate) | CI e testes isolados (AC01–AC05) | [2026-10-14-f53-15-publish-arm64](evidencias/2026-10-14-f53-15-publish-arm64.md) |
| F53-16 | bloqueado externo | piloto ainda não implantado | — |
| F53-17 | bloqueado externo | OCI Monitoring/Notifications ainda não configurados | — |
| F53-18 | bloqueado externo | cutover depende de decisão do dono | — |

Custos: **não medidos**.

## Estado em 2026-10-16

Piloto online: Worker `opportunity-radar.math-francisco2.workers.dev`, API na VM
OCI E5 Free Trial (sa-saopaulo-1), Neon movido para `aws-sa-east-1`, Clerk de
desenvolvimento. Evidências:
[2026-10-16-f53-piloto-online](evidencias/2026-10-16-f53-piloto-online.md) e
[2026-10-16-f53-fechamento-piloto](evidencias/2026-10-16-f53-fechamento-piloto.md).

| Card | Estado em 16/10 | Prova ou lacuna |
| --- | --- | --- |
| F53-04 | provado no piloto, com desvio | Plan da stack com `No changes`; o shape é E5 Free Trial, não A1 Always Free |
| F53-05 | provado | imagens multiarch publicadas por digest e implantadas |
| F53-06 | provado | dump/restore entre regiões Neon com contagens idênticas; compute ocioso suspenso |
| F53-07 | provado em Clerk dev | `/session` `is_owner=true`; `CLERK_AUDIENCE` vazio (token dev sem `aud`) |
| F53-08 | provado em workers.dev | login real e menu de dono; domínio próprio não usado |
| F53-09 | provado | TLS Let's Encrypt, preflight CORS 200 só para a origem do Worker |
| F53-10 | provado | coleta de 225 itens e janela finita sem falha após a correção de lease |
| F53-11 | AC01–AC04 provados; AC05 sem prova | não há alerta de janela perdida |
| F53-12 | medido | projeção de 18,4 CU-h/mês de 80; VM com 762 MiB usados |
| F53-13 | parcial | storage medido (34,7 MB); retenção real não exercitada |
| F53-14 | provado | cópia cifrada no bucket, baixada e restaurada em banco isolado |
| F53-15 | provado | CI verde e Publish por digest no run 38920561681 |
| F53-16 | parcial | E2E do dono provado; segundo usuário sem prova |
| F53-17 | sem prova | alarme de teste desabilitado e e-mail removido a pedido do dono |
| F53-18 | rollback provado; cutover sem prova | troca de digest e volta em 13 s; dados pessoais reais ainda não migrados |

Custos: Neon, OCI e Cloudflare no plano gratuito ou nos créditos do trial, sem
cobrança. O consumo do Cloudflare não foi medido.
