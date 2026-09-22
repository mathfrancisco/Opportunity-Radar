import { apiUrl } from '../../lib/api'

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
  }
}

export async function getCompany(companyId: string): Promise<CompanyDetail> {
  const response = await fetch(apiUrl(`/companies/${companyId}`), {
    headers: { Accept: 'application/json' },
  })
  if (response.status === 404) throw new Error('Empresa não encontrada.')
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
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
  }
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
