import { apiUrl, failureFrom } from '../../lib/api'

export interface CompanySource {
  id?: string
  name?: string
  url?: string
  status?: string
}

export interface Company {
  id: string
  name: string
  domain?: string | null
  priority?: string | number | null
  status?: string | null
  verificationState: string
  sources?: CompanySource[]
}

export interface CompanyPage {
  items: Company[]
  page: number
  pageSize: number
  total: number
}

export interface CompanyListParams {
  page: number
  pageSize: number
  q?: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function optionalString(value: unknown): string | null | undefined {
  return typeof value === 'string' || value === null ? value : undefined
}

function parseSource(value: unknown): CompanySource | null {
  if (typeof value === 'string') return { name: value }
  if (!isRecord(value)) return null
  return {
    id: typeof value.id === 'string' ? value.id : undefined,
    name: typeof value.name === 'string' ? value.name : undefined,
    url: typeof value.url === 'string' ? value.url : undefined,
    status: typeof value.status === 'string' ? value.status : undefined,
  }
}

function parseCompany(value: unknown): Company | null {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.name !== 'string') {
    return null
  }
  const sources = Array.isArray(value.sources)
    ? value.sources.map(parseSource).filter((source): source is CompanySource => source !== null)
    : undefined
  const priority =
    typeof value.priority === 'string' ||
    typeof value.priority === 'number' ||
    value.priority === null
      ? value.priority
      : undefined
  return {
    id: value.id,
    name: value.name,
    domain: optionalString(value.domain),
    priority,
    status: optionalString(value.status),
    verificationState: optionalString(value.verification_state) ?? 'unknown',
    sources,
  }
}

export interface CompanyDetailSource {
  id: string
  name: string
  url: string
  status: string
  externalKey: string | null
  verificationMethod: string | null
  evidence: string | null
  lastVerifiedAt: string | null
  version: number
  revisions: CompanySourceRevision[]
  /** The source proposed from this record, as it reads today; null before any proposal. */
  proposal: ProposedSource | null
}

export interface ProposedSource {
  sourceId: string
  sourceType: string
  externalKey: string | null
  enabled: boolean
  evidenceStatus: string
  termsReviewed: boolean
  collectorLocalTested: boolean
  version: number
  /** The record was corrected after the proposal, and the proposal did not follow. */
  outdated: boolean
}

export type ProposalOutcome = 'none' | 'updated' | 'outdated'

export interface CompanySourceCorrection {
  proposalOutcome: ProposalOutcome
  source: CompanyDetailSource
}

/** One registration or correction of an ATS record, as the server kept it. */
export interface CompanySourceRevision {
  version: number
  changedAt: string
  /** Field name to the value it had before and after this change. */
  changes: Record<string, { from: unknown; to: unknown }>
  evidenceNote: string
}

export interface CompanyDetail {
  id: string
  name: string
  domain: string | null
  priority: string
  status: string
  verificationState: string
  aliases: string[]
  sources: CompanyDetailSource[]
  /** The most recent verification across sources, or null when none was verified. */
  lastVerifiedAt: string | null
  version: number
}

export const companyPriorities = ['high', 'normal', 'low'] as const
export const radarStatuses = ['active', 'paused'] as const

export interface CompanyInput {
  name: string
  domain: string | null
  priority: (typeof companyPriorities)[number]
  radarStatus: (typeof radarStatuses)[number]
  aliases: string[]
}

export interface CompanyRegistration {
  /** `matched`: the name was already known and the existing company answered. */
  outcome: 'created' | 'matched'
  aliasesAdded: number
  company: CompanyDetail
}

export const supportedAts = ['ashby', 'lever', 'greenhouse'] as const

export interface CompanySourceInput {
  sourceType: string
  endpoint: string
  externalKey: string
  evidenceNote: string
}

export interface SourceProposal {
  result: 'proposed' | 'already_proposed' | 'not_detected'
  sourceId: string | null
  evidence: string | null
  enabled: boolean
}

function parseDetailSource(value: unknown): CompanyDetailSource | null {
  if (!isRecord(value) || typeof value.id !== 'string') return null
  return {
    id: value.id,
    name: typeof value.name === 'string' ? value.name : 'fonte',
    url: typeof value.url === 'string' ? value.url : '',
    status: typeof value.status === 'string' ? value.status : 'unknown',
    externalKey: typeof value.external_key === 'string' ? value.external_key : null,
    verificationMethod:
      typeof value.verification_method === 'string' ? value.verification_method : null,
    evidence: typeof value.evidence === 'string' ? value.evidence : null,
    lastVerifiedAt:
      typeof value.last_verified_at === 'string' ? value.last_verified_at : null,
    version: typeof value.version === 'number' ? value.version : 1,
    revisions: (Array.isArray(value.revisions) ? value.revisions : []).flatMap(
      (revision): CompanySourceRevision[] =>
        isRecord(revision) && typeof revision.version === 'number'
          ? [
              {
                version: revision.version,
                changedAt: typeof revision.changed_at === 'string' ? revision.changed_at : '',
                changes: isRecord(revision.changes)
                  ? (revision.changes as CompanySourceRevision['changes'])
                  : {},
                evidenceNote:
                  typeof revision.evidence_note === 'string' ? revision.evidence_note : '',
              },
            ]
          : [],
    ),
    proposal: parseProposal(value.proposal),
  }
}

function parseProposal(value: unknown): ProposedSource | null {
  if (!isRecord(value) || typeof value.source_id !== 'string') return null
  return {
    sourceId: value.source_id,
    sourceType: typeof value.source_type === 'string' ? value.source_type : 'unknown',
    externalKey: typeof value.external_key === 'string' ? value.external_key : null,
    enabled: value.enabled === true,
    evidenceStatus: typeof value.evidence_status === 'string' ? value.evidence_status : 'unverified',
    termsReviewed: value.terms_reviewed === true,
    collectorLocalTested: value.collector_local_tested === true,
    version: typeof value.version === 'number' ? value.version : 1,
    outdated: value.outdated === true,
  }
}

export async function getCompany(companyId: string): Promise<CompanyDetail> {
  const response = await fetch(apiUrl(`/companies/${companyId}`), {
    headers: { Accept: 'application/json' },
  })
  if (response.status === 404) throw new Error('Empresa não encontrada.')
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  return parseCompanyDetail(await response.json())
}

function parseCompanyDetail(body: unknown): CompanyDetail {
  if (!isRecord(body) || typeof body.id !== 'string') {
    throw new Error('A API retornou uma empresa inválida.')
  }
  const sources = (Array.isArray(body.sources) ? body.sources : [])
    .map(parseDetailSource)
    .filter((source): source is CompanyDetailSource => source !== null)
  const verifiedDates = sources
    .map((source) => source.lastVerifiedAt)
    .filter((value): value is string => value !== null)
    .sort()
  return {
    id: body.id,
    name: typeof body.name === 'string' ? body.name : 'Empresa',
    domain: optionalString(body.domain) ?? null,
    priority: typeof body.priority === 'string' ? body.priority : 'normal',
    status: typeof body.status === 'string' ? body.status : 'unknown',
    verificationState:
      typeof body.verification_state === 'string' ? body.verification_state : 'unknown',
    aliases: (Array.isArray(body.aliases) ? body.aliases : [])
      .map((alias) => (isRecord(alias) && typeof alias.alias === 'string' ? alias.alias : null))
      .filter((alias): alias is string => alias !== null),
    sources,
    lastVerifiedAt: verifiedDates.at(-1) ?? null,
    version: typeof body.version === 'number' ? body.version : 1,
  }
}

async function send(path: string, method: string, payload: unknown): Promise<unknown> {
  const response = await fetch(apiUrl(path), {
    method,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw await failureFrom(response)
  return response.json()
}

function companyPayload(input: CompanyInput) {
  return {
    name: input.name,
    domain: input.domain,
    priority: input.priority,
    radar_status: input.radarStatus,
    aliases: input.aliases,
  }
}

export async function registerCompany(input: CompanyInput): Promise<CompanyRegistration> {
  const body = await send('/companies', 'POST', companyPayload(input))
  if (!isRecord(body)) throw new Error('A API retornou um cadastro inválido.')
  return {
    outcome: body.outcome === 'matched' ? 'matched' : 'created',
    aliasesAdded: typeof body.aliases_added === 'number' ? body.aliases_added : 0,
    company: parseCompanyDetail(body.company),
  }
}

export async function updateCompany(
  companyId: string,
  input: CompanyInput & { expectedVersion: number },
): Promise<CompanyDetail> {
  return parseCompanyDetail(
    await send(`/companies/${companyId}`, 'PATCH', {
      ...companyPayload(input),
      expected_version: input.expectedVersion,
    }),
  )
}

function sourcePayload(input: CompanySourceInput) {
  return {
    source_type: input.sourceType,
    endpoint: input.endpoint,
    external_key: input.externalKey,
    evidence_note: input.evidenceNote,
  }
}

export async function addCompanySource(
  companyId: string,
  input: CompanySourceInput,
): Promise<CompanyDetailSource> {
  const source = parseDetailSource(
    await send(`/companies/${companyId}/sources`, 'POST', sourcePayload(input)),
  )
  if (source === null) throw new Error('A API retornou uma fonte inválida.')
  return source
}

export async function updateCompanySource(
  companyId: string,
  sourceId: string,
  input: CompanySourceInput & { expectedVersion: number },
): Promise<CompanySourceCorrection> {
  const body = await send(`/companies/${companyId}/sources/${sourceId}`, 'PATCH', {
    ...sourcePayload(input),
    expected_version: input.expectedVersion,
  })
  const source = isRecord(body) ? parseDetailSource(body.source) : null
  if (!isRecord(body) || source === null) throw new Error('A API retornou uma fonte inválida.')
  return {
    proposalOutcome:
      body.proposal_outcome === 'updated' || body.proposal_outcome === 'outdated'
        ? body.proposal_outcome
        : 'none',
    source,
  }
}

/**
 * Points an outdated proposal at its corrected record and starts its gate over: disables
 * it, clears evidence, terms, test and review date, all in one versioned write.
 */
export async function reopenHomologation(sourceId: string, expectedVersion: number) {
  await send(`/sources/${sourceId}/reopen-homologation`, 'POST', {
    expected_version: expectedVersion,
  })
}

export async function detectCompanySource(companyId: string): Promise<SourceProposal> {
  const response = await fetch(apiUrl(`/companies/${companyId}/detect-source`), {
    method: 'POST',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!isRecord(body) || typeof body.result !== 'string') {
    throw new Error('A API retornou uma proposta inválida.')
  }
  return {
    result: body.result === 'proposed' || body.result === 'already_proposed'
      ? body.result
      : 'not_detected',
    sourceId: typeof body.source_id === 'string' ? body.source_id : null,
    evidence: typeof body.evidence === 'string' ? body.evidence : null,
    enabled: body.enabled === true,
  }
}

export async function getCompanies({
  page,
  pageSize,
  q,
}: CompanyListParams): Promise<CompanyPage> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (q?.trim()) params.set('q', q.trim())
  const response = await fetch(apiUrl(`/companies?${params.toString()}`), {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw new Error('A API retornou uma lista de empresas inválida.')
  }
  return {
    items: body.items.map(parseCompany).filter((company): company is Company => company !== null),
    page: typeof body.page === 'number' ? body.page : page,
    pageSize: typeof body.page_size === 'number' ? body.page_size : pageSize,
    total: typeof body.total === 'number' ? body.total : body.items.length,
  }
}
