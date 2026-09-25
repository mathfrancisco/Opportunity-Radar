import { afterEach, describe, expect, it, vi } from 'vitest'
import { ConflictError } from '../../lib/api'
import { emptyPreferences, getActiveProfile, saveProfileVersion } from './api'

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
  target_role_families: ['SOFTWARE_ENGINEERING', 'DATA'],
}

const skills = [
  { canonical_name: 'python', level: 'advanced', last_used_at: '2026-08-01', experience_months: 60 },
]

const experiences = [
  {
    company_name: 'Acme',
    title: 'Backend Engineer',
    started_on: '2022-01-01',
    ended_on: '2024-06-30',
    summary: 'APIs de pagamento.',
  },
  {
    company_name: 'Globex',
    title: 'Staff Engineer',
    started_on: '2024-07-01',
    ended_on: null,
    summary: null,
  },
]

const projects = [
  {
    name: 'Radar',
    started_on: '2025-01-01',
    ended_on: null,
    description: 'Radar de vagas.',
    url: 'https://example.com/radar',
  },
]

function version(id: string, lock: number, status: string) {
  return {
    id,
    number: 1,
    status,
    profile_lock_version: lock,
    skills,
    experiences,
    projects,
    preferences,
  }
}

function respond(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

describe('getActiveProfile', () => {
  it('devolve null quando ainda não existe perfil', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('null', { status: 404 })))
    await expect(getActiveProfile()).resolves.toBeNull()
  })

  it('preserva a remuneração como texto para não perder precisão', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respond(version('version-1', 3, 'ACTIVE'))))

    const active = await getActiveProfile()

    expect(active?.profileLockVersion).toBe(3)
    expect(active?.preferences.compensationMin).toBe('100000')
    expect(active?.preferences.compensationMax).toBeNull()
    expect(active?.skills[0].canonicalName).toBe('python')
  })

  it('lê experiências, projetos, datas das skills e áreas de interesse', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respond(version('version-1', 3, 'ACTIVE'))))

    const active = await getActiveProfile()

    expect(active?.skills[0].lastUsedAt).toBe('2026-08-01')
    expect(active?.experiences).toEqual([
      {
        companyName: 'Acme',
        title: 'Backend Engineer',
        startedOn: '2022-01-01',
        endedOn: '2024-06-30',
        summary: 'APIs de pagamento.',
      },
      {
        companyName: 'Globex',
        title: 'Staff Engineer',
        startedOn: '2024-07-01',
        endedOn: null,
        summary: null,
      },
    ])
    expect(active?.projects).toEqual([
      {
        name: 'Radar',
        startedOn: '2025-01-01',
        endedOn: null,
        description: 'Radar de vagas.',
        url: 'https://example.com/radar',
      },
    ])
    expect(active?.preferences.targetRoleFamilies).toEqual(['SOFTWARE_ENGINEERING', 'DATA'])
  })
})

describe('saveProfileVersion', () => {
  it('devolve o perfil lido inteiro num só pedido que cria, publica e ativa', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(respond(version('version-1', 3, 'ACTIVE')))
      .mockResolvedValueOnce(respond(version('version-2', 4, 'ACTIVE'), 201))
    vi.stubGlobal('fetch', fetchMock)

    const active = await getActiveProfile()
    if (active === null) throw new Error('O perfil ativo deveria existir.')
    // Only the country changes; everything else must travel back as it was read.
    const saved = await saveProfileVersion(
      {
        skills: active.skills,
        experiences: active.experiences,
        projects: active.projects,
        preferences: { ...active.preferences, countries: ['PT'] },
      },
      active.profileLockVersion,
      active.id,
    )

    expect(saved.status).toBe('ACTIVE')
    expect(saved.profileLockVersion).toBe(4)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const [path, init] = fetchMock.mock.calls[1]
    expect(path).toBe('/api/profile/versions')
    expect(JSON.parse(init.body)).toEqual({
      expected_profile_version: 3,
      base_version_id: 'version-1',
      activate: true,
      skills,
      experiences,
      projects,
      preferences: { ...preferences, countries: ['PT'], compensation_min: '100000' },
    })
  })

  it('para no conflito e pede para recarregar a versão atual', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response('"conflict"', { status: 409 }))
    vi.stubGlobal('fetch', fetchMock)

    const saving = saveProfileVersion(
      { skills: [], experiences: [], projects: [], preferences: emptyPreferences },
      1,
      'version-1',
    )

    // Um conflito é tipado: a tela oferece reler o perfil, e não repetir a escrita.
    await expect(saving).rejects.toBeInstanceOf(ConflictError)
    await expect(saving).rejects.toThrow(/nada foi gravado.*Recarregue para ver a versão atual/)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
