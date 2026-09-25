import { apiUrl } from '../../lib/api'

export const inboxOrders = ['priority', 'recency', 'score'] as const
export type InboxOrder = (typeof inboxOrders)[number]

export interface InboxItem {
  opportunityId: string
  title: string
  companyId: string | null
  companyName: string | null
  companyPriority: string | null
  location: string | null
  workMode: string
  seniority: string
  contractType: string
  lifecycleStatus: string
  publishedAt: string | null
  opportunityVersion: number
  assessmentId: string | null
  assessmentOpportunityVersion: number | null
  assessmentProfileVersionId: string | null
  currentProfileVersionId: string | null
  verdict: string | null
  eligibility: string | null
  score: string | null
  confidence: string | null
  rulesVersion: string | null
  isStale: boolean | null
  assessedAt: string | null
  analysisStatus: string | null
  analysisRecommendedReview: boolean | null
  analysisSummary: string | null
  applied: boolean
  applicationId: string | null
  applicationStage: string | null
  applicationNextActionAt: string | null
}

export interface InboxPage {
  items: InboxItem[]
  total: number
  offset: number
  limit: number
  order: InboxOrder
}

export interface InboxParams {
  page: number
  pageSize: number
  verdicts?: string[]
  minimumScore?: string
  companyId?: string
  workMode?: string
  lifecycleStatus?: string
  onlyAssessed?: boolean
  applied?: boolean
  search?: string
  order?: InboxOrder
}

export interface FailingSource {
  sourceDefinitionId: string
  name: string
  sourceType: string
  enabled: boolean
  lastRunStatus: string | null
  lastRunFinishedAt: string | null
  lastRunError: string | null
}

export interface Overview {
  opportunitiesTotal: number
  opportunitiesActive: number
  newOpportunities: number
  newOpportunityWindowDays: number
  assessedOpportunities: number
  verdictCounts: Record<string, number>
  analysesDegraded: number
  sourcesTotal: number
  sourcesEnabled: number
  sourcesFailing: number
  failingSources: FailingSource[]
  pendingNormalizations: number
  applicationsActive: number
  applicationsByStage: Record<string, number>
  followUpsDue: number
  followUpWindowDays: number
  precisionPercent: string | null
  precisionMarkedCount: number
  companiesCovered: number
  companiesWithAts: number
}

export const metricWindows = ['24h', '7d'] as const
export type MetricWindow = (typeof metricWindows)[number]

export interface SeniorityDistribution {
  counts: Record<string, number>
  percentages: Record<string, number>
  known: number
  unknown: number
  total: number
  mappingVersions: Record<string, number>
  evidence: Record<string, number>
}

export interface SourceMetrics {
  sourceDefinitionId: string
  name: string
  sourceType: string
  enabled: boolean
  schedule: string | null
  coverageState: string
  runs: number
  runsSucceeded: number
  runsPartial: number
  runsFailed: number
  itemsSeen: number
  itemsPersisted: number
  itemsSkipped: number
  itemsInvalid: number
  latencyP95Seconds: number | null
  errorRate: number | null
  dedupeRate: number | null
  hasRuns: boolean
  errorsByCode: Record<string, number>
  seniority: SeniorityDistribution
  incidentOpen: boolean
}

export interface SourceMetricsWindow {
  window: string
  since: string
  until: string
  sources: SourceMetrics[]
}

export interface SourceMetricsReport {
  generatedAt: string
  windows: SourceMetricsWindow[]
}

export interface ModelAnalysisMetrics {
  modelId: string | null
  analyses: number
  completed: number
  failed: number
  totalMsP50: number | null
  totalMsP95: number | null
  totalMsP99: number | null
  promptTokensAvg: number | null
  outputTokensAvg: number | null
  loadMsAvg: number | null
  failureRate: number | null
  failureRates: Record<string, number>
  reuseRate: number | null
}

export interface AnalysisMetricsWindow {
  window: string
  since: string
  until: string
  models: ModelAnalysisMetrics[]
}

export interface AnalysisMetricsReport {
  generatedAt: string
  currentModel: string
  pending: number
  windows: AnalysisMetricsWindow[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function text(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function count(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function countMap(value: unknown): Record<string, number> {
  const result: Record<string, number> = {}
  if (isRecord(value)) {
    for (const [key, entry] of Object.entries(value)) result[key] = count(entry)
  }
  return result
}

function flag(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function parseInboxItem(value: unknown): InboxItem | null {
  if (!isRecord(value) || typeof value.opportunity_id !== 'string') return null
  return {
    opportunityId: value.opportunity_id,
    title: typeof value.title === 'string' ? value.title : 'Sem título',
    companyId: text(value.company_id),
    companyName: text(value.company_name),
    companyPriority: text(value.company_priority),
    location: text(value.location),
    workMode: text(value.work_mode) ?? 'UNKNOWN',
    seniority: text(value.seniority) ?? 'UNKNOWN',
    contractType: text(value.contract_type) ?? 'UNKNOWN',
    lifecycleStatus: text(value.lifecycle_status) ?? 'UNKNOWN',
    publishedAt: text(value.published_at),
    opportunityVersion: typeof value.opportunity_version === 'number' ? value.opportunity_version : 1,
    assessmentId: text(value.assessment_id),
    assessmentOpportunityVersion:
      typeof value.assessment_opportunity_version === 'number'
        ? value.assessment_opportunity_version
        : null,
    assessmentProfileVersionId: text(value.assessment_profile_version_id),
    currentProfileVersionId: text(value.current_profile_version_id),
    verdict: text(value.verdict),
    eligibility: text(value.eligibility),
    score: text(value.score),
    confidence: text(value.confidence),
    rulesVersion: text(value.rules_version),
    isStale: typeof value.is_stale === 'boolean' ? value.is_stale : null,
    assessedAt: text(value.assessed_at),
    analysisStatus: text(value.analysis_status),
    analysisRecommendedReview: flag(value.analysis_recommended_review),
    analysisSummary: text(value.analysis_summary),
    applied: value.applied === true,
    applicationId: text(value.application_id),
    applicationStage: text(value.application_stage),
    applicationNextActionAt: text(value.application_next_action_at),
  }
}

function parseFailingSource(value: unknown): FailingSource | null {
  if (!isRecord(value) || typeof value.source_definition_id !== 'string') return null
  return {
    sourceDefinitionId: value.source_definition_id,
    name: typeof value.name === 'string' ? value.name : 'Fonte sem nome',
    sourceType: text(value.source_type) ?? 'unknown',
    enabled: value.enabled === true,
    lastRunStatus: text(value.last_run_status),
    lastRunFinishedAt: text(value.last_run_finished_at),
    lastRunError: text(value.last_run_error),
  }
}

export async function getInbox({
  page,
  pageSize,
  verdicts,
  minimumScore,
  companyId,
  workMode,
  lifecycleStatus,
  onlyAssessed,
  applied,
  search,
  order = 'priority',
}: InboxParams): Promise<InboxPage> {
  const params = new URLSearchParams({
    offset: String((page - 1) * pageSize),
    limit: String(pageSize),
    order,
  })
  verdicts?.forEach((verdict) => params.append('verdict', verdict))
  if (minimumScore) params.set('minimum_score', minimumScore)
  if (companyId) params.set('company_id', companyId)
  if (workMode) params.set('work_mode', workMode)
  if (lifecycleStatus) params.set('lifecycle_status', lifecycleStatus)
  if (onlyAssessed) params.set('only_assessed', 'true')
  if (applied !== undefined) params.set('applied', applied ? 'true' : 'false')
  if (search?.trim()) params.set('search', search.trim())

  const response = await fetch(apiUrl(`/inbox?${params.toString()}`), {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw new Error('A API retornou uma inbox inválida.')
  }
  return {
    items: body.items.map(parseInboxItem).filter((item): item is InboxItem => item !== null),
    total: count(body.total),
    offset: count(body.offset),
    limit: typeof body.limit === 'number' ? body.limit : pageSize,
    order,
  }
}

function optionalNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function rateMap(value: unknown): Record<string, number> {
  const result: Record<string, number> = {}
  if (isRecord(value)) {
    for (const [key, entry] of Object.entries(value)) {
      if (typeof entry === 'number' && Number.isFinite(entry)) result[key] = entry
    }
  }
  return result
}

function parseSeniority(value: unknown): SeniorityDistribution {
  const record = isRecord(value) ? value : {}
  return {
    counts: countMap(record.counts),
    percentages: rateMap(record.percentages),
    known: count(record.known),
    unknown: count(record.unknown),
    total: count(record.total),
    mappingVersions: countMap(record.mapping_versions),
    evidence: countMap(record.evidence),
  }
}

function parseSourceMetrics(value: unknown): SourceMetrics | null {
  if (!isRecord(value) || typeof value.source_definition_id !== 'string') return null
  return {
    sourceDefinitionId: value.source_definition_id,
    name: typeof value.name === 'string' ? value.name : 'Fonte sem nome',
    sourceType: text(value.source_type) ?? 'unknown',
    enabled: value.enabled === true,
    schedule: text(value.schedule),
    coverageState: text(value.coverage_state) ?? 'NOT_RUN',
    runs: count(value.runs),
    runsSucceeded: count(value.runs_succeeded),
    runsPartial: count(value.runs_partial),
    runsFailed: count(value.runs_failed),
    itemsSeen: count(value.items_seen),
    itemsPersisted: count(value.items_persisted),
    itemsSkipped: count(value.items_skipped),
    itemsInvalid: count(value.items_invalid),
    latencyP95Seconds: optionalNumber(value.latency_p95_seconds),
    // Null is the answer when the window holds no run; it must not collapse to zero.
    errorRate: optionalNumber(value.error_rate),
    dedupeRate: optionalNumber(value.dedupe_rate),
    hasRuns: value.has_runs === true,
    errorsByCode: countMap(value.errors_by_code),
    seniority: parseSeniority(value.seniority),
    incidentOpen: value.incident_open === true,
  }
}

export async function getSourceMetrics(): Promise<SourceMetricsReport> {
  const response = await fetch(apiUrl('/source-metrics'), {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!isRecord(body) || !Array.isArray(body.windows)) {
    throw new Error('A API retornou métricas de fontes inválidas.')
  }
  return {
    generatedAt: text(body.generated_at) ?? '',
    windows: body.windows
      .map((entry): SourceMetricsWindow | null => {
        if (!isRecord(entry) || typeof entry.window !== 'string') return null
        return {
          window: entry.window,
          since: text(entry.since) ?? '',
          until: text(entry.until) ?? '',
          sources: Array.isArray(entry.sources)
            ? entry.sources
                .map(parseSourceMetrics)
                .filter((item): item is SourceMetrics => item !== null)
            : [],
        }
      })
      .filter((entry): entry is SourceMetricsWindow => entry !== null),
  }
}

function parseModelAnalysisMetrics(value: unknown): ModelAnalysisMetrics | null {
  if (!isRecord(value)) return null
  return {
    modelId: text(value.model_id),
    analyses: count(value.analyses),
    completed: count(value.completed),
    failed: count(value.failed),
    // Null means the window recorded no cost; it must not collapse to zero.
    totalMsP50: optionalNumber(value.total_ms_p50),
    totalMsP95: optionalNumber(value.total_ms_p95),
    totalMsP99: optionalNumber(value.total_ms_p99),
    promptTokensAvg: optionalNumber(value.prompt_tokens_avg),
    outputTokensAvg: optionalNumber(value.output_tokens_avg),
    loadMsAvg: optionalNumber(value.load_ms_avg),
    failureRate: optionalNumber(value.failure_rate),
    failureRates: rateMap(value.failure_rates),
    reuseRate: optionalNumber(value.reuse_rate),
  }
}

export async function getAnalysisMetrics(): Promise<AnalysisMetricsReport> {
  const response = await fetch(apiUrl('/analysis-metrics'), {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!isRecord(body) || !Array.isArray(body.windows)) {
    throw new Error('A API retornou métricas de análise inválidas.')
  }
  return {
    generatedAt: text(body.generated_at) ?? '',
    currentModel: text(body.current_model) ?? '',
    pending: count(body.pending),
    windows: body.windows
      .map((entry): AnalysisMetricsWindow | null => {
        if (!isRecord(entry) || typeof entry.window !== 'string') return null
        return {
          window: entry.window,
          since: text(entry.since) ?? '',
          until: text(entry.until) ?? '',
          models: Array.isArray(entry.models)
            ? entry.models
                .map(parseModelAnalysisMetrics)
                .filter((item): item is ModelAnalysisMetrics => item !== null)
            : [],
        }
      })
      .filter((entry): entry is AnalysisMetricsWindow => entry !== null),
  }
}

export async function getOverview(): Promise<Overview> {
  const response = await fetch(apiUrl('/overview'), {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!isRecord(body)) throw new Error('A API retornou um resumo inválido.')
  const verdictCounts = countMap(body.verdict_counts)
  return {
    opportunitiesTotal: count(body.opportunities_total),
    opportunitiesActive: count(body.opportunities_active),
    newOpportunities: count(body.new_opportunities),
    newOpportunityWindowDays: count(body.new_opportunity_window_days),
    assessedOpportunities: count(body.assessed_opportunities),
    verdictCounts,
    analysesDegraded: count(body.analyses_degraded),
    sourcesTotal: count(body.sources_total),
    sourcesEnabled: count(body.sources_enabled),
    sourcesFailing: count(body.sources_failing),
    failingSources: Array.isArray(body.failing_sources)
      ? body.failing_sources
          .map(parseFailingSource)
          .filter((source): source is FailingSource => source !== null)
      : [],
    pendingNormalizations: count(body.pending_normalizations),
    applicationsActive: count(body.applications_active),
    applicationsByStage: countMap(body.applications_by_stage),
    followUpsDue: count(body.follow_ups_due),
    followUpWindowDays: count(body.follow_up_window_days),
    precisionPercent: text(body.precision_percent),
    precisionMarkedCount: count(body.precision_marked_count),
    companiesCovered: count(body.companies_covered),
    companiesWithAts: count(body.companies_with_ats),
  }
}
