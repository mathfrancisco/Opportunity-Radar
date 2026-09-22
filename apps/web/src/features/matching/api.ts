import { apiUrl } from '../../lib/api'

export interface MatchFactor {
  factorCode: string
  weight: string
  rawScore: string | null
  contribution: string
  status: string
  confidence: string
  missingPolicy: string
  explanation: string
  evidenceRefs: unknown[]
}

export interface EligibilityDetail {
  code: string
  result: string
  reason: string
  severity: string | null
  confidence: string | null
  evidenceRefs: unknown[]
}

export interface MatchAnalysis {
  id: string
  status: string
  failureCode: string | null
  detail: string | null
  summary: string | null
  strengths: string[]
  risks: string[]
  inferences: string[]
  unknowns: string[]
  recommendedReview: boolean | null
  modelId: string | null
  promptVersion: string | null
  schemaVersion: string
  analyzedAt: string
}

export interface MatchAssessment {
  id: string
  opportunityId: string
  opportunityVersion: number
  profileVersionId: string
  rulesVersion: string
  taxonomyVersion: string
  inputHash: string
  eligibility: string
  eligibilityDetails: EligibilityDetail[]
  verdict: string
  score: string
  confidence: string
  isStale: boolean
  assessedAt: string
  factors: MatchFactor[]
  analysis: MatchAnalysis | null
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

function strings(value: unknown): string[] {
  return list(value).filter((item): item is string => typeof item === 'string')
}

function parseFactor(value: unknown): MatchFactor | null {
  if (!isRecord(value) || typeof value.factor_code !== 'string') return null
  return {
    factorCode: value.factor_code,
    weight: required(value.weight, '0'),
    rawScore: text(value.raw_score),
    contribution: required(value.contribution, '0'),
    status: required(value.status, 'UNKNOWN'),
    confidence: required(value.confidence, '0'),
    missingPolicy: required(value.missing_policy, 'NEUTRAL'),
    explanation: required(value.explanation),
    evidenceRefs: list(value.evidence_refs),
  }
}

function parseEligibility(value: unknown): EligibilityDetail | null {
  if (!isRecord(value) || typeof value.code !== 'string') return null
  return {
    code: value.code,
    result: required(value.result, 'UNKNOWN'),
    reason: required(value.reason),
    severity: text(value.severity),
    confidence: text(value.confidence),
    evidenceRefs: list(value.evidence_refs),
  }
}

function parseAnalysis(value: unknown): MatchAnalysis | null {
  if (!isRecord(value) || typeof value.id !== 'string') return null
  return {
    id: value.id,
    status: required(value.status, 'UNKNOWN'),
    failureCode: text(value.failure_code),
    detail: text(value.detail),
    summary: text(value.summary),
    strengths: strings(value.strengths),
    risks: strings(value.risks),
    inferences: strings(value.inferences),
    unknowns: strings(value.unknowns),
    recommendedReview: typeof value.recommended_review === 'boolean'
      ? value.recommended_review
      : null,
    modelId: text(value.model_id),
    promptVersion: text(value.prompt_version),
    schemaVersion: required(value.schema_version),
    analyzedAt: required(value.analyzed_at),
  }
}

function parseAssessment(value: unknown): MatchAssessment | null {
  if (!isRecord(value) || typeof value.id !== 'string') return null
  return {
    id: value.id,
    opportunityId: required(value.opportunity_id),
    opportunityVersion:
      typeof value.opportunity_version === 'number' ? value.opportunity_version : 1,
    profileVersionId: required(value.profile_version_id),
    rulesVersion: required(value.rules_version),
    taxonomyVersion: required(value.taxonomy_version),
    inputHash: required(value.input_hash),
    eligibility: required(value.eligibility, 'UNKNOWN'),
    eligibilityDetails: list(value.eligibility_details)
      .map(parseEligibility)
      .filter((item): item is EligibilityDetail => item !== null),
    verdict: required(value.verdict, 'UNKNOWN'),
    score: required(value.score, '0'),
    confidence: required(value.confidence, '0'),
    isStale: value.is_stale === true,
    assessedAt: required(value.assessed_at),
    factors: list(value.factors)
      .map(parseFactor)
      .filter((item): item is MatchFactor => item !== null),
    analysis: parseAnalysis(value.analysis),
  }
}

/** The most recent assessment of an opportunity, or null when it was never evaluated. */
export async function getLatestAssessment(
  opportunityId: string,
): Promise<MatchAssessment | null> {
  const params = new URLSearchParams({ opportunity_id: opportunityId, limit: '1' })
  const response = await fetch(apiUrl(`/matches?${params.toString()}`), {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw new Error('A API retornou uma lista de avaliações inválida.')
  }
  const [first] = body.items
  return first === undefined ? null : parseAssessment(first)
}

export async function evaluateOpportunity(opportunityId: string): Promise<MatchAssessment> {
  const response = await fetch(apiUrl('/matches/evaluate'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ opportunity_id: opportunityId }),
  })
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const assessment = parseAssessment(await response.json())
  if (assessment === null) throw new Error('A API retornou uma avaliação inválida.')
  return assessment
}

export async function analyzeAssessment(
  assessmentId: string,
  options: { refresh?: boolean } = {},
): Promise<MatchAnalysis> {
  const response = await fetch(apiUrl(`/matches/${assessmentId}/analysis`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ refresh: options.refresh === true }),
  })
  // 409 is the worker holding the same analysis. Saying so beats a bare status code,
  // because waiting and retrying is the correct response and a generic failure hides that.
  if (response.status === 409) {
    throw new Error('Esta análise já está em andamento. Tente novamente em instantes.')
  }
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const analysis = parseAnalysis(await response.json())
  if (analysis === null) throw new Error('A API retornou uma análise inválida.')
  return analysis
}
