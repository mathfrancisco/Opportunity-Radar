import { apiUrl, requestFailure } from '../../lib/api'

export interface ProfileSkill {
  canonicalName: string
  level: string | null
  /** ISO date (YYYY-MM-DD). */
  lastUsedAt: string | null
  experienceMonths: number | null
}

export interface ProfileExperience {
  companyName: string
  title: string
  /** ISO dates (YYYY-MM-DD); no end date means the position is current. */
  startedOn: string
  endedOn: string | null
  summary: string | null
}

export interface ProfileProject {
  name: string
  startedOn: string | null
  endedOn: string | null
  description: string | null
  url: string | null
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
  /** `role-family-v1` codes. Empty means every area. */
  targetRoleFamilies: string[]
}

export interface ProfileVersion {
  id: string
  number: number
  status: string
  profileLockVersion: number
  skills: ProfileSkill[]
  experiences: ProfileExperience[]
  projects: ProfileProject[]
  preferences: ProfilePreferences
}

/** A whole snapshot: what is not in the draft is not in the saved version. */
export interface ProfileDraft {
  skills: ProfileSkill[]
  experiences: ProfileExperience[]
  projects: ProfileProject[]
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
  targetRoleFamilies: [],
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
    lastUsedAt: text(value.last_used_at),
    experienceMonths: numberOrNull(value.experience_months),
  }
}

function parseExperience(value: unknown): ProfileExperience | null {
  if (
    !isRecord(value) ||
    typeof value.company_name !== 'string' ||
    typeof value.title !== 'string' ||
    typeof value.started_on !== 'string'
  ) {
    return null
  }
  return {
    companyName: value.company_name,
    title: value.title,
    startedOn: value.started_on,
    endedOn: text(value.ended_on),
    summary: text(value.summary),
  }
}

function parseProject(value: unknown): ProfileProject | null {
  if (!isRecord(value) || typeof value.name !== 'string') return null
  return {
    name: value.name,
    startedOn: text(value.started_on),
    endedOn: text(value.ended_on),
    description: text(value.description),
    url: text(value.url),
  }
}

function parseList<T>(value: unknown, parse: (item: unknown) => T | null): T[] {
  return (Array.isArray(value) ? value : [])
    .map(parse)
    .filter((item): item is T => item !== null)
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
    targetRoleFamilies: stringList(value.target_role_families),
  }
}

function parseVersion(value: unknown): ProfileVersion | null {
  if (!isRecord(value) || typeof value.id !== 'string') return null
  return {
    id: value.id,
    number: numberOrNull(value.number) ?? 0,
    status: typeof value.status === 'string' ? value.status : 'UNKNOWN',
    profileLockVersion: numberOrNull(value.profile_lock_version) ?? 0,
    skills: parseList(value.skills, parseSkill),
    experiences: parseList(value.experiences, parseExperience),
    projects: parseList(value.projects, parseProject),
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
    target_role_families: preferences.targetRoleFamilies,
  }
}

function serializeDraft(draft: ProfileDraft) {
  return {
    skills: draft.skills.map((skill) => ({
      canonical_name: skill.canonicalName,
      level: skill.level,
      last_used_at: skill.lastUsedAt,
      experience_months: skill.experienceMonths,
    })),
    experiences: draft.experiences.map((experience) => ({
      company_name: experience.companyName,
      title: experience.title,
      started_on: experience.startedOn,
      ended_on: experience.endedOn,
      summary: experience.summary,
    })),
    projects: draft.projects.map((project) => ({
      name: project.name,
      started_on: project.startedOn,
      ended_on: project.endedOn,
      description: project.description,
      url: project.url,
    })),
    preferences: serializePreferences(draft.preferences),
  }
}

async function readVersion(response: Response, what: string): Promise<ProfileVersion> {
  if (!response.ok) {
    // A versão do perfil é o lock: um 409 aqui é sempre outra edição, nunca uma falha de rede.
    throw requestFailure(
      response.status,
      response.status === 409
        ? `Outra edição mudou o perfil enquanto você editava, então nada foi gravado ao ${what}. Recarregue para ver a versão atual.`
        : `A API respondeu com ${response.status} ao ${what}.`,
    )
  }
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
 * A relevant change is a new version, never an edit of the current one. One request
 * creates, publishes and activates it in a single transaction, so a failure leaves no
 * draft or published version behind and the active one untouched.
 *
 * The draft is the whole snapshot — experiences, projects and skill dates included — and
 * `baseVersionId` names the version it was read from, so the server fills anything this
 * client does not know about from it instead of erasing it. The lock version makes a
 * concurrent edit fail with a conflict instead of silently winning.
 */
export async function saveProfileVersion(
  draft: ProfileDraft,
  expectedProfileVersion: number,
  baseVersionId: string | null,
): Promise<ProfileVersion> {
  return readVersion(
    await post('/profile/versions', {
      expected_profile_version: expectedProfileVersion,
      base_version_id: baseVersionId,
      activate: true,
      ...serializeDraft(draft),
    }),
    'salvar a versão',
  )
}
