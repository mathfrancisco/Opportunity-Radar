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
      applied: false,
      search: '  plataforma  ',
      order: 'score',
    })

    expect(fetch).toHaveBeenCalledWith(
      '/api/inbox?offset=25&limit=25&order=score&verdict=HIGH_PRIORITY&verdict=RECOMMENDED' +
        '&minimum_score=70&work_mode=REMOTE&lifecycle_status=ACTIVE&only_assessed=true' +
        '&applied=false&search=plataforma',
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
          applied: false,
          application_id: null,
          application_stage: null,
          application_next_action_at: null,
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
    expect(page.items[0].applied).toBe(false)
    expect(page.items[0].applicationStage).toBeNull()
    expect(page.order).toBe('priority')
  })

  it('rejeita respostas sem uma coleção de itens', async () => {
    respond({ total: 0 })
    await expect(getInbox({ page: 1, pageSize: 25 })).rejects.toThrow('inbox inválida')
  })
})

describe('getOverview', () => {
  it('traz o pipeline por estágio e a janela de follow-up', async () => {
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
      applications_active: 3,
      applications_by_stage: { APPLIED: 2, INTERVIEW: 1 },
      follow_ups_due: 1,
      follow_up_window_days: 7,
    })

    const overview = await getOverview()

    expect(overview.opportunitiesTotal).toBe(12)
    expect(overview.verdictCounts).toEqual({ HIGH_PRIORITY: 2, RECOMMENDED: 3 })
    expect(overview.failingSources[0].name).toBe('Ashby Supabase')
    expect(overview.applicationsActive).toBe(3)
    expect(overview.applicationsByStage).toEqual({ APPLIED: 2, INTERVIEW: 1 })
    expect(overview.followUpsDue).toBe(1)
    expect(overview.followUpWindowDays).toBe(7)
  })

  it('propaga o status quando a API falha', async () => {
    respond({}, 503)
    await expect(getOverview()).rejects.toThrow('503')
  })
})
