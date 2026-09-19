import { afterEach, describe, expect, it, vi } from 'vitest'
import { getActiveProfile, saveProfileVersion } from './api'

afterEach(() => vi.unstubAllGlobals())

const preferences = {
  work_modes: ['REMOTE'],
  contracts: ['FULL_TIME'],
  countries: ['BR'],
  timezone_start_hour: 9,
  timezone_end_hour: 18,
  compensation_min: 100000,
  compensation_max: null,
  compensation_currency: 'USD',
  compensation_period: 'YEAR',
  relocation_allowed: false,
  sponsorship_required: false,
}

function version(id: string, lock: number, status: string) {
  return {
    id,
    number: 1,
    status,
    profile_lock_version: lock,
    skills: [{ canonical_name: 'python', level: null, experience_months: null }],
    experiences: [],
    projects: [],
    preferences,
  }
}

describe('getActiveProfile', () => {
  it('devolve null quando ainda não existe perfil', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('null', { status: 404 })))
    await expect(getActiveProfile()).resolves.toBeNull()
  })

  it('preserva a remuneração como texto para não perder precisão', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(version('version-1', 3, 'ACTIVE')), { status: 200 }),
      ),
    )

    const active = await getActiveProfile()

    expect(active?.profileLockVersion).toBe(3)
    expect(active?.preferences.compensationMin).toBe('100000')
    expect(active?.preferences.compensationMax).toBeNull()
    expect(active?.skills[0].canonicalName).toBe('python')
  })
})

describe('saveProfileVersion', () => {
  it('encadeia criar, publicar e ativar carregando o lock de cada passo', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(version('version-2', 4, 'DRAFT')), { status: 201 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(version('version-2', 5, 'PUBLISHED')), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(version('version-2', 6, 'ACTIVE')), { status: 200 }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const saved = await saveProfileVersion(
      {
        skills: [{ canonicalName: 'python', level: null, experienceMonths: null }],
        preferences: {
          workModes: ['REMOTE'],
          contracts: ['FULL_TIME'],
          countries: ['BR'],
          timezoneStartHour: 9,
          timezoneEndHour: 18,
          compensationMin: '100000',
          compensationMax: null,
          compensationCurrency: 'USD',
          compensationPeriod: 'YEAR',
          relocationAllowed: false,
          sponsorshipRequired: false,
        },
      },
      3,
    )

    expect(saved.status).toBe('ACTIVE')
    expect(fetchMock).toHaveBeenCalledTimes(3)
    const [create, publish, activate] = fetchMock.mock.calls
    expect(create[0]).toBe('/api/profile/versions')
    expect(JSON.parse(create[1].body).expected_profile_version).toBe(3)
    expect(publish[0]).toBe('/api/profile/versions/version-2/publish')
    expect(JSON.parse(publish[1].body).expected_profile_version).toBe(4)
    expect(activate[0]).toBe('/api/profile/versions/version-2/activate')
    expect(JSON.parse(activate[1].body).expected_profile_version).toBe(5)
  })

  it('para no conflito em vez de seguir publicando', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('"conflict"', { status: 409 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      saveProfileVersion(
        {
          skills: [],
          preferences: {
            workModes: [],
            contracts: [],
            countries: [],
            timezoneStartHour: null,
            timezoneEndHour: null,
            compensationMin: null,
            compensationMax: null,
            compensationCurrency: null,
            compensationPeriod: null,
            relocationAllowed: false,
            sponsorshipRequired: false,
          },
        },
        1,
      ),
    ).rejects.toThrow('409')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
