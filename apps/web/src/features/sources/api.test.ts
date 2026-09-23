import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createSource,
  getSourceHealth,
  getSourceRuns,
  normalizeRun,
  probeSource,
  runSource,
  submitManualRun,
  updateSourceControls,
} from './api'

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

function sentBody(): Record<string, unknown> {
  const call = vi.mocked(fetch).mock.calls[0]
  return JSON.parse(String((call[1] as RequestInit).body)) as Record<string, unknown>
}

const sourceBody = {
  id: 'source-9',
  source_type: 'greenhouse',
  name: 'Acme board',
  enabled: false,
  schedule: null,
  priority: 100,
  configuration: { board_token: 'acme' },
  evidence_status: 'unverified',
  reviewed_at: null,
  terms_reviewed: false,
  collector_local_tested: false,
  version: 1,
}

describe('createSource', () => {
  it('nunca envia habilitação: a fonte nasce desabilitada', async () => {
    respond(sourceBody, 201)

    const source = await createSource({
      sourceType: 'greenhouse',
      name: 'Acme board',
      schedule: null,
      priority: 100,
      rateLimitPolicy: {},
      configuration: { board_token: 'acme' },
    })

    const body = sentBody()
    expect(body).not.toHaveProperty('enabled')
    expect(body).not.toHaveProperty('evidence_status')
    expect(body.configuration).toEqual({ board_token: 'acme' })
    expect(source.enabled).toBe(false)
    expect(source.version).toBe(1)
  })
})

describe('updateSourceControls', () => {
  it('envia a versão lida como expected_version', async () => {
    respond({ ...sourceBody, terms_reviewed: true, version: 2 })

    await updateSourceControls('source-9', {
      enabled: false,
      termsReviewed: true,
      collectorLocalTested: false,
      reviewedAt: null,
      expectedVersion: 1,
    })

    expect(sentBody()).toMatchObject({ expected_version: 1, terms_reviewed: true })
  })
})

describe('entrada manual', () => {
  it('envia as entradas em modo manual, com o arquivo em base64', async () => {
    respond({ id: 'run-1', status: 'SUCCEEDED', items_seen: 1, items_persisted: 1 }, 201)

    await submitManualRun('source-manual', [
      {
        kind: 'FILE',
        value: 'vaga.txt',
        contentBase64: 'VmFnYQ==',
        contentType: 'text/plain',
        metadata: { title: 'Vaga' },
      },
    ])

    const body = sentBody()
    expect(body.mode).toBe('MANUAL')
    expect(body.inputs).toEqual([
      {
        kind: 'FILE',
        value: 'vaga.txt',
        content_base64: 'VmFnYQ==',
        content_type: 'text/plain',
        metadata: { title: 'Vaga' },
      },
    ])
  })

  it('lê o desfecho da normalização item a item', async () => {
    respond({
      source_run_id: 'run-1',
      items: [
        {
          raw_item_id: 'raw-1',
          canonical_url: null,
          result: {
            status: 'SUCCEEDED',
            identity_decision: 'NEW',
            error_summary: null,
            opportunity_id: 'opp-1',
          },
          opportunity: { title: 'Senior Python Engineer' },
        },
        {
          raw_item_id: 'raw-2',
          canonical_url: null,
          result: {
            status: 'FAILED',
            identity_decision: null,
            error_summary: 'title is required',
            opportunity_id: null,
          },
          opportunity: null,
        },
      ],
    })

    const items = await normalizeRun('run-1')

    expect(fetch).toHaveBeenCalledWith(
      '/api/opportunities/normalizations/runs/run-1',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(items[0]).toMatchObject({ opportunityId: 'opp-1', opportunityTitle: 'Senior Python Engineer' })
    expect(items[1]).toMatchObject({ status: 'FAILED', errorSummary: 'title is required' })
  })
})

describe('probeSource', () => {
  it('lê a sonda que falhou como resposta, não como erro', async () => {
    respond({
      probe: {
        id: 'probe-1',
        status: 'FAILED',
        items_seen: 0,
        http_requests: 1,
        error_code: 'SOURCE_NOT_FOUND',
        detail: 'board not found',
        evidence_recorded: false,
        finished_at: '2026-09-23T12:00:00Z',
      },
      source: sourceBody,
    })

    const { probe, source } = await probeSource('source-9', 1)

    expect(sentBody()).toEqual({ expected_version: 1 })
    expect(probe).toMatchObject({ status: 'FAILED', errorCode: 'SOURCE_NOT_FOUND' })
    expect(source.evidenceStatus).toBe('unverified')
  })
})
