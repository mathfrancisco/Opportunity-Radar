import { apiUrl } from '../../lib/api'

export const applicationStages = [
  'INTERESTED',
  'APPLIED',
  'SCREENING',
  'INTERVIEW',
  'TECHNICAL',
  'FINAL',
  'OFFER',
  'REJECTED',
  'WITHDRAWN',
  'CLOSED',
] as const

export type ApplicationStage = (typeof applicationStages)[number]

export const stageLabels: Record<ApplicationStage, string> = {
  INTERESTED: 'Interesse',
  APPLIED: 'Candidatura enviada',
  SCREENING: 'Triagem',
  INTERVIEW: 'Entrevista',
  TECHNICAL: 'Teste técnico',
  FINAL: 'Etapa final',
  OFFER: 'Oferta',
  REJECTED: 'Recusada',
  WITHDRAWN: 'Desistência',
  CLOSED: 'Encerrada',
}

export interface StageHistoryEntry {
  id: string
  fromStage: string | null
  toStage: string
  reason: string | null
  source: string
  notes: string | null
  occurredAt: string
}

export interface Application {
  id: string
  opportunityId: string
  profileVersionId: string
  currentStage: string
  status: string
  outcome: string | null
  nextAction: string | null
  nextActionAt: string | null
  notes: string | null
  appliedAt: string | null
  startedAt: string
  closedAt: string | null
  version: number
  allowedTransitions: string[]
  history: StageHistoryEntry[]
}

export interface ApplicationPage {
  items: Application[]
  total: number
  offset: number
  limit: number
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

function count(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function parseHistory(value: unknown): StageHistoryEntry | null {
  if (!isRecord(value) || typeof value.id !== 'string') return null
  return {
    id: value.id,
    fromStage: text(value.from_stage),
    toStage: required(value.to_stage, 'UNKNOWN'),
    reason: text(value.reason),
    source: required(value.source, 'MANUAL'),
    notes: text(value.notes),
    occurredAt: required(value.occurred_at),
  }
}

function parseApplication(value: unknown): Application | null {
  if (!isRecord(value) || typeof value.id !== 'string') return null
  return {
    id: value.id,
    opportunityId: required(value.opportunity_id),
    profileVersionId: required(value.profile_version_id),
    currentStage: required(value.current_stage, 'INTERESTED'),
    status: required(value.status, 'ACTIVE'),
    outcome: text(value.outcome),
    nextAction: text(value.next_action),
    nextActionAt: text(value.next_action_at),
    notes: text(value.notes),
    appliedAt: text(value.applied_at),
    startedAt: required(value.started_at),
    closedAt: text(value.closed_at),
    version: count(value.version),
    allowedTransitions: Array.isArray(value.allowed_transitions)
      ? value.allowed_transitions.filter((item): item is string => typeof item === 'string')
      : [],
    history: (Array.isArray(value.history) ? value.history : [])
      .map(parseHistory)
      .filter((item): item is StageHistoryEntry => item !== null),
  }
}

async function send(
  path: string,
  method: 'POST' | 'PATCH',
  payload: unknown,
): Promise<Application> {
  const response = await fetch(apiUrl(path), {
    method,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = isRecord(body) && isRecord(body.detail) ? body.detail : null
    const message = detail && typeof detail.message === 'string' ? detail.message : null
    throw new Error(message ?? `A API respondeu com ${response.status}.`)
  }
  const application = parseApplication(body)
  if (application === null) throw new Error('A API retornou uma candidatura inválida.')
  return application
}

export async function listApplications(
  params: { status?: string; stage?: string; opportunityId?: string; limit?: number } = {},
): Promise<ApplicationPage> {
  const query = new URLSearchParams({ limit: String(params.limit ?? 100) })
  if (params.status) query.set('application_status', params.status)
  if (params.stage) query.set('stage', params.stage)
  if (params.opportunityId) query.set('opportunity_id', params.opportunityId)
  const response = await fetch(apiUrl(`/applications?${query.toString()}`), {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw new Error('A API retornou uma lista de candidaturas inválida.')
  }
  return {
    items: body.items
      .map(parseApplication)
      .filter((item): item is Application => item !== null),
    total: count(body.total),
    offset: count(body.offset),
    limit: count(body.limit),
  }
}

/** The active application of an opportunity, or null when there is none. */
export async function getApplicationForOpportunity(
  opportunityId: string,
): Promise<Application | null> {
  const page = await listApplications({ opportunityId, status: 'ACTIVE', limit: 1 })
  return page.items[0] ?? null
}

export function startApplication(input: {
  opportunityId: string
  stage?: ApplicationStage
  notes?: string | null
}): Promise<Application> {
  return send('/applications', 'POST', {
    opportunity_id: input.opportunityId,
    stage: input.stage ?? 'INTERESTED',
    notes: input.notes ?? null,
  })
}

export function transitionApplication(input: {
  applicationId: string
  stage: string
  expectedVersion: number
  notes?: string | null
}): Promise<Application> {
  return send(`/applications/${input.applicationId}/transitions`, 'POST', {
    stage: input.stage,
    expected_version: input.expectedVersion,
    notes: input.notes ?? null,
  })
}

export function setNextAction(input: {
  applicationId: string
  expectedVersion: number
  nextAction: string | null
  nextActionAt: string | null
  notes?: string | null
}): Promise<Application> {
  return send(`/applications/${input.applicationId}/next-action`, 'PATCH', {
    expected_version: input.expectedVersion,
    next_action: input.nextAction,
    next_action_at: input.nextActionAt,
    notes: input.notes ?? null,
  })
}
