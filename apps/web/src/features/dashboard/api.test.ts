import { afterEach, describe, expect, it, vi } from 'vitest'
import { getInbox, getOverview } from './api'

afterEach(() => vi.unstubAllGlobals())

function respond(body: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })),
  )
}

describe('getInbox', () => {
  it('traduz filtros e paginação para a query da API', async () => {
    respond({ items: [], total: 0, offset: 25, limit: 25 })

    await getInbox({
      page: 2,
      pageSize: 25,
      verdicts: ['HIGH_PRIORITY', 'RECOMMENDED'],
      minimumScore: '70',
      workMode: 'REMOTE',
      lifecycleStatus: 'ACTIVE',
      onlyAssessed: true,
      search: '  plataforma  ',
      order: 'score',
    })

    expect(fetch).toHaveBeenCalledWith(
      '/api/inbox?offset=25&limit=25&order=score&verdict=HIGH_PRIORITY&verdict=RECOMMENDED' +
        '&minimum_score=70&work_mode=REMOTE&lifecycle_status=ACTIVE&only_assessed=true' +
        '&search=plataforma',
      expect.any(Object),
    )
  })

  it('mantém oportunidades ainda não avaliadas', async () => {
    respond({
      items: [
        {
          opportunity_id: 'opportunity-1',
          title: 'Backend Engineer',
          company_id: null,
          company_name: 'Acme',
          company_priority: 'HIGH',
          location: 'Remoto',
          work_mode: 'REMOTE',
          seniority: 'SENIOR',
          contract_type: 'FULL_TIME',
          lifecycle_status: 'ACTIVE',
          published_at: '2026-09-10T00:00:00Z',
          opportunity_version: 1,
          assessment_id: null,
          verdict: null,
          eligibility: null,
          score: null,
          confidence: null,
          rules_version: null,
          assessed_at: null,
          analysis_status: null,
          analysis_recommended_review: null,
          analysis_summary: null,
        },
      ],
      total: 1,
      offset: 0,
      limit: 25,
    })

    const page = await getInbox({ page: 1, pageSize: 25 })

    expect(page.total).toBe(1)
    expect(page.items[0].opportunityId).toBe('opportunity-1')
    expect(page.items[0].verdict).toBeNull()
    expect(page.items[0].score).toBeNull()
    expect(page.order).toBe('priority')
  })

  it('rejeita respostas sem uma coleção de itens', async () => {
    respond({ total: 0 })
    await expect(getInbox({ page: 1, pageSize: 25 })).rejects.toThrow('inbox inválida')
  })
})

describe('getOverview', () => {
  it('preserva a ausência do pipeline como null, não como zero', async () => {
    respond({
      opportunities_total: 12,
      opportunities_active: 9,
      new_opportunities: 3,
      new_opportunity_window_days: 7,
      assessed_opportunities: 5,
      verdict_counts: { HIGH_PRIORITY: 2, RECOMMENDED: 3 },
      analyses_degraded: 1,
      sources_total: 7,
      sources_enabled: 1,
      sources_failing: 1,
      failing_sources: [
        {
          source_definition_id: 'source-1',
          name: 'Ashby Supabase',
          source_type: 'ashby',
          enabled: true,
          last_run_status: 'FAILED',
          last_run_finished_at: '2026-09-17T10:00:00Z',
          last_run_error: 'timeout',
        },
      ],
      pending_normalizations: 4,
      applications_active: null,
      follow_ups_due: null,
    })

    const overview = await getOverview()

    expect(overview.opportunitiesTotal).toBe(12)
    expect(overview.verdictCounts).toEqual({ HIGH_PRIORITY: 2, RECOMMENDED: 3 })
    expect(overview.failingSources[0].name).toBe('Ashby Supabase')
    expect(overview.applicationsActive).toBeNull()
    expect(overview.followUpsDue).toBeNull()
  })

  it('propaga o status quando a API falha', async () => {
    respond({}, 503)
    await expect(getOverview()).rejects.toThrow('503')
  })
})
