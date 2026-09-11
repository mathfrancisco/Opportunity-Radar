import { afterEach, describe, expect, it, vi } from 'vitest'
import { getCompanies } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('getCompanies', () => {
  it('consulta a página solicitada e mantém os campos disponíveis', async () => {
    const company = {
      id: 'company-1',
      name: 'Acme',
      domain: 'acme.test',
      priority: 'HIGH',
      status: 'ACTIVE',
      verification_state: 'unverified',
      sources: [{ id: 'source-1', name: 'Greenhouse', status: 'VERIFIED' }],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ items: [company], page: 1, page_size: 25, total: 1 }),
          { status: 200 },
        ),
      ),
    )

    await expect(getCompanies({ page: 1, pageSize: 25, q: 'acme' })).resolves.toEqual({
      items: [
        {
          id: 'company-1',
          name: 'Acme',
          domain: 'acme.test',
          priority: 'HIGH',
          status: 'ACTIVE',
          verificationState: 'unverified',
          sources: [{ id: 'source-1', name: 'Greenhouse', status: 'VERIFIED' }],
        },
      ],
      page: 1,
      pageSize: 25,
      total: 1,
    })
    expect(fetch).toHaveBeenCalledWith(
      '/api/companies?page=1&page_size=25&q=acme',
      expect.any(Object),
    )
  })

  it('rejeita respostas sem uma coleção de itens', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ total: 0 }), { status: 200 }),
      ),
    )
    await expect(getCompanies({ page: 1, pageSize: 25 })).rejects.toThrow(
      'lista de empresas inválida',
    )
  })
})
