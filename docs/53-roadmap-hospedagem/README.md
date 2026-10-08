# Roadmap 53 — hospedagem econômica e recuperável

**Estado: planejado; nenhum card está implementado ou aceito em 6 de outubro de
2026.** Este índice decompõe o [plano de hospedagem](../53-plano-hospedagem-cloudflare-oracle-neon-clerk.md).
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
