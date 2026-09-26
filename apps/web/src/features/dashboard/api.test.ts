import { afterEach, describe, expect, it, vi } from 'vitest'
import { getAnalysisMetrics, getInbox, getOverview, getSourceMetrics } from './api'

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

  it('preserva o aviso de avaliação desatualizada recebido da API', async () => {
    respond({
      items: [{
        opportunity_id: 'opportunity-1',
        opportunity_version: 3,
        assessment_id: 'assessment-1',
        assessment_opportunity_version: 2,
        assessment_profile_version_id: 'profile-old',
        current_profile_version_id: 'profile-current',
        is_stale: true,
      }],
      total: 1,
      offset: 0,
      limit: 25,
    })

    const page = await getInbox({ page: 1, pageSize: 25 })

    expect(page.items[0].isStale).toBe(true)
    expect(page.items[0].assessmentProfileVersionId).toBe('profile-old')
    expect(page.items[0].currentProfileVersionId).toBe('profile-current')
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

describe('getSourceMetrics', () => {
  it('preserva taxa ausente como ausente e não como zero', async () => {
    respond({
      generated_at: '2026-09-22T12:00:00Z',
      windows: [
        {
          window: '24h',
          since: '2026-09-21T12:00:00Z',
          until: '2026-09-22T12:00:00Z',
          sources: [
            {
              source_definition_id: 'source-1',
              name: 'Greenhouse Radar',
              source_type: 'greenhouse',
              enabled: true,
              schedule: '*/30 * * * *',
              coverage_state: 'NOT_RUN',
              runs: 0,
              runs_succeeded: 0,
              runs_partial: 0,
              runs_failed: 0,
              items_seen: 0,
              items_persisted: 0,
              items_skipped: 0,
              items_invalid: 0,
              latency_p95_seconds: null,
              error_rate: null,
              dedupe_rate: null,
              has_runs: false,
              errors_by_code: {},
              seniority: {
                counts: {},
                percentages: {},
                known: 0,
                unknown: 0,
                total: 0,
                mapping_versions: {},
                evidence: {},
              },
              incident_open: false,
            },
          ],
        },
      ],
    })

    const report = await getSourceMetrics()

    expect(report.windows).toHaveLength(1)
    const source = report.windows[0].sources[0]
    expect(source.hasRuns).toBe(false)
    expect(source.errorRate).toBeNull()
    expect(source.dedupeRate).toBeNull()
    expect(source.latencyP95Seconds).toBeNull()
    expect(source.coverageState).toBe('NOT_RUN')
  })

  it('traz senioridade desconhecida com a procedência do mapeamento', async () => {
    respond({
      generated_at: '2026-09-22T12:00:00Z',
      windows: [
        {
          window: '7d',
          since: '2026-09-15T12:00:00Z',
          until: '2026-09-22T12:00:00Z',
          sources: [
            {
              source_definition_id: 'source-1',
              coverage_state: 'SUCCEEDED',
              runs: 4,
              error_rate: 0.25,
              dedupe_rate: 0.5,
              has_runs: true,
              errors_by_code: { SOURCE_TIMEOUT: 1 },
              seniority: {
                counts: { SENIOR: 1, UNKNOWN: 3 },
                percentages: { SENIOR: 25, UNKNOWN: 75 },
                known: 1,
                unknown: 3,
                total: 4,
                mapping_versions: { 'seniority-v1': 4 },
                evidence: { title: 4 },
              },
              incident_open: true,
            },
          ],
        },
      ],
    })

    const report = await getSourceMetrics()

    const source = report.windows[0].sources[0]
    expect(source.seniority.unknown).toBe(3)
    expect(source.seniority.percentages.UNKNOWN).toBe(75)
    expect(source.seniority.mappingVersions).toEqual({ 'seniority-v1': 4 })
    expect(source.errorsByCode).toEqual({ SOURCE_TIMEOUT: 1 })
    expect(source.incidentOpen).toBe(true)
  })

  it('rejeita respostas sem janelas', async () => {
    respond({ generated_at: '2026-09-22T12:00:00Z' })
    await expect(getSourceMetrics()).rejects.toThrow('métricas de fontes inválidas')
  })
})

describe('getAnalysisMetrics', () => {
  it('lê os agregados por modelo e mantém null como indisponível', async () => {
    respond({
      generated_at: '2026-09-24T12:00:00Z',
      current_model: 'qwen3:8b-q4_K_M',
      pending: 4,
      windows: [
        {
          window: '7d',
          since: '2026-09-17T12:00:00Z',
          until: '2026-09-24T12:00:00Z',
          models: [
            {
              model_id: 'qwen3:8b-q4_K_M',
              analyses: 8,
              completed: 6,
              failed: 2,
              total_ms_p50: 3500,
              total_ms_p95: 5750,
              total_ms_p99: 5950,
              prompt_tokens_avg: 900,
              output_tokens_avg: 100,
              load_ms_avg: null,
              failure_rate: 0.25,
              failure_rates: { TIMEOUT: 0.125, SCHEMA_MISMATCH: 0.125 },
              reuse_rate: null,
            },
          ],
        },
        { window: '24h', since: '', until: '', models: [] },
      ],
    })

    const report = await getAnalysisMetrics()

    expect(fetch).toHaveBeenCalledWith('/api/analysis-metrics', expect.any(Object))
    expect(report.currentModel).toBe('qwen3:8b-q4_K_M')
    expect(report.pending).toBe(4)
    const [week, day] = report.windows
    expect(week.models[0]).toMatchObject({
      modelId: 'qwen3:8b-q4_K_M',
      totalMsP50: 3500,
      totalMsP95: 5750,
      loadMsAvg: null,
      failureRate: 0.25,
      failureRates: { TIMEOUT: 0.125, SCHEMA_MISMATCH: 0.125 },
      reuseRate: null,
    })
    expect(day.models).toEqual([])
  })

  it('recusa uma resposta sem janelas', async () => {
    respond({ current_model: 'x' })

    await expect(getAnalysisMetrics()).rejects.toThrow('métricas de análise inválidas')
  })

  it('lê o bloco ai com saldo diário, fallback e breaker por modelo', async () => {
    respond({
      generated_at: '2026-09-26T12:00:00Z',
      current_model: 'openai/gpt-oss-120b',
      pending: 0,
      windows: [{ window: '24h', since: '', until: '', models: [] }],
      ai: {
        state: 'enabled',
        window_hours: 24,
        cache_hit_rate: 0.35,
        by_model: [
          {
            model: 'openai/gpt-oss-120b',
            requests: 120,
            success_rate: 0.97,
            rate_limited_rate: 0.02,
            fallback_rate: 0.01,
            latency_ms_avg: 900,
            latency_ms_p95: 2100,
            prompt_tokens: 250000,
            completion_tokens: 50000,
            json_valid_rate: 0.99,
            breaker: 'closed',
            day_requests_used: 120,
            day_requests_limit: 850,
            day_tokens_used: 300000,
            day_tokens_limit: 170000,
          },
        ],
      },
    })

    const report = await getAnalysisMetrics()

    expect(report.ai.state).toBe('enabled')
    expect(report.ai.cacheHitRate).toBe(0.35)
    expect(report.ai.byModel[0]).toMatchObject({
      model: 'openai/gpt-oss-120b',
      dayRequestsUsed: 120,
      dayRequestsLimit: 850,
      fallbackRate: 0.01,
      breaker: 'closed',
    })
  })

  it('sem o bloco ai, responde um estado desligado em vez de falhar', async () => {
    respond({
      generated_at: '2026-09-26T12:00:00Z',
      current_model: 'x',
      pending: 0,
      windows: [{ window: '24h', since: '', until: '', models: [] }],
    })

    const report = await getAnalysisMetrics()

    expect(report.ai).toEqual({
      state: 'disabled',
      windowHours: 24,
      byModel: [],
      cacheHitRate: null,
    })
  })
})
