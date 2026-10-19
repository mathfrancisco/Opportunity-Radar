import { apiUrl, failureFrom, privateFetch } from '../../lib/api'

export type SavedSearchFilterValue = string | string[] | number | boolean
export type SavedSearchFilters = Record<string, SavedSearchFilterValue>

export interface SavedSearch {
  id: string
  name: string
  term: string | null
  filters: SavedSearchFilters
  lastOpenedAt: string | null
  createdAt: string
}

export interface SavedSearchSummary extends SavedSearch {
  newCount: number | null
  countError: 'invalid_filters' | 'invalid_summary' | null
  /** `salary_unit_defaulted`: a legacy salary filter counted as BRL/month. */
  countNote: 'salary_unit_defaulted' | null
}

export interface NewSavedSearch {
  name: string
  term: string | null
  filters: SavedSearchFilters
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function parseFilters(value: unknown): SavedSearchFilters | null {
  if (!isRecord(value)) return null
  const filters: SavedSearchFilters = {}
  for (const [key, item] of Object.entries(value)) {
    if (typeof item === 'string') filters[key] = item
    else if (Array.isArray(item) && item.every((entry) => typeof entry === 'string')) {
      filters[key] = item
    } else if (typeof item === 'number' || typeof item === 'boolean') filters[key] = item
    else return null
  }
  return filters
}

function parseSavedSearch(value: unknown): SavedSearch | null {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.name !== 'string') {
    return null
  }
  const filters = parseFilters(value.filters)
  if (filters === null) return null
  return {
    id: value.id,
    name: value.name,
    term: typeof value.term === 'string' ? value.term : null,
    filters,
    lastOpenedAt: typeof value.last_opened_at === 'string' ? value.last_opened_at : null,
    createdAt: typeof value.created_at === 'string' ? value.created_at : '',
  }
}

async function send(
  path: string,
  method: string,
  payload?: unknown,
  signal?: AbortSignal,
): Promise<unknown> {
  const response = await privateFetch(apiUrl(path), {
    method,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
    signal,
  })
  if (!response.ok) throw await failureFrom(response, method)
  return response.json()
}

export async function createSavedSearch(input: NewSavedSearch): Promise<SavedSearch> {
  const value = await send('/saved-searches', 'POST', input)
  const savedSearch = parseSavedSearch(value)
  if (savedSearch === null) throw new Error('A API retornou uma busca salva inválida.')
  return savedSearch
}

export async function getSavedSearches(signal?: AbortSignal): Promise<SavedSearch[]> {
  const value = await send('/saved-searches', 'GET', undefined, signal)
  if (!Array.isArray(value)) throw new Error('A API retornou uma lista de buscas inválida.')
  const searches = value.map(parseSavedSearch)
  if (searches.some((item) => item === null)) {
    throw new Error('A API retornou uma busca salva inválida.')
  }
  return searches.filter((item): item is SavedSearch => item !== null)
}

export function parseSummary(value: unknown): SavedSearchSummary[] {
  if (!Array.isArray(value)) throw new Error('A API retornou um resumo de buscas inválido.')
  return value.flatMap((item): SavedSearchSummary[] => {
    if (!isRecord(item) || typeof item.id !== 'string' || typeof item.name !== 'string') return []
    const countError = item.count_error === 'invalid_filters' ? 'invalid_filters' : null
    const countNote = item.count_note === 'salary_unit_defaulted' ? 'salary_unit_defaulted' : null
    const parsed = parseSavedSearch(item)
    const base: SavedSearch = parsed ?? {
      id: item.id,
      name: item.name,
      term: typeof item.term === 'string' ? item.term : null,
      filters: {},
      lastOpenedAt: typeof item.last_opened_at === 'string' ? item.last_opened_at : null,
      createdAt: typeof item.created_at === 'string' ? item.created_at : '',
    }
    const rawCount = item.new_count
    const validCount = typeof rawCount === 'number' && Number.isInteger(rawCount) && rawCount >= 0
    if (countError === 'invalid_filters' || !parsed || !validCount) {
      return [{ ...base, newCount: null, countError: countError ?? 'invalid_summary', countNote }]
    }
    return [{ ...base, newCount: rawCount, countError: null, countNote }]
  })
}

export async function getSavedSearchSummary(signal?: AbortSignal): Promise<SavedSearchSummary[]> {
  return parseSummary(await send('/saved-searches/summary', 'GET', undefined, signal))
}

export async function openSavedSearch(savedSearchId: string): Promise<SavedSearch> {
  const value = await send(`/saved-searches/${savedSearchId}`, 'PATCH', { open: true })
  const savedSearch = parseSavedSearch(value)
  if (savedSearch === null) throw new Error('A API retornou uma busca salva inválida.')
  return savedSearch
}

export async function renameSavedSearch(savedSearchId: string, name: string): Promise<SavedSearch> {
  const value = await send(`/saved-searches/${savedSearchId}`, 'PATCH', { name })
  const savedSearch = parseSavedSearch(value)
  if (savedSearch === null) throw new Error('A API retornou uma busca salva inválida.')
  return savedSearch
}

export async function deleteSavedSearch(savedSearchId: string): Promise<void> {
  const response = await privateFetch(apiUrl(`/saved-searches/${savedSearchId}`), {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw await failureFrom(response, 'DELETE')
}

export async function getSavedSearchNewCount(
  savedSearchId: string,
  signal?: AbortSignal,
): Promise<number> {
  const value = await send(`/saved-searches/${savedSearchId}/new-count`, 'GET', undefined, signal)
  if (!isRecord(value) || typeof value.new_count !== 'number') {
    throw new Error('A API retornou uma contagem de novidades inválida.')
  }
  return value.new_count
}
