import { apiUrl, failureFrom } from '../../lib/api'

export type SavedSearchFilters = Record<string, string | string[]>

export interface SavedSearch {
  id: string
  name: string
  term: string | null
  filters: SavedSearchFilters
  lastOpenedAt: string | null
  createdAt: string
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
    } else return null
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

async function send(path: string, method: string, payload?: unknown): Promise<unknown> {
  const response = await fetch(apiUrl(path), {
    method,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
  if (!response.ok) throw await failureFrom(response)
  return response.json()
}

export async function createSavedSearch(input: NewSavedSearch): Promise<SavedSearch> {
  const value = await send('/saved-searches', 'POST', input)
  const savedSearch = parseSavedSearch(value)
  if (savedSearch === null) throw new Error('A API retornou uma busca salva inválida.')
  return savedSearch
}

export async function getSavedSearches(): Promise<SavedSearch[]> {
  const value = await send('/saved-searches', 'GET')
  if (!Array.isArray(value)) throw new Error('A API retornou uma lista de buscas inválida.')
  const searches = value.map(parseSavedSearch)
  if (searches.some((item) => item === null)) {
    throw new Error('A API retornou uma busca salva inválida.')
  }
  return searches.filter((item): item is SavedSearch => item !== null)
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
  const response = await fetch(apiUrl(`/saved-searches/${savedSearchId}`), {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw await failureFrom(response)
}

export async function getSavedSearchNewCount(savedSearchId: string): Promise<number> {
  const value = await send(`/saved-searches/${savedSearchId}/new-count`, 'GET')
  if (!isRecord(value) || typeof value.new_count !== 'number') {
    throw new Error('A API retornou uma contagem de novidades inválida.')
  }
  return value.new_count
}
