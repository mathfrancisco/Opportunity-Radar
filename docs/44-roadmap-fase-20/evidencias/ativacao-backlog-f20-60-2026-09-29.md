# F20-60 — Ativação das 3 fontes `activate` do backlog (2026-09-29)

Execução na `f20manual` (pilha manual), a partir da recomendação de
`careers-backlog-f20-60-2026-09-29.md` (DoorDash, Remotebase, Lemon.io). A pilha real
`opportunity-radar` não foi tocada. Nenhuma varredura sem filtro: `discover_ats.py` e
`enable_sources.py` **não** foram executados (não têm filtro por empresa); o caminho usado
foi um script curto dentro do container `api`, que reutiliza `enable_sources._probe`,
`enable_sources._homologation_audit` e `AcquisitionService.record_script_probe`, e grava
`CompanySource` + `SourceDefinitionModel` com a mesma forma das fontes F20-60 anteriores
(Grafana Labs, Devsu, Andela): `company_source` `api_json_confirmed`, método
`manual_probe_f20_60`, `external_key` = slug; `source_definition` prioridade 25,
`requests_per_second` 0,2, `homologation_audit`. Chave de configuração por ATS:
`board_token` (Greenhouse), `account_identifier` (Workable), `board_identifier` (Ashby).

## Confirmação de pertencimento (GET na API pública do ATS, 1 req/s)

O estado inicial das 3 empresas: `radar_status=backlog`, só `company_source` `careers`
`unverified`, nenhuma `source_definition`, nenhum `discovery_attempt`.

| Empresa | ATS / slug | Prova de pertencimento | Veredito |
| --- | --- | --- | --- |
| DoorDash | Greenhouse `doordashusa` | `GET https://boards-api.greenhouse.io/v1/boards/doordashusa` → `name: "DoorDash USA"`; `GET .../jobs` → 463 vagas, `company_name: "DoorDash USA"`, `absolute_url` em `job-boards.greenhouse.io/doordashusa/jobs/...` | Confirmado (nome oficial do board = empresa). Sem URL no domínio `doordash.com` nas respostas. |
| Remotebase | Workable `remotebase` | `GET https://apply.workable.com/api/v1/widget/accounts/remotebase?details=true` → `name: "Remotebase"`, 5 vagas, descrições citam RemoteBase; link de edição `remotebase.workable.com` | Confirmado por nome. Nenhuma URL `remotebase.com` nas respostas; o `company_source` `careers` original (`remotebase.com/careers`) segue `unverified`. |
| Lemon.io | Ashby `lemon-io` | `GET https://api.ashbyhq.com/posting-api/job-board/lemon-io` → 4 vagas; descrição "About Lemon.io (http://Lemon.io) ... talent marketplace"; `jobUrl` em `jobs.ashbyhq.com/lemon-io/...` | Confirmado (descrição se identifica com o domínio `lemon.io`). |

## Resultado por fonte

Probe (`max_items=1`) `PASSED` nas três; fonte habilitada (`enabled=true`,
`evidence_status=confirmed`, `terms_reviewed`, `collector_local_tested`) e empresa
`radar_status` `backlog` → `active`. Coleta única por fonte com
`collect.py --source-id <id> --correlation-id f20-60-backlog`.

| Empresa | source_id | Status | seen | persisted | skipped | invalid |
| --- | --- | --- | --- | --- | --- | --- |
| DoorDash | `95b33987-d008-42a4-85e8-b62eabee4797` | `SUCCEEDED` | 463 | 463 | 0 | 0 |
| Remotebase | `38b33510-f7d5-40b8-801b-302829234cb6` | `SUCCEEDED` | 5 | 5 | 0 | 0 |
| Lemon.io | `29d7a98e-1efd-4b8b-8c88-e701faadcc6f` | `SUCCEEDED` | 4 | 4 | 0 | 0 |

Habilitadas na `f20manual`: +3 (uma requisição HTTP por coleta, `retry_count` 0).

## Incertezas

- Pertencimento por nome/conteúdo do board; nenhuma resposta traz URL no domínio próprio
  da empresa para DoorDash e Remotebase. O risco é homônimo (o mesmo cuidado que o
  relatório de backlog registrou para `fullstack`, `terminal`, `tcs`). DoorDash e
  Lemon.io têm evidência forte (nome oficial do board; descrição com o domínio);
  Remotebase é a mais fraca.
- Lemon.io também tem BambooHR (`lemonio`, sem coletor); só o Ashby é coletado.
- O `company_source` `careers` original das 3 empresas continua `unverified`.
- Termos: fontes tratadas como API pública de ATS (mesma revisão de nível de coletor de
  Greenhouse, Workable e Ashby); termos individuais dos sites não foram lidos.
- Ativação na pilha real só depois de `2026-10-05T12:02Z`, com probe antes
  (`validacao-pendente.md` §4).
