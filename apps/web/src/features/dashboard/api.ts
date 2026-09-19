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
  assessmentId: string | null
  verdict: string | null
  eligibility: string | null
  score: string | null
  confidence: string | null
  assessedAt: string | null
  analysisStatus: string | null
  analysisRecommendedReview: boolean | null
  analysisSummary: string | null
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
  workMode?: string
  lifecycleStatus?: string
  onlyAssessed?: boolean
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
  /** Null means phase 8 has not built the pipeline yet — it does not mean zero. */
  applicationsActive: number | null
  followUpsDue: number | null
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

function optionalCount(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
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
    assessmentId: text(value.assessment_id),
    verdict: text(value.verdict),
    eligibility: text(value.eligibility),
    score: text(value.score),
    confidence: text(value.confidence),
    assessedAt: text(value.assessed_at),
    analysisStatus: text(value.analysis_status),
    analysisRecommendedReview: flag(value.analysis_recommended_review),
    analysisSummary: text(value.analysis_summary),
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
  workMode,
  lifecycleStatus,
  onlyAssessed,
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
  if (workMode) params.set('work_mode', workMode)
  if (lifecycleStatus) params.set('lifecycle_status', lifecycleStatus)
  if (onlyAssessed) params.set('only_assessed', 'true')
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

export async function getOverview(): Promise<Overview> {
  const response = await fetch(apiUrl('/overview'), {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!isRecord(body)) throw new Error('A API retornou um resumo inválido.')
  const verdictCounts: Record<string, number> = {}
  if (isRecord(body.verdict_counts)) {
    for (const [verdict, value] of Object.entries(body.verdict_counts)) {
      verdictCounts[verdict] = count(value)
    }
  }
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
    applicationsActive: optionalCount(body.applications_active),
    followUpsDue: optionalCount(body.follow_ups_due),
  }
}
