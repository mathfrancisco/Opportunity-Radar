import { afterEach, describe, expect, it, vi } from 'vitest'
import { getOpportunity } from './api'

afterEach(() => vi.unstubAllGlobals())

function respond(body: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })),
  )
}

describe('getOpportunity', () => {
  it('preserva procedência, remuneração e skills do detalhe', async () => {
    respond({
      id: 'opportunity-1',
      fingerprint: 'f'.repeat(64),
      fingerprint_version: 'v1',
      title: 'Senior Python Engineer',
      company_id: 'company-1',
      company_name: 'Example',
      location: 'Remote',
      work_mode: 'REMOTE',
      seniority: 'SENIOR',
      contract_type: 'FULL_TIME',
      description: 'Required: Python and ReactJS.',
      lifecycle_status: 'ACTIVE',
      published_at: null,
      source_updated_at: null,
      version: 2,
      compensations: [
        {
          minimum: '100000',
          maximum: '150000',
          currency: 'USD',
          period: 'YEAR',
          gross_net: 'UNKNOWN',
          evidence_text: 'USD 100k-150k',
          evidence_source: 'metadata.salaryRange',
          normalizer_version: 'v1',
          source_occurrence_id: 'occurrence-1',
          raw_item_id: 'raw-1',
        },
      ],
      skills: [
        {
          canonical_name: 'python',
          display_name: 'Python',
          requirement: 'REQUIRED',
          evidence: [{ raw_item_id: 'raw-1' }],
          taxonomy_version: 'skills-v1',
          normalizer_version: 'v1',
        },
      ],
      occurrences: [
        {
          id: 'occurrence-1',
          raw_item_id: 'raw-1',
          source_definition_id: 'source-1',
          external_id: null,
          source_url: 'https://example.com/jobs/ci-1',
          first_seen_at: '2026-09-17T10:00:00Z',
          last_seen_at: '2026-09-17T10:00:00Z',
          source_published_at: null,
          source_updated_at: null,
        },
      ],
      normalization_results: [
        {
          id: 'normalization-1',
          raw_item_id: 'raw-1',
          opportunity_id: 'opportunity-1',
          source_occurrence_id: 'occurrence-1',
          status: 'SUCCEEDED',
          normalizer_version: 'v1',
          identity_decision: 'NEW',
          reasons: [],
          error_summary: null,
          processed_at: '2026-09-17T10:01:00Z',
        },
      ],
    })

    const detail = await getOpportunity('opportunity-1')

    expect(fetch).toHaveBeenCalledWith('/api/opportunities/opportunity-1', expect.any(Object))
    expect(detail.title).toBe('Senior Python Engineer')
    expect(detail.compensations[0].currency).toBe('USD')
    expect(detail.skills[0].displayName).toBe('Python')
    expect(detail.occurrences[0].sourceUrl).toBe('https://example.com/jobs/ci-1')
    expect(detail.normalizationResults[0].identityDecision).toBe('NEW')
    expect(detail.publishedAt).toBeNull()
    // The response predates retention, so the payload is still there to reprocess.
    expect(detail.occurrences[0].payloadRetained).toBe(true)
    expect(detail.occurrences[0].payloadExpiredAt).toBeNull()
  })

  it('mostra a ocorrência cujo conteúdo bruto a retenção já expirou', async () => {
    respond({
      id: 'opportunity-1',
      occurrences: [
        {
          id: 'occurrence-1',
          raw_item_id: 'raw-1',
          source_definition_id: 'source-1',
          first_seen_at: '2025-09-17T10:00:00Z',
          last_seen_at: '2025-09-17T10:00:00Z',
          payload_retained: false,
          payload_expired_at: '2026-09-22T00:00:00Z',
        },
      ],
    })

    const detail = await getOpportunity('opportunity-1')

    expect(detail.occurrences[0].payloadRetained).toBe(false)
    expect(detail.occurrences[0].payloadExpiredAt).toBe('2026-09-22T00:00:00Z')
  })

  it('traduz 404 em uma mensagem própria', async () => {
    respond({ detail: { code: 'opportunity_not_found' } }, 404)
    await expect(getOpportunity('missing')).rejects.toThrow('não encontrada')
  })

  it('rejeita um corpo sem identidade', async () => {
    respond({ title: 'sem id' })
    await expect(getOpportunity('opportunity-1')).rejects.toThrow('oportunidade inválida')
  })
})
