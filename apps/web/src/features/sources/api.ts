import { apiUrl } from '../../lib/api'

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
}

export interface SourceHealthList {
  items: SourceHealth[]
  total: number
  failing: number
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
    throw new Error(message ?? `A API respondeu com ${response.status}.`)
  }
  const run = parseRun(body)
  if (run === null) throw new Error('A API retornou uma execução inválida.')
  return run
}
