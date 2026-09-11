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
