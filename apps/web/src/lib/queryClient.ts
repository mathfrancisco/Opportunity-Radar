import { QueryClient } from '@tanstack/react-query'
import { HttpError, NetworkError } from './api'

export const queryStaleTimes = {
  standard: 60_000,
  profile: 300_000,
} as const

/** Allows one retry only for a transient GET transport or server failure. */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (failureCount >= 1) return false
  if (error instanceof NetworkError) return error.method === 'GET'
  return error instanceof HttpError && error.method === 'GET' && error.status >= 500
}

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetryQuery, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  })
}
