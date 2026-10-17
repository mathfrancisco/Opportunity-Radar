import { describe, expect, it } from 'vitest'
import { ConflictError, FieldError, HttpError, NetworkError } from './api'
import { createQueryClient, queryStaleTimes, shouldRetryQuery } from './queryClient'

describe('query retry policy', () => {
  it('retries one GET transport or 5xx failure, then stops', () => {
    expect(shouldRetryQuery(0, new NetworkError('offline', 'GET'))).toBe(true)
    expect(shouldRetryQuery(0, new HttpError('unavailable', 503, 'GET'))).toBe(true)
    expect(shouldRetryQuery(1, new HttpError('unavailable', 503, 'GET'))).toBe(false)
  })

  it('does not retry auth, client, parser, cancellation, or writes', () => {
    expect(shouldRetryQuery(0, new HttpError('forbidden', 403, 'GET'))).toBe(false)
    expect(shouldRetryQuery(0, new ConflictError('changed', 'GET'))).toBe(false)
    expect(shouldRetryQuery(0, new FieldError('name', 'invalid', null, 422, 'GET'))).toBe(false)
    expect(shouldRetryQuery(0, new NetworkError('offline', 'POST'))).toBe(false)
    expect(shouldRetryQuery(0, new TypeError('invalid JSON'))).toBe(false)
    expect(shouldRetryQuery(0, Object.assign(new Error('parser'), { method: 'GET' }))).toBe(false)
    expect(shouldRetryQuery(0, { method: 'GET', status: 503 })).toBe(false)
    expect(shouldRetryQuery(0, new DOMException('cancelled', 'AbortError'))).toBe(false)
  })

  it('keeps focus disabled and mutations non-retrying in the factory used by the app and harness', () => {
    const client = createQueryClient()
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(false)
    expect(client.getDefaultOptions().mutations?.retry).toBe(false)
    expect(queryStaleTimes.standard).toBe(60_000)
    expect(queryStaleTimes.profile).toBe(300_000)
  })
})
