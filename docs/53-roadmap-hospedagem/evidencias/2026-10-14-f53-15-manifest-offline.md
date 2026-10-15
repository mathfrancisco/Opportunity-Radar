# F53-15 — contrato offline de manifest ARM64

Data: 2026-10-14 (UTC). Branch `test/f53-arm64-offline`.

## O que foi verificado

O contrato do validador `scripts/validate_cloud_images.py` (critério AC05:
"api, worker e proxy incluem linux/arm64") agora é exercitado em um step
não gated do job `Backend / lint and types`, "Validate offline cloud manifest
contracts". O step não depende do job `Publish` nem de
`TENANCY_OWNER_API_READY`, não tem `if:` nem `continue-on-error`.

Cobertura, com fixtures OCI sintéticas em `tests/fixtures/cloud_images/`
(índice multi-arch e índice somente amd64) e subprocesso real do validador:

- modo por papel (api, worker, proxy): aceita multi-arch, rejeita amd64-only;
- modo legado: aceita os três multi-arch; rejeita um papel amd64-only por vez
  nomeando o papel; rejeita manifest ausente;
- rejeita bytes alterados após o cálculo do digest e `windows/arm64`;
- resultado idêntico com `TENANCY_OWNER_API_READY` ausente e `"false"`.

## Limite da evidência

Contrato offline do validador verificado em CI não gated; manifests publicados
e runtime arm64 continuam externos. Esta evidência prova a lógica do validador
e a ligação no CI, não imagens publicadas. AC05 permanece aberto externamente.
