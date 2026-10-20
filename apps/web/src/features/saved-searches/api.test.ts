import { installTestAuth } from '../../test/auth'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSavedSearch, getSavedSearches, getSavedSearchSummary, openSavedSearch, parseSummary } from './api'

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

  it('consulta o resumo aditivo e valida contagens não negativas inteiras', async () => {
    const summary = {
      id: 'saved-1', name: 'Backend remoto', term: null, filters: {},
      last_opened_at: null, created_at: '2040-01-01T00:00:00Z', new_count: 2,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify([summary]), { status: 200 }),
    ))

    await expect(getSavedSearchSummary()).resolves.toMatchObject([
      { id: 'saved-1', newCount: 2 },
    ])
    expect(fetch).toHaveBeenCalledWith('/api/saved-searches/summary', expect.any(Object))
    expect(parseSummary([{ ...summary, new_count: -1 }])[0]).toMatchObject({ newCount: null, countError: 'invalid_summary' })
    expect(parseSummary([{ ...summary, new_count: 1.5 }])[0]).toMatchObject({ newCount: null, countError: 'invalid_summary' })
  })

  it('lê count_note do resumo', () => {
    const base = { id: 's', name: 'N', filters: {}, new_count: 1 }
    expect(parseSummary([{ ...base, count_note: 'salary_unit_defaulted' }])[0]).toMatchObject({
      countNote: 'salary_unit_defaulted',
    })
    expect(parseSummary([{ ...base, count_note: 'other' }])[0]).toMatchObject({ countNote: null })
    expect(parseSummary([base])[0]).toMatchObject({ countNote: null })
  })

  it('isola filtros legados inválidos e preserva contagens válidas e filtros booleanos', () => {
    const result = parseSummary([
      { id: 'bad', name: 'Legada', filters: { order: 42 }, new_count: null, count_error: 'invalid_filters' },
      { id: 'good', name: 'Válida', filters: { only_startups: true }, new_count: 3, count_error: null },
    ])
    expect(result).toMatchObject([
      { id: 'bad', filters: {}, newCount: null, countError: 'invalid_filters' },
      { id: 'good', filters: { only_startups: true }, newCount: 3, countError: null },
    ])
  })
})

installTestAuth()
