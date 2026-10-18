export type RequestOutcome = 'success' | 'error' | 'cancelled'
export type RequestMetricsMode = 'baseline' | 'final'
export type SavedSearchFixture = 'legacy' | 'summary'
export type RequestTrafficKind = 'product' | 'auth-session' | 'preflight'

export interface RequestMetric {
  method: string
  endpoint: string
  status: number | null
  outcome: RequestOutcome
  trafficKind: RequestTrafficKind
  /** Chronological fixture request number. It does not classify retries. */
  requestOrdinal: number
  /** Null until a scenario supplies an explicit logical-operation correlation. */
  retry: boolean | null
  synthetic: true
  bytes: number | null
  durationMs: number
}

export interface RequestMetricsReport {
  version: 1
  synthetic: true
  mode: RequestMetricsMode
  savedSearchFixture: SavedSearchFixture
  provenance: {
    baselineSha: string
    finalRevision: string | null
    finalDirty: boolean | null
  }
  requests: RequestMetric[]
  routes: RequestRouteSummary[]
}

/** Aggregate is scoped to one scenario and normalized transport route. */
export interface RequestRouteSummary {
  method: string
  endpoint: string
  trafficKind: RequestTrafficKind
  calls: number
  errors: number
  cancelled: number
  /** Attempts where fixture correlation can classify retry state, plus true retries. */
  retryKnown: { attempts: number, retries: number }
  retryUnknown: number
  /** Bytes are summed only for observed bodies; unknown bytes remain explicit. */
  bytesKnown: { responses: number, total: number }
  bytesUnknown: number
  durationMs: { percentileMethod: 'nearest-rank', p50: number, p95: number }
}

export type OfflineRoute = (request: Request) => Response | Promise<Response>

export interface RequestMetricsOptions {
  mode?: RequestMetricsMode
  now?: () => number
  savedSearchFixture?: SavedSearchFixture
  /** A fixture-only correlation that distinguishes a retry from another operation. */
  isRetry?: (request: Request, requestOrdinal: number) => boolean
}

const baselineSha = 'a7f62e302dc7633a005c5e7ada66402e0fa71435'

const uuidSegment = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i
const identifierParents = new Set([
  'applications',
  'companies',
  'duplicate-candidates',
  'matches',
  'opportunities',
  'runs',
  'saved-searches',
  'sources',
])
const namedRouteSegments = new Set([
  'analysis',
  'coverage',
  'duplicate-candidates',
  'evaluate',
  'homologation-queue',
  'inbox',
  'latest',
  'new-count',
  'normalizations',
  'relevance',
  'runs',
  'summary',
])

/** Removes query strings and identifiers before an offline result is persisted. */
export function normalizedEndpoint(input: RequestInfo | URL): string {
  const url = new URL(String(input), 'http://offline.invalid')
  const path = url.pathname.replace(/^\/api(?=\/|$)/, '') || '/'
  return path
    .split('/')
    .map((part, index, parts) =>
      uuidSegment.test(part) || (identifierParents.has(parts[index - 1]) && !namedRouteSegments.has(part))
        ? ':id'
        : part,
    )
    .join('/')
}

/** The comparison cannot silently mix the original N+1 fixture and a future summary fixture. */
export function requestMetricsMode(value = process.env.REQUEST_METRICS_MODE): RequestMetricsMode {
  if (value === undefined || value === 'final') return 'final'
  if (value === 'baseline') return 'baseline'
  throw new Error('REQUEST_METRICS_MODE deve ser baseline ou final.')
}

/** Baseline replay uses the captured defaults; final mode uses the application factory. */
export function createScenarioQueryClient(mode: RequestMetricsMode) {
  if (mode === 'final') return createQueryClient()
  return new QueryClient({
    defaultOptions: {
      queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 0 },
      mutations: { retry: false },
    },
  })
}

async function bodySize(response: Response): Promise<number | null> {
  const value = response.headers.get('content-length')
  if (value !== null && /^\d+$/.test(value)) return Number(value)
  try {
    return new TextEncoder().encode(await response.clone().text()).byteLength
  } catch {
    return null
  }
}

function trafficKind(method: string, endpoint: string): RequestTrafficKind {
  if (method === 'OPTIONS') return 'preflight'
  if (endpoint === '/session' || endpoint.startsWith('/auth/')) return 'auth-session'
  return 'product'
}

function reportProvenance() {
  const dirty = process.env.REQUEST_METRICS_FINAL_DIRTY
  return {
    baselineSha: process.env.REQUEST_METRICS_BASELINE_SHA ?? baselineSha,
    finalRevision: process.env.REQUEST_METRICS_FINAL_REVISION ?? null,
    finalDirty: dirty === 'true' ? true : dirty === 'false' ? false : null,
  }
}

function nearestRank(values: number[], percentile: number) {
  const sorted = [...values].sort((left, right) => left - right)
  return sorted[Math.max(0, Math.ceil(sorted.length * percentile) - 1)]
}

function summarizeRoutes(requests: RequestMetric[]): RequestRouteSummary[] {
  const groups = new Map<string, RequestMetric[]>()
  for (const request of requests) {
    const key = [request.method, request.endpoint, request.trafficKind].join('\u0000')
    groups.set(key, [...(groups.get(key) ?? []), request])
  }
  return [...groups.values()].map((group) => {
    const first = group[0]
    const knownBytes = group.filter(({ bytes }) => bytes !== null) as Array<RequestMetric & { bytes: number }>
    const retryKnown = group.filter(({ retry }) => retry !== null)
    const durations = group.map(({ durationMs }) => durationMs)
    return {
      method: first.method,
      endpoint: first.endpoint,
      trafficKind: first.trafficKind,
      calls: group.length,
      errors: group.filter(({ outcome }) => outcome === 'error').length,
      cancelled: group.filter(({ outcome }) => outcome === 'cancelled').length,
      retryKnown: { attempts: retryKnown.length, retries: retryKnown.filter(({ retry }) => retry).length },
      retryUnknown: group.length - retryKnown.length,
      bytesKnown: { responses: knownBytes.length, total: knownBytes.reduce((total, request) => total + request.bytes, 0) },
      bytesUnknown: group.length - knownBytes.length,
      durationMs: { percentileMethod: 'nearest-rank', p50: nearestRank(durations, 0.5), p95: nearestRank(durations, 0.95) },
    }
  })
}

/**
 * A fetch replacement for route tests. It accepts only fixture routes: an unregistered
 * request rejects before a network call can escape the test process.
 */
export function createRequestMetricsFetch(route: OfflineRoute, options: RequestMetricsOptions = {}) {
  const now = options.now ?? (() => performance.now())
  const mode = options.mode ?? requestMetricsMode()
  const savedSearchFixture = options.savedSearchFixture ?? (mode === 'final' ? 'summary' : 'legacy')
  const requests: RequestMetric[] = []
  let requestOrdinal = 0

  const fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    const endpoint = normalizedEndpoint(input)
    const kind = trafficKind(method, endpoint)
    const ordinal = ++requestOrdinal
    const started = now()

    const request = new Request(
      input instanceof Request ? input : new URL(String(input), 'http://offline.invalid').toString(),
      init,
    )
    try {
      const response = await route(request)
      requests.push({
        method,
        endpoint,
        status: response.status,
        outcome: response.ok ? 'success' : 'error',
        trafficKind: kind,
        requestOrdinal: ordinal,
        retry: options.isRetry?.(request, ordinal) ?? null,
        synthetic: true,
        bytes: await bodySize(response),
        durationMs: Math.max(0, now() - started),
      })
      return response
    } catch (error) {
      const cancelled = error instanceof DOMException && error.name === 'AbortError'
      requests.push({
        method,
        endpoint,
        status: null,
        outcome: cancelled ? 'cancelled' : 'error',
        trafficKind: kind,
        requestOrdinal: ordinal,
        retry: options.isRetry?.(request, ordinal) ?? null,
        synthetic: true,
        bytes: null,
        durationMs: Math.max(0, now() - started),
      })
      throw error
    }
  }

  return {
    fetch,
    report(): RequestMetricsReport {
      return {
        version: 1,
        synthetic: true,
        mode,
        savedSearchFixture,
        provenance: reportProvenance(),
        requests: [...requests],
        routes: summarizeRoutes(requests),
      }
    },
  }
}
import { QueryClient } from '@tanstack/react-query'
import { createQueryClient } from '../lib/queryClient'

