import { type FormEvent, useState } from 'react'
import {
  type CompanyDetail,
  type CompanyInput,
  companyPriorities,
  radarStatuses,
} from '../features/companies/api'
import { ConflictError, FieldError } from '../lib/api'
import { Button } from './Button'
import { Field, controlClassName } from './Field'
import { ConflictNotice, ErrorState } from './states'

const priorityLabels: Record<CompanyInput['priority'], string> = {
  high: 'Alta',
  normal: 'Normal',
  low: 'Baixa',
}

const statusLabels: Record<CompanyInput['radarStatus'], string> = {
  active: 'Ativa no radar',
  paused: 'Pausada',
}

interface Draft {
  name: string
  domain: string
  priority: CompanyInput['priority']
  radarStatus: CompanyInput['radarStatus']
  aliases: string
}

function draftFrom(company: CompanyDetail | null): Draft {
  if (!company) return { name: '', domain: '', priority: 'normal', radarStatus: 'active', aliases: '' }
  return {
    name: company.name,
    domain: company.domain ?? '',
    priority: (companyPriorities as readonly string[]).includes(company.priority)
      ? (company.priority as CompanyInput['priority'])
      : 'normal',
    radarStatus: (radarStatuses as readonly string[]).includes(company.status)
      ? (company.status as CompanyInput['radarStatus'])
      : 'active',
    aliases: company.aliases.join('\n'),
  }
}

function inputFrom(draft: Draft): CompanyInput {
  return {
    name: draft.name.trim(),
    domain: draft.domain.trim() || null,
    priority: draft.priority,
    radarStatus: draft.radarStatus,
    aliases: draft.aliases
      .split('\n')
      .map((alias) => alias.trim())
      .filter(Boolean),
  }
}

interface CompanyFormProps {
  /** Null creates; a company edits that record at its current version. */
  company: CompanyDetail | null
  pending: boolean
  error: Error | null
  onSubmit: (input: CompanyInput) => void
  onCancel: () => void
  onReload?: () => void
}

/**
 * Create or edit a company. Identity is the server's to decide: the form only says, before
 * sending, that a known name will answer with the existing company, and shows afterwards
 * which of the two happened.
 */
export function CompanyForm({
  company,
  pending,
  error,
  onSubmit,
  onCancel,
  onReload,
}: CompanyFormProps) {
  const [draft, setDraft] = useState<Draft>(() => draftFrom(company))
  const [nameProblem, setNameProblem] = useState<string | null>(null)
  const field = error instanceof FieldError ? error.field : null
  const problemFor = (key: string) => (field === key ? error?.message : undefined)
  const placedFields = ['name', 'domain', 'priority', 'radar_status', 'aliases']
  const unplaced =
    error && !(error instanceof ConflictError) && !placedFields.includes(field ?? '')
      ? error.message
      : null

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!draft.name.trim()) {
      setNameProblem('Dê o nome da empresa.')
      return
    }
    setNameProblem(null)
    onSubmit(inputFrom(draft))
  }

  const titleId = company ? `edit-company-${company.id}` : 'new-company-title'

  return (
    <form
      aria-labelledby={titleId}
      className="rounded-2xl border border-line bg-surface p-5"
      noValidate
      onSubmit={submit}
    >
      <h2 className="text-section" id={titleId}>
        {company ? 'Editar empresa' : 'Nova empresa'}
      </h2>
      {!company && (
        <p className="mt-2 max-w-2xl text-sm text-subtle">
          Um nome que o catálogo já conhece — pelo nome ou por um alias — não cria uma segunda
          empresa: a existente responde, e o nome digitado fica registrado como alias dela.
        </p>
      )}
      {company && (
        <p className="mt-2 max-w-2xl text-sm text-subtle">
          Renomear mantém o nome atual como alias, para que a próxima importação ou a próxima
          vaga que o citar continue chegando aqui.
        </p>
      )}

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <Field error={nameProblem ?? problemFor('name')} label="Nome">
          <input
            className={controlClassName}
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
            required
            value={draft.name}
          />
        </Field>
        <Field
          error={problemFor('domain')}
          hint="Opcional. Um endereço colado vira só o domínio: https://www.acme.com/jobs → acme.com."
          label="Domínio"
        >
          <input
            className={controlClassName}
            inputMode="url"
            onChange={(event) => setDraft({ ...draft, domain: event.target.value })}
            value={draft.domain}
          />
        </Field>
        <Field error={problemFor('priority')} label="Prioridade">
          <select
            className={controlClassName}
            onChange={(event) =>
              setDraft({ ...draft, priority: event.target.value as Draft['priority'] })
            }
            value={draft.priority}
          >
            {companyPriorities.map((priority) => (
              <option key={priority} value={priority}>
                {priorityLabels[priority]}
              </option>
            ))}
          </select>
        </Field>
        <Field error={problemFor('radar_status')} label="Status no radar">
          <select
            className={controlClassName}
            onChange={(event) =>
              setDraft({ ...draft, radarStatus: event.target.value as Draft['radarStatus'] })
            }
            value={draft.radarStatus}
          >
            {radarStatuses.map((status) => (
              <option key={status} value={status}>
                {statusLabels[status]}
              </option>
            ))}
          </select>
        </Field>
        <Field
          className="sm:col-span-2"
          error={problemFor('aliases')}
          hint="Um por linha. Outros nomes pelos quais a empresa aparece em vagas."
          label="Aliases"
        >
          <textarea
            className={controlClassName}
            onChange={(event) => setDraft({ ...draft, aliases: event.target.value })}
            rows={3}
            value={draft.aliases}
          />
        </Field>
      </div>

      {error instanceof ConflictError && (
        <ConflictNotice className="mt-5" onReload={onReload}>
          A empresa mudou depois que você a abriu. Recarregue para ver a versão atual — o que
          você digitou continua aqui; confira e salve de novo.
        </ConflictNotice>
      )}
      {unplaced && <ErrorState className="mt-5">{unplaced}</ErrorState>}

      <div className="mt-5 flex flex-wrap gap-3">
        <Button disabled={pending} type="submit">
          {pending ? 'Salvando…' : company ? 'Salvar empresa' : 'Cadastrar empresa'}
        </Button>
        <Button onClick={onCancel} variant="secondary">
          Cancelar
        </Button>
      </div>
    </form>
  )
}
