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
  version: number
  compensations: Compensation[]
  skills: OpportunitySkill[]
  occurrences: SourceOccurrence[]
  normalizationResults: NormalizationResult[]
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
  }
}
