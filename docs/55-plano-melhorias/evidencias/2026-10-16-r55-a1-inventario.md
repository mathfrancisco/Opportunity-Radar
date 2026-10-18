# R55-A1 — inventário do banco local (16/10/2026)

Sem PII, sem segredos. Contagens exatas com `count(*)` (não estatística) no container `opportunity-radar-dev-postgres-1`, aberto com `default_transaction_read_only=on`. Revisão Alembic local: `20261006_0068` (antes da tenancy `0069`).

## Contagem por tabela

| Tabela | Linhas |
| --- | ---: |
| `acquisition.host_budget_state` | 35 |
| `acquisition.payload_retention_event` | 0 |
| `acquisition.raw_item` | 91170 |
| `acquisition.raw_item_payload` | 91170 |
| `acquisition.source_alert_incident` | 3 |
| `acquisition.source_checkpoint` | 163 |
| `acquisition.source_definition` | 442 |
| `acquisition.source_execution_claim` | 425 |
| `acquisition.source_probe` | 443 |
| `acquisition.source_run` | 12409 |
| `acquisition.tavily_extract_cache` | 2937 |
| `company_radar.company` | 522 |
| `company_radar.company_alias` | 11 |
| `company_radar.company_import_batch` | 8 |
| `company_radar.company_import_issue` | 33 |
| `company_radar.company_source` | 802 |
| `company_radar.company_source_revision` | 334 |
| `company_radar.company_startup_evidence` | 0 |
| `company_radar.discovery_attempt` | 0 |
| `crm.application_process` | 0 |
| `crm.stage_history` | 0 |
| `dashboard.saved_search` | 0 |
| `matching.current_assessment` | 52539 |
| `matching.match_analysis` | 3209 |
| `matching.match_analysis_claim` | 0 |
| `matching.match_assessment` | 135153 |
| `matching.match_factor` | 1081224 |
| `opportunities.duplicate_candidate` | 196 |
| `opportunities.field_suggestion` | 39 |
| `opportunities.normalization_result` | 93893 |
| `opportunities.opportunity` | 36195 |
| `opportunities.opportunity_compensation` | 11203 |
| `opportunities.opportunity_embedding` | 0 |
| `opportunities.opportunity_embedding_failure` | 0 |
| `opportunities.opportunity_skill` | 45400 |
| `opportunities.relevance_mark` | 172 |
| `opportunities.source_occurrence` | 39936 |
| `opportunities.source_occurrence_observation` | 602830 |
| `platform.ai_call_record` | 1171 |
| `platform.ai_operation_record` | 2968 |
| `platform.ai_quota_usage` | 1115 |
| `platform.ai_suggestion_defer` | 6 |
| `platform.worker_job_state` | 8 |
| `platform.worker_pass_history` | 1029 |
| `profile.career_profile` | 1 |
| `profile.employment_preference` | 2 |
| `profile.experience` | 4 |
| `profile.profile_skill` | 22 |
| `profile.profile_version` | 2 |
| `profile.project` | 0 |
| `profile.skill` | 21 |
| `public.alembic_version` | 1 |

## Recortes relevantes para a migração
- Fontes por tipo: inhire 257, ashby 66, greenhouse 61, workday 19, lever 15, workable 11, teamtailor 7, manual 2, factorial 2, remotive 1, hacker_news 1 (442).
- Estado das fontes (enabled, terms_reviewed, collector_local_tested, evidence_status): 434 habilitadas, revisadas, testadas e `confirmed`; 1 habilitada e `confirmed` sem termos revisados; 3 revisadas e testadas, desabilitadas; 1 testada e `confirmed`, desabilitada; 3 `unverified`.
- 408 fontes têm `company_source_id`; 34 não têm.
- `company_source.verification_status`: ats_identified 400, careers_confirmed 329, api_json_confirmed 19, backlog 52, unverified 2.
- Dado mais novo: `raw_item.fetched_at` e `opportunity.first_seen_at` máximos em 2026-10-08 20:06 UTC. Em 2026-10-16 há 0 raw items dos últimos 7 dias, logo o escopo de "vagas" da migração dá 0 linhas na prática.
- Tabelas de `company_radar` e `profile` que a estatística mostrava vazias: `company_radar.company` tem 522 e `company_source` 802; `profile.career_profile` tem 1; `company_startup_evidence` e `discovery_attempt` são realmente 0.
- Tabelas com `owner_sub` (tenancy 0069): somente career_profile, application_process, saved_search, relevance_mark, match_assessment. Nenhuma tabela do catálogo tem a coluna.

## Escopo de A2 (decisão do dono)
Migra: company, company_alias, company_source, company_source_revision, company_startup_evidence, source_definition, source_probe e raw_item/raw_item_payload dos últimos 7 dias. Não migra: oportunidades, avaliações, perfil, CRM, marcas, telemetria de IA, checkpoints, claims, budget de host, incidentes, cache Tavily, lotes de importação.
