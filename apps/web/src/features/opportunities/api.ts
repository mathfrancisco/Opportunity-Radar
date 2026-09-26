import { apiUrl } from '../../lib/api'

export interface Compensation {
  minimum: string | null
  maximum: string | null
  currency: string | null
  period: string
  grossNet: string
  evidenceText: string | null
  evidenceSource: string | null
  rawItemId: string
}

export interface OpportunitySkill {
  canonicalName: string
  displayName: string
  requirement: string
  taxonomyVersion: string
  evidence: unknown[]
}

export interface SourceOccurrence {
  id: string
  rawItemId: string
  sourceDefinitionId: string
  externalId: string | null
  sourceUrl: string | null
  firstSeenAt: string
  lastSeenAt: string
  sourcePublishedAt: string | null
  payloadRetained: boolean
  payloadExpiredAt: string | null
}

export interface NormalizationResult {
  id: string
  rawItemId: string
  status: string
  normalizerVersion: string
  identityDecision: string | null
  reasons: unknown[]
  errorSummary: string | null
  processedAt: string
}

export interface RelevanceMark {
  id: string
  relevant: boolean
  reason: string | null
  note: string | null
  markedAt: string
}

export interface OpportunityDetail {
  id: string
  fingerprint: string
  fingerprintVersion: string
  title: string
  companyId: string | null
  companyName: string | null
  location: string | null
  workMode: string
  seniority: string
  contractType: string
  description: string | null
  lifecycleStatus: string
  publishedAt: string | null
  /** When this opportunity was first persisted (F20-26): the older `createdAt` of a
   * duplicate pair is the one `confirm_duplicate` keeps as the survivor. */
  createdAt: string
  version: number
  compensations: Compensation[]
  skills: OpportunitySkill[]
  occurrences: SourceOccurrence[]
  normalizationResults: NormalizationResult[]
  relevanceMark: RelevanceMark | null
}

export interface DuplicateCandidate {
  id: string
  opportunityId: string
  duplicateOpportunityId: string
  rule: string
  score: string | null
  status: string
  decidedBy: string | null
  decidedAt: string | null
  createdAt: string
}

function parseRelevanceMark(value: unknown): RelevanceMark | null {
  if (!isRecord(value) || typeof value.id !== 'string') return null
  return {
    id: value.id,
    relevant: value.relevant === true,
    reason: text(value.reason),
    note: text(value.note),
    markedAt: required(value.marked_at),
  }
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

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function parseCompensation(value: unknown): Compensation | null {
  if (!isRecord(value)) return null
  return {
    minimum: text(value.minimum),
    maximum: text(value.maximum),
    currency: text(value.currency),
    period: required(value.period, 'UNKNOWN'),
    grossNet: required(value.gross_net, 'UNKNOWN'),
    evidenceText: text(value.evidence_text),
    evidenceSource: text(value.evidence_source),
    rawItemId: required(value.raw_item_id),
  }
}

function parseSkill(value: unknown): OpportunitySkill | null {
  if (!isRecord(value) || typeof value.canonical_name !== 'string') return null
  return {
    canonicalName: value.canonical_name,
    displayName: required(value.display_name, value.canonical_name),
    requirement: required(value.requirement, 'UNKNOWN'),
    taxonomyVersion: required(value.taxonomy_version),
    evidence: list(value.evidence),
  }
}

function parseOccurrence(value: unknown): SourceOccurrence | null {
  if (!isRecord(value) || typeof value.id !== 'string') return null
  return {
    id: value.id,
    rawItemId: required(value.raw_item_id),
    sourceDefinitionId: required(value.source_definition_id),
    externalId: text(value.external_id),
    sourceUrl: text(value.source_url),
    firstSeenAt: required(value.first_seen_at),
    lastSeenAt: required(value.last_seen_at),
    sourcePublishedAt: text(value.source_published_at),
    // An older API that does not know about retention has every payload, so the absent
    // field means retained rather than expired.
    payloadRetained: value.payload_retained !== false,
    payloadExpiredAt: text(value.payload_expired_at),
  }
}

function parseNormalization(value: unknown): NormalizationResult | null {
  if (!isRecord(value) || typeof value.id !== 'string') return null
  return {
    id: value.id,
    rawItemId: required(value.raw_item_id),
    status: required(value.status, 'UNKNOWN'),
    normalizerVersion: required(value.normalizer_version),
    identityDecision: text(value.identity_decision),
    reasons: list(value.reasons),
    errorSummary: text(value.error_summary),
    processedAt: required(value.processed_at),
  }
}

export async function getOpportunity(opportunityId: string): Promise<OpportunityDetail> {
  const response = await fetch(apiUrl(`/opportunities/${opportunityId}`), {
    headers: { Accept: 'application/json' },
  })
  if (response.status === 404) throw new Error('Oportunidade não encontrada.')
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!isRecord(body) || typeof body.id !== 'string') {
    throw new Error('A API retornou uma oportunidade inválida.')
  }
  return {
    id: body.id,
    fingerprint: required(body.fingerprint),
    fingerprintVersion: required(body.fingerprint_version),
    title: required(body.title, 'Sem título'),
    companyId: text(body.company_id),
    companyName: text(body.company_name),
    location: text(body.location),
    workMode: required(body.work_mode, 'UNKNOWN'),
    seniority: required(body.seniority, 'UNKNOWN'),
    contractType: required(body.contract_type, 'UNKNOWN'),
    description: text(body.description),
    lifecycleStatus: required(body.lifecycle_status, 'UNKNOWN'),
    publishedAt: text(body.published_at),
    createdAt: required(body.created_at),
    version: typeof body.version === 'number' ? body.version : 1,
    compensations: list(body.compensations)
      .map(parseCompensation)
      .filter((item): item is Compensation => item !== null),
    skills: list(body.skills)
      .map(parseSkill)
      .filter((item): item is OpportunitySkill => item !== null),
    occurrences: list(body.occurrences)
      .map(parseOccurrence)
      .filter((item): item is SourceOccurrence => item !== null),
    normalizationResults: list(body.normalization_results)
      .map(parseNormalization)
      .filter((item): item is NormalizationResult => item !== null),
    relevanceMark: parseRelevanceMark(body.relevance_mark),
  }
}

function parseDuplicateCandidate(value: unknown): DuplicateCandidate | null {
  if (!isRecord(value) || typeof value.id !== 'string') return null
  return {
    id: value.id,
    opportunityId: required(value.opportunity_id),
    duplicateOpportunityId: required(value.duplicate_opportunity_id),
    rule: required(value.rule, 'title_location_window'),
    score: text(value.score),
    status: required(value.status, 'PENDING'),
    decidedBy: text(value.decided_by),
    decidedAt: text(value.decided_at),
    createdAt: required(value.created_at),
  }
}

/** F20-26: candidates naming this opportunity on either side of the pair, every status
 * included — callers filter to `PENDING` for the "still owed a decision" view. */
export async function getDuplicateCandidates(
  opportunityId: string,
): Promise<DuplicateCandidate[]> {
  const response = await fetch(
    apiUrl(`/opportunities/${opportunityId}/duplicate-candidates`),
    { headers: { Accept: 'application/json' } },
  )
  if (response.status === 404) throw new Error('Oportunidade não encontrada.')
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw new Error('A API retornou candidatos a duplicata inválidos.')
  }
  return body.items
    .map(parseDuplicateCandidate)
    .filter((item): item is DuplicateCandidate => item !== null)
}

async function resolveDuplicateCandidate(
  action: 'confirm' | 'reject',
  candidateId: string,
  payload: Record<string, unknown>,
): Promise<DuplicateCandidate> {
  const response = await fetch(
    apiUrl(`/opportunities/duplicate-candidates/${candidateId}/${action}`),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(payload),
    },
  )
  if (response.status === 404) throw new Error('Candidato a duplicata não encontrado.')
  if (!response.ok) {
    const detail: unknown = await response.json().catch(() => null)
    const message =
      isRecord(detail) && isRecord(detail.detail) && typeof detail.detail.message === 'string'
        ? detail.detail.message
        : `A API respondeu com ${response.status}.`
    throw new Error(message)
  }
  const body: unknown = await response.json()
  const candidate = parseDuplicateCandidate(body)
  if (candidate === null) throw new Error('A API retornou uma resolução inválida.')
  return candidate
}

/** "É a mesma vaga": junta o par na oportunidade mais antiga (o backend decide qual é a
 * sobrevivente pelo `created_at`; o cliente só informa as versões esperadas de cada lado). */
export async function confirmDuplicate(
  candidateId: string,
  input: {
    expectedVersionSurvivor: number
    expectedVersionAbsorbed: number
    decidedBy: string
  },
): Promise<DuplicateCandidate> {
  return resolveDuplicateCandidate('confirm', candidateId, {
    expected_version_survivor: input.expectedVersionSurvivor,
    expected_version_absorbed: input.expectedVersionAbsorbed,
    decided_by: input.decidedBy,
  })
}

/** "São vagas diferentes": grava o par como recusado; a mesma dupla não volta a ser
 * sugerida enquanto nada mudar de material. */
export async function rejectDuplicate(
  candidateId: string,
  input: { decidedBy: string },
): Promise<DuplicateCandidate> {
  return resolveDuplicateCandidate('reject', candidateId, { decided_by: input.decidedBy })
}

export async function markRelevance(
  opportunityId: string,
  input: { relevant: boolean; reason?: string | null; note?: string | null },
): Promise<RelevanceMark> {
  const response = await fetch(apiUrl(`/opportunities/${opportunityId}/relevance`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({
      relevant: input.relevant,
      reason: input.reason ?? null,
      note: input.note ?? null,
    }),
  })
  if (response.status === 404) throw new Error('Oportunidade não encontrada.')
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  const mark = parseRelevanceMark(body)
  if (mark === null) throw new Error('A API retornou uma marca inválida.')
  return mark
}
