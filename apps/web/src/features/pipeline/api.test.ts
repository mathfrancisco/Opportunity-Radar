import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  getApplicationForOpportunity,
  setNextAction,
  startApplication,
  transitionApplication,
} from './api'

afterEach(() => vi.unstubAllGlobals())

const application = {
  id: 'application-1',
  opportunity_id: 'opportunity-1',
  profile_version_id: 'profile-1',
  current_stage: 'INTERESTED',
  status: 'ACTIVE',
  outcome: null,
  next_action: null,
  next_action_at: null,
  notes: null,
  applied_at: null,
  started_at: '2026-09-18T12:00:00Z',
  closed_at: null,
  version: 1,
  allowed_transitions: ['APPLIED', 'CLOSED', 'REJECTED', 'WITHDRAWN'],
  history: [
    {
      id: 'history-1',
      from_stage: null,
      to_stage: 'INTERESTED',
      reason: 'started',
      source: 'MANUAL',
      notes: null,
      occurred_at: '2026-09-18T12:00:00Z',
    },
  ],
}

function respond(body: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })),
  )
}

describe('startApplication', () => {
  it('cria a candidatura no estágio informado', async () => {
    respond(application, 201)

    const created = await startApplication({
      opportunityId: 'opportunity-1',
      stage: 'INTERESTED',
    })

    expect(fetch).toHaveBeenCalledWith(
      '/api/applications',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(created.currentStage).toBe('INTERESTED')
    expect(created.allowedTransitions).toContain('APPLIED')
    expect(created.history).toHaveLength(1)
    expect(created.history[0].fromStage).toBeNull()
  })

  it('propaga o conflito quando já existe candidatura ativa', async () => {
    respond(
      {
        detail: {
          code: 'duplicate_active_application',
          message: 'this opportunity already has an active application for this profile',
        },
      },
      409,
    )
    await expect(
      startApplication({ opportunityId: 'opportunity-1' }),
    ).rejects.toThrow('already has an active application')
  })
})

describe('transitionApplication', () => {
  it('envia o estágio alvo com a versão esperada', async () => {
    respond({ ...application, current_stage: 'APPLIED', version: 2 })

    const moved = await transitionApplication({
      applicationId: 'application-1',
      stage: 'APPLIED',
      expectedVersion: 1,
    })

    const [url, init] = (fetch as unknown as { mock: { calls: [string, RequestInit][] } })
      .mock.calls[0]
    expect(url).toBe('/api/applications/application-1/transitions')
    expect(JSON.parse(String(init.body))).toEqual({
      stage: 'APPLIED',
      expected_version: 1,
      notes: null,
    })
    expect(moved.version).toBe(2)
  })

  it('propaga a recusa de uma transição ilegal', async () => {
    respond(
      {
        detail: {
          code: 'invalid_stage_transition',
          message: 'cannot move an application from INTERESTED to OFFER',
        },
      },
      422,
    )
    await expect(
      transitionApplication({
        applicationId: 'application-1',
        stage: 'OFFER',
        expectedVersion: 1,
      }),
    ).rejects.toThrow('cannot move an application')
  })
})

describe('setNextAction', () => {
  it('grava a próxima ação com a data', async () => {
    respond({
      ...application,
      version: 2,
      next_action: 'Enviar follow-up',
      next_action_at: '2026-09-20T12:00:00Z',
    })

    const updated = await setNextAction({
      applicationId: 'application-1',
      expectedVersion: 1,
      nextAction: 'Enviar follow-up',
      nextActionAt: '2026-09-20T12:00:00Z',
    })

    expect(updated.nextAction).toBe('Enviar follow-up')
    expect(updated.nextActionAt).toBe('2026-09-20T12:00:00Z')
  })
})

describe('getApplicationForOpportunity', () => {
  it('devolve null quando a oportunidade não tem candidatura ativa', async () => {
    respond({ items: [], total: 0, offset: 0, limit: 1 })

    await expect(getApplicationForOpportunity('opportunity-1')).resolves.toBeNull()
    expect(fetch).toHaveBeenCalledWith(
      '/api/applications?limit=1&application_status=ACTIVE&opportunity_id=opportunity-1',
      expect.any(Object),
    )
  })

  it('devolve a candidatura ativa quando existe', async () => {
    respond({ items: [application], total: 1, offset: 0, limit: 1 })
    const found = await getApplicationForOpportunity('opportunity-1')
    expect(found?.id).toBe('application-1')
  })
})
