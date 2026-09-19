import { afterEach, describe, expect, it, vi } from 'vitest'
import { getCompany } from './api'

afterEach(() => vi.unstubAllGlobals())

function respond(body: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })),
  )
}

describe('getCompany', () => {
  it('reduz as verificações das fontes à mais recente', async () => {
    respond({
      id: 'company-1',
      name: 'Supabase',
      domain: 'supabase.com',
      priority: 'high',
      status: 'active',
      verification_state: 'api_json_confirmed',
      aliases: [{ id: 'alias-1', alias: 'Supabase Inc' }],
      sources: [
        {
          id: 'source-1',
          name: 'ashby',
          url: 'https://api.ashbyhq.com/posting-api/job-board/supabase',
          status: 'api_json_confirmed',
          external_key: 'supabase',
          verification_method: 'http_json',
          evidence: 'Endpoint respondeu 200 com lista de vagas.',
          last_verified_at: '2026-09-10T00:00:00Z',
        },
        {
          id: 'source-2',
          name: 'careers',
          url: 'https://supabase.com/careers',
          status: 'careers_confirmed',
          external_key: null,
          verification_method: 'manual',
          evidence: null,
          last_verified_at: '2026-09-14T00:00:00Z',
        },
      ],
    })

    const company = await getCompany('company-1')

    expect(fetch).toHaveBeenCalledWith('/api/companies/company-1', expect.any(Object))
    expect(company.aliases).toEqual(['Supabase Inc'])
    expect(company.sources).toHaveLength(2)
    expect(company.lastVerifiedAt).toBe('2026-09-14T00:00:00Z')
  })

  it('devolve null quando nenhuma fonte foi verificada', async () => {
    respond({
      id: 'company-2',
      name: 'Sem fontes',
      domain: null,
      priority: 'normal',
      status: 'active',
      verification_state: 'unverified',
      aliases: [],
      sources: [],
    })

    const company = await getCompany('company-2')

    expect(company.lastVerifiedAt).toBeNull()
    expect(company.domain).toBeNull()
  })

  it('traduz 404 em uma mensagem própria', async () => {
    respond({ detail: { code: 'company_not_found' } }, 404)
    await expect(getCompany('missing')).rejects.toThrow('não encontrada')
  })
})
