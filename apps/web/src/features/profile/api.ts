import { apiUrl } from '../../lib/api'

export interface ProfileSkill {
  canonicalName: string
  level: string | null
  experienceMonths: number | null
}

export interface ProfilePreferences {
  workModes: string[]
  contracts: string[]
  countries: string[]
  timezoneStartHour: number | null
  timezoneEndHour: number | null
  compensationMin: string | null
  compensationMax: string | null
  compensationCurrency: string | null
  compensationPeriod: string | null
  relocationAllowed: boolean
  sponsorshipRequired: boolean
}

export interface ProfileVersion {
  id: string
  number: number
  status: string
  profileLockVersion: number
  skills: ProfileSkill[]
  preferences: ProfilePreferences
}

export interface ProfileDraft {
  skills: ProfileSkill[]
  preferences: ProfilePreferences
}

export const emptyPreferences: ProfilePreferences = {
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
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function text(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function parseSkill(value: unknown): ProfileSkill | null {
  if (!isRecord(value) || typeof value.canonical_name !== 'string') return null
  return {
    canonicalName: value.canonical_name,
    level: text(value.level),
    experienceMonths: numberOrNull(value.experience_months),
  }
}

function parsePreferences(value: unknown): ProfilePreferences {
  if (!isRecord(value)) return emptyPreferences
  return {
    workModes: stringList(value.work_modes),
    contracts: stringList(value.contracts),
    countries: stringList(value.countries),
    timezoneStartHour: numberOrNull(value.timezone_start_hour),
    timezoneEndHour: numberOrNull(value.timezone_end_hour),
    // The API serialises Decimal as a JSON number or string depending on the value; both
    // are kept as text so no precision is lost on the way back.
    compensationMin: value.compensation_min === null ? null : String(value.compensation_min),
    compensationMax: value.compensation_max === null ? null : String(value.compensation_max),
    compensationCurrency: text(value.compensation_currency),
    compensationPeriod: text(value.compensation_period),
    relocationAllowed: value.relocation_allowed === true,
    sponsorshipRequired: value.sponsorship_required === true,
  }
}

function parseVersion(value: unknown): ProfileVersion | null {
  if (!isRecord(value) || typeof value.id !== 'string') return null
  return {
    id: value.id,
    number: numberOrNull(value.number) ?? 0,
    status: typeof value.status === 'string' ? value.status : 'UNKNOWN',
    profileLockVersion: numberOrNull(value.profile_lock_version) ?? 0,
    skills: (Array.isArray(value.skills) ? value.skills : [])
      .map(parseSkill)
      .filter((item): item is ProfileSkill => item !== null),
    preferences: parsePreferences(value.preferences),
  }
}

function serializePreferences(preferences: ProfilePreferences) {
  return {
    work_modes: preferences.workModes,
    contracts: preferences.contracts,
    countries: preferences.countries,
    timezone_start_hour: preferences.timezoneStartHour,
    timezone_end_hour: preferences.timezoneEndHour,
    compensation_min: preferences.compensationMin,
    compensation_max: preferences.compensationMax,
    compensation_currency: preferences.compensationCurrency,
    compensation_period: preferences.compensationPeriod,
    relocation_allowed: preferences.relocationAllowed,
    sponsorship_required: preferences.sponsorshipRequired,
  }
}

async function readVersion(response: Response, what: string): Promise<ProfileVersion> {
  if (!response.ok) throw new Error(`A API respondeu com ${response.status} ao ${what}.`)
  const version = parseVersion(await response.json())
  if (version === null) throw new Error('A API retornou um perfil inválido.')
  return version
}

/** The active version, or null when no profile has been created yet. */
export async function getActiveProfile(): Promise<ProfileVersion | null> {
  const response = await fetch(apiUrl('/profile'), {
    headers: { Accept: 'application/json' },
  })
  if (response.status === 404) return null
  return readVersion(response, 'carregar o perfil')
}

export async function listProfileVersions(): Promise<ProfileVersion[]> {
  const response = await fetch(apiUrl('/profile/versions'), {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`A API respondeu com ${response.status}.`)
  const body: unknown = await response.json()
  if (!Array.isArray(body)) throw new Error('A API retornou versões inválidas.')
  return body.map(parseVersion).filter((item): item is ProfileVersion => item !== null)
}

function post(path: string, payload: unknown) {
  return fetch(apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  })
}

/**
 * A relevant change is a new version, never an edit of the current one: create, publish,
 * activate. Each step carries the lock version the previous one returned, so a concurrent
 * edit fails with a conflict instead of silently winning.
 */
export async function saveProfileVersion(
  draft: ProfileDraft,
  expectedProfileVersion: number,
): Promise<ProfileVersion> {
  const created = await readVersion(
    await post('/profile/versions', {
      expected_profile_version: expectedProfileVersion,
      skills: draft.skills.map((skill) => ({
        canonical_name: skill.canonicalName,
        level: skill.level,
        experience_months: skill.experienceMonths,
      })),
      experiences: [],
      projects: [],
      preferences: serializePreferences(draft.preferences),
    }),
    'criar a versão',
  )

  const published = await readVersion(
    await post(`/profile/versions/${created.id}/publish`, {
      expected_profile_version: created.profileLockVersion,
    }),
    'publicar a versão',
  )

  return readVersion(
    await post(`/profile/versions/${published.id}/activate`, {
      expected_profile_version: published.profileLockVersion,
    }),
    'ativar a versão',
  )
}
