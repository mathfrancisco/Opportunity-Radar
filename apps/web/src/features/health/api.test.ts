import { afterEach, describe, expect, it, vi } from 'vitest'
import { getReadiness } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('getReadiness', () => {
  it('interpreta uma resposta pronta', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ready' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok', ollama: { status: 'healthy' } }), { status: 200 })))

    await expect(getReadiness()).resolves.toEqual({ state: 'ready', detail: undefined })
    expect(fetch).toHaveBeenCalledWith('/api/health/ready', expect.any(Object))
  })

  it('preserva o modo degradado sem falhar o dashboard', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ready' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok', ollama: { status: 'degraded' } }), { status: 200 })))

    await expect(getReadiness()).resolves.toEqual({ state: 'degraded', detail: 'Ollama indisponível. A coleta e as regras continuam disponíveis.' })
  })

  it('falha quando a API não responde com sucesso', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 503 })))

    await expect(getReadiness()).rejects.toThrow('503')
  })
})
