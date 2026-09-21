import { afterEach, describe, expect, it, vi } from 'vitest'
import { getSourceHealth, getSourceRuns, runSource } from './api'

afterEach(() => vi.unstubAllGlobals())

function respond(body: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })),
  )
}

describe('getSourceHealth', () => {
  it('mantém ausência de execução como null, não como zero', async () => {
    respond({
      items: [
        {
          source_definition_id: 'source-1',
          name: 'Ashby Supabase',
          source_type: 'ashby',
          enabled: false,
          evidence_status: 'ats_identified',
          terms_reviewed: false,
          collector_local_tested: false,
          schedule: null,
          last_run_id: null,
          last_run_status: null,
          last_run_started_at: null,
          last_run_finished_at: null,
          last_run_duration_seconds: null,
          last_run_error_code: null,
          last_run_error: null,
          last_run_items_seen: null,
          last_run_items_persisted: null,
          last_run_items_skipped: null,
          last_run_items_invalid: null,
        },
      ],
      total: 1,
      failing: 0,
    })

    const health = await getSourceHealth()

    expect(fetch).toHaveBeenCalledWith('/api/source-health', expect.any(Object))
    expect(health.items[0].lastRunStatus).toBeNull()
    expect(health.items[0].lastRunItemsPersisted).toBeNull()
    expect(health.items[0].enabled).toBe(false)
    expect(health.failing).toBe(0)
  })

  it('rejeita respostas sem coleção de itens', async () => {
    respond({ total: 0 })
    await expect(getSourceHealth()).rejects.toThrow('fontes inválida')
  })
})

describe('getSourceRuns', () => {
  it('pede o histórico paginado daquela fonte', async () => {
    respond({ items: [], page: 1, page_size: 10, total: 0 })

    await getSourceRuns('source-1')

    expect(fetch).toHaveBeenCalledWith(
      '/api/source-runs?source_id=source-1&page=1&page_size=10',
      expect.any(Object),
    )
  })
})

describe('runSource', () => {
  it('devolve a execução criada', async () => {
    respond(
      {
        id: 'run-1',
        source_definition_id: 'source-1',
        source_name: 'CI manual intake',
        execution_trigger: 'ON_DEMAND',
        status: 'SUCCEEDED',
        started_at: '2026-09-17T10:00:00Z',
        finished_at: '2026-09-17T10:00:05Z',
        items_seen: 2,
        items_persisted: 2,
        items_skipped: 0,
        items_invalid: 0,
        http_requests: 0,
        retry_count: 0,
        rate_limit_events: 0,
        error_code: null,
        error_summary: null,
        checkpoint_before: null,
        checkpoint_after: null,
        correlation_id: 'dashboard-1',
      },
      201,
    )

    const run = await runSource('source-1')

    expect(run.status).toBe('SUCCEEDED')
    expect(run.executionTrigger).toBe('ON_DEMAND')
    expect(run.itemsPersisted).toBe(2)
  })

  it('propaga a mensagem do domínio quando a fonte está bloqueada', async () => {
    respond(
      { detail: { code: 'source_disabled', message: 'Source is disabled.' } },
      422,
    )
    await expect(runSource('source-1')).rejects.toThrow('Source is disabled.')
  })
})
