import { installTestAuth } from '../../test/auth'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { setAuthTokenGetter } from '../../lib/api'
import { getReadiness } from './api'

afterEach(() => {
  setAuthTokenGetter(null)
  vi.unstubAllGlobals()
})

describe('getReadiness', () => {
  it('interpreta uma resposta pronta', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ready' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok', ai: { status: 'healthy' } }), { status: 200 })))

    await expect(getReadiness()).resolves.toEqual({ state: 'ready', detail: undefined })
    expect(fetch).toHaveBeenCalledWith('/api/health/ready', expect.any(Object))
  })

  it('gets a fresh Clerk token for each health request', async () => {
    const tokens = ['readiness-token', 'health-token']
    const getToken = vi.fn(async () => tokens.shift() ?? null)
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ready' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok', ai: { status: 'healthy' } }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    setAuthTokenGetter(getToken)

    await expect(getReadiness()).resolves.toEqual({ state: 'ready', detail: undefined })

    expect(getToken).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls.map(([url, init]) => [
      url,
      new Headers(init?.headers).get('Authorization'),
    ])).toEqual([
      ['/api/health/ready', 'Bearer readiness-token'],
      ['/api/health', 'Bearer health-token'],
    ])
  })

  it('preserva o modo degradado sem falhar o dashboard', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ready' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok', ai: { status: 'degraded' } }), { status: 200 })))

    await expect(getReadiness()).resolves.toEqual({ state: 'degraded', detail: 'IA indisponível. A coleta e as regras continuam disponíveis.' })
  })

  it('falha quando a API não responde com sucesso', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 503 })))

    await expect(getReadiness()).rejects.toThrow('503')
  })
})

installTestAuth()
