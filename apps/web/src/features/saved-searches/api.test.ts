import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSavedSearch, getSavedSearches, openSavedSearch } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('saved searches API', () => {
  it('salva, lista e abre uma busca', async () => {
    const saved = {
      id: 'saved-1',
      name: 'Backend remoto',
      term: 'backend',
      filters: { work_mode: 'REMOTE' },
      last_opened_at: null,
      created_at: '2040-01-01T00:00:00Z',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn()
        .mockResolvedValueOnce(new Response(JSON.stringify(saved), { status: 201 }))
        .mockResolvedValueOnce(new Response(JSON.stringify([saved]), { status: 200 }))
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({ ...saved, last_opened_at: '2040-01-02T00:00:00Z' }),
            { status: 200 },
          ),
        ),
    )

    const created = await createSavedSearch({
      name: 'Backend remoto',
      term: 'backend',
      filters: { work_mode: 'REMOTE' },
    })
    const listed = await getSavedSearches()
    const opened = await openSavedSearch('saved-1')

    expect(created.id).toBe('saved-1')
    expect(listed.map((item) => item.id)).toEqual(['saved-1'])
    expect(opened.lastOpenedAt).toBe('2040-01-02T00:00:00Z')
    expect(fetch).toHaveBeenNthCalledWith(
      1,
      '/api/saved-searches',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/saved-searches', expect.any(Object))
    expect(fetch).toHaveBeenNthCalledWith(
      3,
      '/api/saved-searches/saved-1',
      expect.objectContaining({ method: 'PATCH' }),
    )
    const request = vi.mocked(fetch).mock.calls[0][1] as RequestInit
    expect(JSON.parse(String(request.body))).toEqual({
      name: 'Backend remoto',
      term: 'backend',
      filters: { work_mode: 'REMOTE' },
    })
  })
})
