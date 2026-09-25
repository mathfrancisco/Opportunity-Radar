import { type FormEvent, useState } from 'react'
import { Button } from '../components/Button'
import { PageShell } from '../components/PageShell'
import { ConflictNotice, EmptyState, ErrorState, LoadingState } from '../components/states'
import { ConflictError } from '../lib/api'
import {
  emptyPreferences,
  type ProfilePreferences,
  type ProfileSkill,
  type ProfileVersion,
} from '../features/profile/api'
import {
  useActiveProfile,
  useProfileVersions,
  useSaveProfile,
} from '../features/profile/useProfile'

const workModes = ['REMOTE', 'HYBRID', 'ONSITE']
const contracts = ['FULL_TIME', 'PART_TIME', 'CONTRACT', 'INTERNSHIP']
const periods = ['YEAR', 'MONTH', 'HOUR']

// The API's PROFILE_ROLE_FAMILIES (`role-family-v1`). UNKNOWN is not offered: the Inbox
// always shows a posting with no classified area, so it is never a preference.
const roleFamilies = [
  { code: 'SOFTWARE_ENGINEERING', label: 'Engenharia de software' },
  { code: 'DATA', label: 'Dados' },
  { code: 'INFRASTRUCTURE', label: 'Infraestrutura' },
  { code: 'SECURITY', label: 'Segurança' },
  { code: 'QA', label: 'Qualidade (QA)' },
  { code: 'PRODUCT', label: 'Produto' },
  { code: 'DESIGN', label: 'Design' },
  { code: 'SALES', label: 'Vendas' },
  { code: 'MARKETING', label: 'Marketing' },
  { code: 'OPERATIONS', label: 'Operações' },
  { code: 'PEOPLE', label: 'Pessoas' },
  { code: 'FINANCE', label: 'Finanças' },
  { code: 'LEGAL', label: 'Jurídico' },
  { code: 'SUPPORT', label: 'Suporte' },
  { code: 'OTHER', label: 'Outras' },
]

function toList(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
}

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value]
}

function hourValue(value: string): number | null {
  if (value === '') return null
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed >= 0 && parsed <= 23 ? parsed : null
}

function count(total: number, one: string, many: string): string {
  return `${total} ${total === 1 ? one : many}`
}

/** YYYY-MM-DD as MM/YYYY, the precision a résumé uses. */
function month(date: string): string {
  return `${date.slice(5, 7)}/${date.slice(0, 4)}`
}

function period(startedOn: string | null, endedOn: string | null): string | null {
  if (startedOn === null) return null
  return `${month(startedOn)} – ${endedOn === null ? 'atual' : month(endedOn)}`
}

function Versions({ versions }: { versions: ProfileVersion[] }) {
  if (versions.length === 0) {
    return <p className="text-sm text-subtle">Nenhuma versão registrada.</p>
  }
  return (
    <ul className="grid gap-2">
      {[...versions]
        .sort((left, right) => right.number - left.number)
        .map((version) => (
          <li
            className="flex flex-wrap items-baseline justify-between gap-3 rounded-2xl border border-line bg-surface p-4 text-sm"
            key={version.id}
          >
            <span className="font-medium">Versão {version.number}</span>
            <span className="text-muted">
              {version.status} · {count(version.skills.length, 'skill', 'skills')} ·{' '}
              {count(version.experiences.length, 'experiência', 'experiências')} ·{' '}
              {count(version.projects.length, 'projeto', 'projetos')} ·{' '}
              {version.preferences.countries.join(', ') || 'sem países'}
            </span>
          </li>
        ))}
    </ul>
  )
}

/**
 * Experiences and projects are not edited on this page, but they are part of the profile:
 * showing them is how the operator sees that saving a preference carries them over.
 */
function PreservedHistory({ version }: { version: ProfileVersion }) {
  return (
    <section aria-labelledby="preserved-history" className="grid gap-3 text-sm">
      <div>
        <h2 className="font-medium" id="preserved-history">
          Experiências e projetos
        </h2>
        <p className="text-muted">
          Não são editados nesta tela e seguem sem mudança para a nova versão.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <h3 className="text-xs font-medium text-subtle">Experiências</h3>
          {version.experiences.length === 0 ? (
            <p className="mt-2 text-subtle">Nenhuma experiência registrada.</p>
          ) : (
            <ul className="mt-2 grid gap-2">
              {version.experiences.map((experience, index) => (
                <li
                  className="rounded-2xl border border-line bg-surface p-4"
                  key={`${experience.companyName}-${experience.startedOn}-${index}`}
                >
                  <span className="font-medium">{experience.title}</span>
                  <span className="block text-muted">
                    {experience.companyName} · {period(experience.startedOn, experience.endedOn)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="text-xs font-medium text-subtle">Projetos</h3>
          {version.projects.length === 0 ? (
            <p className="mt-2 text-subtle">Nenhum projeto registrado.</p>
          ) : (
            <ul className="mt-2 grid gap-2">
              {version.projects.map((project, index) => {
                const dates = period(project.startedOn, project.endedOn)
                return (
                  <li
                    className="rounded-2xl border border-line bg-surface p-4"
                    key={`${project.name}-${index}`}
                  >
                    <span className="font-medium">{project.name}</span>
                    {dates && <span className="block text-muted">{dates}</span>}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>
    </section>
  )
}

interface ProfileDraftState {
  versionId: string | null
  skillsText: string
  preferences: ProfilePreferences
}

function profileDraft(version: ProfileVersion | null | undefined): ProfileDraftState {
  return {
    versionId: version?.id ?? null,
    skillsText: version?.skills.map((skill) => skill.canonicalName).join(', ') ?? '',
    preferences: version?.preferences ?? emptyPreferences,
  }
}

function useProfileDraft(version: ProfileVersion | null | undefined) {
  const versionId = version?.id ?? null
  const [draft, setDraft] = useState(() => profileDraft(version))

  // A version is immutable. Resetting by key keeps the editor in sync when the active
  // version changes, without copying query data into state from an effect.
  if (draft.versionId !== versionId) {
    setDraft(profileDraft(version))
  }

  return {
    skillsText: draft.skillsText,
    preferences: draft.preferences,
    setSkillsText: (skillsText: string) =>
      setDraft((current) => ({ ...current, skillsText })),
    updatePreferences: (changes: Partial<ProfilePreferences>) =>
      setDraft((current) => ({
        ...current,
        preferences: { ...current.preferences, ...changes },
      })),
  }
}

export function ProfilePage() {
  const active = useActiveProfile()
  const versions = useProfileVersions()
  const save = useSaveProfile()
  const { skillsText, preferences, setSkillsText, updatePreferences } = useProfileDraft(active.data)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const current = active.data ?? null
    const known = new Map(current?.skills.map((skill) => [skill.canonicalName, skill] as const))
    // Only the names are edited here: a skill the profile already had keeps its level,
    // months and last use instead of coming back empty.
    const skills: ProfileSkill[] = toList(skillsText).map((name) => {
      const canonicalName = name.toLowerCase()
      return (
        known.get(canonicalName) ?? {
          canonicalName,
          level: null,
          lastUsedAt: null,
          experienceMonths: null,
        }
      )
    })
    save.mutate({
      draft: {
        skills,
        experiences: current?.experiences ?? [],
        projects: current?.projects ?? [],
        preferences,
      },
      expectedProfileVersion: current?.profileLockVersion ?? 0,
      baseVersionId: current?.id ?? null,
    })
  }

  function reload() {
    save.reset()
    void active.refetch()
    void versions.refetch()
  }

  return (
    <PageShell
      current="/profile"
      eyebrow="Critérios de decisão"
      title="Perfil e preferências"
      description="O que o matching considera ao avaliar uma vaga. Salvar cria uma nova versão e a ativa; as avaliações anteriores continuam apontando para a versão que as produziu."
    >
      <div>
        {active.isPending && (
          <LoadingState className="mt-8">Carregando perfil…</LoadingState>
        )}
        {active.isError && (
          <ErrorState className="mt-8" onRetry={() => void active.refetch()}>Não foi possível carregar o perfil.</ErrorState>
        )}
        {active.isSuccess && active.data === null && (
          <EmptyState className="mt-8">Nenhum perfil ativo ainda. Preencha o formulário para criar a primeira versão.</EmptyState>
        )}
      </div>

      {!active.isPending && !active.isError && (
        <form className="mt-8 grid gap-6" onSubmit={submit}>
          <label className="text-sm">
            <span className="font-medium">Skills</span>
            <span className="block text-muted">Separadas por vírgula.</span>
            <input
              className="mt-2 w-full rounded-xl border border-line-strong bg-surface px-4 py-3"
              onChange={(event) => setSkillsText(event.target.value)}
              placeholder="python, react, postgresql"
              value={skillsText}
            />
          </label>

          {active.data && <PreservedHistory version={active.data} />}

          <fieldset aria-describedby="role-families-hint">
            <legend className="text-sm font-medium">Áreas de interesse</legend>
            <p className="text-sm text-muted" id="role-families-hint">
              Nenhuma marcada vale como todas as áreas. Vagas sem área classificada aparecem
              sempre.
            </p>
            <div className="mt-2 flex flex-wrap gap-4">
              {roleFamilies.map((family) => (
                <label className="flex items-center gap-2 text-sm" key={family.code}>
                  <input
                    checked={preferences.targetRoleFamilies.includes(family.code)}
                    onChange={() =>
                      updatePreferences({
                        targetRoleFamilies: toggle(preferences.targetRoleFamilies, family.code),
                      })
                    }
                    type="checkbox"
                  />
                  {family.label}
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-sm font-medium">Modalidades aceitas</legend>
            <div className="mt-2 flex flex-wrap gap-4">
              {workModes.map((mode) => (
                <label className="flex items-center gap-2 text-sm" key={mode}>
                  <input
                    checked={preferences.workModes.includes(mode)}
                    onChange={() =>
                      updatePreferences({ workModes: toggle(preferences.workModes, mode) })
                    }
                    type="checkbox"
                  />
                  {mode}
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-sm font-medium">Contratos aceitos</legend>
            <div className="mt-2 flex flex-wrap gap-4">
              {contracts.map((contract) => (
                <label className="flex items-center gap-2 text-sm" key={contract}>
                  <input
                    checked={preferences.contracts.includes(contract)}
                    onChange={() =>
                      updatePreferences({ contracts: toggle(preferences.contracts, contract) })
                    }
                    type="checkbox"
                  />
                  {contract}
                </label>
              ))}
            </div>
          </fieldset>

          <label className="text-sm">
            <span className="font-medium">Países</span>
            <span className="block text-muted">
              Códigos ISO separados por vírgula. Lista vazia mantém o país da vaga como
              desconhecido, e desconhecido não reprova.
            </span>
            <input
              className="mt-2 w-full rounded-xl border border-line-strong bg-surface px-4 py-3"
              onChange={(event) =>
                updatePreferences({ countries: toList(event.target.value.toUpperCase()) })
              }
              placeholder="BR, PT"
              value={preferences.countries.join(', ')}
            />
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm">
              <span className="font-medium">Início da janela de timezone</span>
              <input
                className="mt-2 w-full rounded-xl border border-line-strong bg-surface px-4 py-3"
                max={23}
                min={0}
                onChange={(event) =>
                  updatePreferences({ timezoneStartHour: hourValue(event.target.value) })
                }
                type="number"
                value={preferences.timezoneStartHour ?? ''}
              />
            </label>
            <label className="text-sm">
              <span className="font-medium">Fim da janela de timezone</span>
              <input
                className="mt-2 w-full rounded-xl border border-line-strong bg-surface px-4 py-3"
                max={23}
                min={0}
                onChange={(event) =>
                  updatePreferences({ timezoneEndHour: hourValue(event.target.value) })
                }
                type="number"
                value={preferences.timezoneEndHour ?? ''}
              />
            </label>
          </div>

          <div className="grid gap-3 sm:grid-cols-4">
            <label className="text-sm">
              <span className="font-medium">Remuneração mínima</span>
              <input
                className="mt-2 w-full rounded-xl border border-line-strong bg-surface px-4 py-3"
                min={0}
                onChange={(event) =>
                  updatePreferences({ compensationMin: event.target.value || null })
                }
                type="number"
                value={preferences.compensationMin ?? ''}
              />
            </label>
            <label className="text-sm">
              <span className="font-medium">Remuneração máxima</span>
              <input
                className="mt-2 w-full rounded-xl border border-line-strong bg-surface px-4 py-3"
                min={0}
                onChange={(event) =>
                  updatePreferences({ compensationMax: event.target.value || null })
                }
                type="number"
                value={preferences.compensationMax ?? ''}
              />
            </label>
            <label className="text-sm">
              <span className="font-medium">Moeda</span>
              <input
                className="mt-2 w-full rounded-xl border border-line-strong bg-surface px-4 py-3"
                maxLength={3}
                onChange={(event) =>
                  updatePreferences({ compensationCurrency: event.target.value.toUpperCase() || null })
                }
                placeholder="USD"
                value={preferences.compensationCurrency ?? ''}
              />
            </label>
            <label className="text-sm">
              <span className="font-medium">Período</span>
              <select
                className="mt-2 w-full rounded-xl border border-line-strong bg-surface px-4 py-3"
                onChange={(event) =>
                  updatePreferences({ compensationPeriod: event.target.value || null })
                }
                value={preferences.compensationPeriod ?? ''}
              >
                <option value="">—</option>
                {periods.map((period) => (
                  <option key={period} value={period}>
                    {period}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input
                checked={preferences.relocationAllowed}
                onChange={(event) => updatePreferences({ relocationAllowed: event.target.checked })}
                type="checkbox"
              />
              Aceito relocação
            </label>
            <label className="flex items-center gap-2">
              <input
                checked={preferences.sponsorshipRequired}
                onChange={(event) => updatePreferences({ sponsorshipRequired: event.target.checked })}
                type="checkbox"
              />
              Preciso de patrocínio de visto
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button disabled={save.isPending} type="submit">
              {save.isPending ? 'Salvando…' : 'Salvar como nova versão e ativar'}
            </Button>
            {active.data && (
              <span className="text-xs text-muted">
                Versão ativa {active.data.number} · lock {active.data.profileLockVersion}
              </span>
            )}
          </div>

          {save.isError &&
            (save.error instanceof ConflictError ? (
              <ConflictNotice onReload={reload} reloadLabel="Recarregar o perfil">
                {save.error.message}
              </ConflictNotice>
            ) : (
              <p className="text-sm text-danger-ink">{save.error.message}</p>
            ))}
          {save.isSuccess && (
            <p className="text-sm text-success-ink">
              Versão {save.data.number} ativa. Avaliações antigas continuam apontando para
              a versão que as produziu.
            </p>
          )}
        </form>
      )}

      <section className="mt-section">
        <h2 className="text-section">Versões</h2>
        <div className="mt-4">
          {versions.isPending && (
            <p className="text-sm text-subtle">Carregando versões…</p>
          )}
          {versions.isError && (
            <p className="text-sm text-danger-ink">
              Não foi possível carregar o histórico de versões.
            </p>
          )}
          {versions.data && <Versions versions={versions.data} />}
        </div>
      </section>
    </PageShell>
  )
}
