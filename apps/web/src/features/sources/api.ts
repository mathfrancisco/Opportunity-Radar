import { apiUrl, failureFrom, requestFailure } from '../../lib/api'

export interface SourceHealth {
  sourceDefinitionId: string
  name: string
  sourceType: string
  enabled: boolean
  evidenceStatus: string
  termsReviewed: boolean
  collectorLocalTested: boolean
  schedule: string | null
  lastRunId: string | null
  lastRunStatus: string | null
  lastRunStartedAt: string | null
  lastRunFinishedAt: string | null
  lastRunDurationSeconds: number | null
  lastRunErrorCode: string | null
  lastRunError: string | null
  lastRunItemsSeen: number | null
  lastRunItemsPersisted: number | null
  lastRunItemsSkipped: number | null
  lastRunItemsInvalid: number | null
  seniorityCounts: Record<string, number>
}

export interface SourceHealthList {
  items: SourceHealth[]
  total: number
  failing: number
}

export interface SourceCoverageReport {
  catalogCompanies: number
  catalogSourceRecords: number
  proposedSources: number
  homologatedSources: number
  enabledSources: number
  eligibleSources: number
}

export interface SourceRun {
  id: string
  sourceDefinitionId: string
  sourceName: string | null
  executionTrigger: string
  status: string
  startedAt: string | null
  finishedAt: string | null
  itemsSeen: number
  itemsPersisted: number
  itemsSkipped: number
  itemsInvalid: number
  errorCode: string | null
  errorSummary: string | null
  correlationId: string | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function text(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function required(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function optionalNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function count(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function parseHealth(value: unknown): SourceHealth | null {
  if (!isRecord(value) || typeof value.source_definition_id !== 'string') return null
  return {
    sourceDefinitionId: value.source_definition_id,
    name: required(value.name, 'Fonte sem nome'),
    sourceType: required(value.source_type, 'unknown'),
    enabled: value.enabled === true,
    evidenceStatus: required(value.evidence_status, 'unverified'),
    termsReviewed: value.terms_reviewed === true,
    collectorLocalTested: value.collector_local_tested === true,
    schedule: text(value.schedule),
    lastRunId: text(value.last_run_id),
    lastRunStatus: text(value.last_run_status),
    lastRunStartedAt: text(value.last_run_started_at),
    lastRunFinishedAt: text(value.last_run_finished_at),
    lastRunDurationSeconds: optionalNumber(value.last_run_duration_seconds),
    lastRunErrorCode: text(value.last_run_error_code),
    lastRunError: text(value.last_run_error),
    lastRunItemsSeen: optionalNumber(value.last_run_items_seen),
    lastRunItemsPersisted: optionalNumber(value.last_run_items_persisted),
    lastRunItemsSkipped: optionalNumber(value.last_run_items_skipped),
    lastRunItemsInvalid: optionalNumber(value.last_run_items_invalid),
    seniorityCounts: isRecord(value.seniority_counts)
      ? Object.entries(value.seniority_counts).reduce<Record<string, number>>(
          (counts, [level, count]) => {
            if (typeof count === 'number') counts[level] = count
            return counts
          },
          {},
        )
      : {},
  }
}

function parseRun(value: unknown): SourceRun | null {
  if (!isRecord(value) || typeof value.id !== 'string') return null
  return {
    id: value.id,
    sourceDefinitionId: required(value.source_definition_id),
    sourceName: text(value.source_name),
    executionTrigger: required(value.execution_trigger, 'ON_DEMAND'),
    status: required(value.status, 'UNKNOWN'),
    startedAt: text(value.started_at),
    finishedAt: text(value.finished_at),
    itemsSeen: count(value.items_seen),
    itemsPersisted: count(value.items_persisted),
    itemsSkipped: count(value.items_skipped),
    itemsInvalid: count(value.items_invalid),
    errorCode: text(value.error_code),
    errorSummary: text(value.error_summary),
    correlationId: text(value.correlation_id),
  }
}

export async function getSourceHealth(): Promise<SourceHealthList> {
  const response = await fetch(apiUrl('/source-health'), {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw new Error('A API retornou uma lista de fontes inválida.')
  }
  return {
    items: body.items.map(parseHealth).filter((item): item is SourceHealth => item !== null),
    total: count(body.total),
    failing: count(body.failing),
  }
}

export async function getSourceCoverage(): Promise<SourceCoverageReport> {
  const response = await fetch(apiUrl('/source-coverage'), {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!isRecord(body)) throw new Error('A API retornou uma cobertura inválida.')
  return {
    catalogCompanies: count(body.catalog_companies),
    catalogSourceRecords: count(body.catalog_source_records),
    proposedSources: count(body.proposed_sources),
    homologatedSources: count(body.homologated_sources),
    enabledSources: count(body.enabled_sources),
    eligibleSources: count(body.eligible_sources),
  }
}

export async function getSourceRuns(sourceId: string, limit = 10): Promise<SourceRun[]> {
  const params = new URLSearchParams({
    source_id: sourceId,
    page: '1',
    page_size: String(limit),
  })
  const response = await fetch(apiUrl(`/source-runs?${params.toString()}`), {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw new Error('A API retornou um histórico de execuções inválido.')
  }
  return body.items.map(parseRun).filter((item): item is SourceRun => item !== null)
}

/**
 * Runs a source now. A collector that fails answers with a run in a failed state, so the
 * error belongs in the run history rather than in a toast.
 */
export async function runSource(sourceId: string): Promise<SourceRun> {
  const response = await fetch(apiUrl(`/sources/${sourceId}/runs`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ correlation_id: `dashboard-${Date.now()}` }),
  })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = isRecord(body) && isRecord(body.detail) ? body.detail : null
    const message = detail && typeof detail.message === 'string' ? detail.message : null
    throw requestFailure(response.status, message)
  }
  const run = parseRun(body)
  if (run === null) throw new Error('A API retornou uma execução inválida.')
  return run
}

/** The collectors a source can be created for, with the configuration each one needs. */
export const sourceTypes = ['ashby', 'lever', 'greenhouse', 'remotive', 'manual'] as const
export type SourceType = (typeof sourceTypes)[number]

export interface SourceDefinition {
  id: string
  sourceType: string
  name: string
  enabled: boolean
  schedule: string | null
  priority: number
  configuration: Record<string, unknown>
  evidenceStatus: string
  reviewedAt: string | null
  termsReviewed: boolean
  collectorLocalTested: boolean
  version: number
}

export interface NewSource {
  sourceType: SourceType
  name: string
  schedule: string | null
  priority: number
  rateLimitPolicy: Record<string, number>
  configuration: Record<string, string>
}

export interface SourceControls {
  enabled: boolean
  termsReviewed: boolean
  collectorLocalTested: boolean
  /** ISO date-time; null keeps the review date the source already has. */
  reviewedAt: string | null
  expectedVersion: number
}

export type ManualInputKind = 'URL' | 'TEXT' | 'FILE'

export interface ManualInput {
  kind: ManualInputKind
  value: string
  contentBase64?: string
  contentType?: string
  metadata: Record<string, string>
}

export interface RunNormalizationItem {
  rawItemId: string
  canonicalUrl: string | null
  status: string
  identityDecision: string | null
  errorSummary: string | null
  opportunityId: string | null
  opportunityTitle: string | null
}

function parseSource(value: unknown): SourceDefinition | null {
  if (!isRecord(value) || typeof value.id !== 'string') return null
  return {
    id: value.id,
    sourceType: required(value.source_type, 'unknown'),
    name: required(value.name, 'Fonte sem nome'),
    enabled: value.enabled === true,
    schedule: text(value.schedule),
    priority: count(value.priority),
    configuration: isRecord(value.configuration) ? value.configuration : {},
    evidenceStatus: required(value.evidence_status, 'unverified'),
    reviewedAt: text(value.reviewed_at),
    termsReviewed: value.terms_reviewed === true,
    collectorLocalTested: value.collector_local_tested === true,
    version: count(value.version),
  }
}

async function send(path: string, method: string, payload: unknown): Promise<unknown> {
  const response = await fetch(apiUrl(path), {
    method,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
  if (!response.ok) throw await failureFrom(response)
  return response.json()
}

export async function getSource(sourceId: string): Promise<SourceDefinition> {
  const response = await fetch(apiUrl(`/sources/${sourceId}`), {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw await failureFrom(response)
  const source = parseSource(await response.json())
  if (source === null) throw new Error('A API retornou uma fonte inválida.')
  return source
}

/**
 * Creates a source. It is born disabled, always: the form never sends `enabled`, and the
 * gate that decides when an external source may run belongs to homologation, not here.
 */
export async function createSource(input: NewSource): Promise<SourceDefinition> {
  const body = await send('/sources', 'POST', {
    source_type: input.sourceType,
    name: input.name,
    schedule: input.schedule,
    priority: input.priority,
    rate_limit_policy: input.rateLimitPolicy,
    configuration: input.configuration,
  })
  const source = parseSource(body)
  if (source === null) throw new Error('A API retornou uma fonte inválida.')
  return source
}

export async function updateSourceControls(
  sourceId: string,
  controls: SourceControls,
): Promise<SourceDefinition> {
  const body = await send(`/sources/${sourceId}`, 'PATCH', {
    enabled: controls.enabled,
    terms_reviewed: controls.termsReviewed,
    collector_local_tested: controls.collectorLocalTested,
    reviewed_at: controls.reviewedAt,
    expected_version: controls.expectedVersion,
  })
  const source = parseSource(body)
  if (source === null) throw new Error('A API retornou uma fonte inválida.')
  return source
}

/** Submits manual inputs as one run. Repeated evidence comes back counted as skipped. */
export async function submitManualRun(
  sourceId: string,
  inputs: ManualInput[],
): Promise<SourceRun> {
  const body = await send(`/sources/${sourceId}/runs`, 'POST', {
    mode: 'MANUAL',
    correlation_id: `manual-intake-${Date.now()}`,
    inputs: inputs.map((input) => ({
      kind: input.kind,
      value: input.value,
      content_base64: input.contentBase64 ?? null,
      content_type: input.contentType ?? null,
      metadata: input.metadata,
    })),
  })
  const run = parseRun(body)
  if (run === null) throw new Error('A API retornou uma execução inválida.')
  return run
}

export async function normalizeRun(runId: string): Promise<RunNormalizationItem[]> {
  const body = await send(`/opportunities/normalizations/runs/${runId}`, 'POST', undefined)
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw new Error('A API retornou uma normalização inválida.')
  }
  return body.items.flatMap((item): RunNormalizationItem[] => {
    if (!isRecord(item) || typeof item.raw_item_id !== 'string' || !isRecord(item.result)) {
      return []
    }
    const opportunity = isRecord(item.opportunity) ? item.opportunity : null
    return [
      {
        rawItemId: item.raw_item_id,
        canonicalUrl: text(item.canonical_url),
        status: required(item.result.status, 'UNKNOWN'),
        identityDecision: text(item.result.identity_decision),
        errorSummary: text(item.result.error_summary),
        opportunityId: text(item.result.opportunity_id),
        opportunityTitle: opportunity ? text(opportunity.title) : null,
      },
    ]
  })
}
