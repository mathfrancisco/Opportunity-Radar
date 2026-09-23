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
              {version.status} · {version.skills.length} skill
              {version.skills.length === 1 ? '' : 's'} ·{' '}
              {version.preferences.countries.join(', ') || 'sem países'}
            </span>
          </li>
        ))}
    </ul>
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
    const skills: ProfileSkill[] = toList(skillsText).map((name) => ({
      canonicalName: name.toLowerCase(),
      level: null,
      experienceMonths: null,
    }))
    save.mutate({
      draft: { skills, preferences },
      expectedProfileVersion: active.data?.profileLockVersion ?? 0,
    })
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
              <ConflictNotice onReload={() => void active.refetch()}>
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

      <section className="mt-10">
        <h2 className="text-lg font-semibold">Versões</h2>
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
