import { afterEach, describe, expect, it, vi } from 'vitest'
import { FieldError } from '../../lib/api'
import { registerCompany, updateCompany, updateCompanySource } from './api'

afterEach(() => vi.unstubAllGlobals())

function respond(body: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })),
  )
}

function sentBody(): Record<string, unknown> {
  const call = vi.mocked(fetch).mock.calls[0]
  return JSON.parse(String((call[1] as RequestInit).body)) as Record<string, unknown>
}

const companyBody = {
  id: 'company-1',
  name: 'Acme',
  domain: 'acme.com',
  priority: 'normal',
  status: 'active',
  verification_state: 'unverified',
  aliases: [{ id: 'alias-1', alias: 'ACME Labs' }],
  sources: [
    {
      id: 'cs-1',
      name: 'greenhouse',
      url: 'https://boards.greenhouse.io/acme',
      status: 'ats_identified',
      external_key: 'acme',
      verification_method: 'manual',
      evidence: 'Footer link.',
      last_verified_at: '2026-09-23T10:00:00Z',
      version: 2,
      revisions: [
        {
          version: 1,
          changed_at: '2026-09-22T10:00:00Z',
          changes: { external_key: { from: null, to: 'acmeold' } },
          evidence_note: 'Seen on careers.',
        },
        {
          version: 2,
          changed_at: '2026-09-23T10:00:00Z',
          changes: { external_key: { from: 'acmeold', to: 'acme' } },
          evidence_note: 'Board moved.',
        },
      ],
    },
  ],
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-23T10:00:00Z',
  version: 4,
}

describe('registerCompany', () => {
  it('diz se a empresa foi criada ou se uma existente respondeu', async () => {
    respond({ outcome: 'matched', aliases_added: 1, company: companyBody }, 201)

    const result = await registerCompany({
      name: 'ACME Labs',
      domain: null,
      priority: 'normal',
      radarStatus: 'active',
      aliases: [],
    })

    expect(result.outcome).toBe('matched')
    expect(result.aliasesAdded).toBe(1)
    expect(result.company.version).toBe(4)
    expect(sentBody()).toEqual({
      name: 'ACME Labs',
      domain: null,
      priority: 'normal',
      radar_status: 'active',
      aliases: [],
    })
  })

  it('leva o domínio de outra empresa ao campo, como conflito de identidade', async () => {
    respond(
      {
        detail: {
          code: 'identity_conflict',
          message: 'domain acme.com already belongs to Acme',
          field: 'domain',
        },
      },
      409,
    )

    const failure = registerCompany({
      name: 'Other',
      domain: 'acme.com',
      priority: 'normal',
      radarStatus: 'active',
      aliases: [],
    })

    await expect(failure).rejects.toBeInstanceOf(FieldError)
  })
})

describe('updateCompany', () => {
  it('envia a versão lida e lê o histórico das fontes', async () => {
    respond(companyBody)

    const company = await updateCompany('company-1', {
      name: 'Acme',
      domain: 'acme.com',
      priority: 'high',
      radarStatus: 'active',
      aliases: ['ACME Labs'],
      expectedVersion: 3,
    })

    expect(sentBody()).toMatchObject({ expected_version: 3, priority: 'high' })
    expect(company.sources[0].revisions.map((revision) => revision.version)).toEqual([1, 2])
    expect(company.sources[0].revisions[1].changes.external_key).toEqual({
      from: 'acmeold',
      to: 'acme',
    })
  })
})

describe('updateCompanySource', () => {
  it('corrige na versão lida, com a nota de evidência', async () => {
    respond({
      proposal_outcome: 'outdated',
      source: {
        ...companyBody.sources[0],
        proposal: {
          source_id: 'src-1',
          source_type: 'greenhouse',
          external_key: 'acmeold',
          enabled: true,
          evidence_status: 'confirmed',
          terms_reviewed: true,
          collector_local_tested: true,
          version: 5,
          outdated: true,
        },
      },
    })

    const correction = await updateCompanySource('company-1', 'cs-1', {
      sourceType: 'greenhouse',
      endpoint: 'https://boards.greenhouse.io/acme',
      externalKey: 'acme',
      evidenceNote: 'Board moved.',
      expectedVersion: 1,
    })

    expect(fetch).toHaveBeenCalledWith(
      '/api/companies/company-1/sources/cs-1',
      expect.objectContaining({ method: 'PATCH' }),
    )
    expect(sentBody()).toEqual({
      source_type: 'greenhouse',
      endpoint: 'https://boards.greenhouse.io/acme',
      external_key: 'acme',
      evidence_note: 'Board moved.',
      expected_version: 1,
    })
    expect(correction.proposalOutcome).toBe('outdated')
    expect(correction.source.proposal).toMatchObject({ externalKey: 'acmeold', outdated: true })
  })
})
