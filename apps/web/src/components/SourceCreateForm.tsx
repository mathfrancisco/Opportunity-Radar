import { type FormEvent, useState } from 'react'
import { type SourceDefinition, type SourceType, sourceTypes } from '../features/sources/api'
import { useCreateSource } from '../features/sources/useSources'
import { FieldError } from '../lib/api'
import { Button } from './Button'
import { Field, controlClassName } from './Field'
import { ErrorState } from './states'

/*
 * O que cada collector exige, espelhado do contrato e não reinventado: o servidor valida
 * cada campo de novo, e a recusa dele volta para o campo que a causou.
 */
interface ConfigField {
  key: string
  label: string
  required: boolean
  hint: string
  options?: readonly string[]
}

const configFields: Record<SourceType, ConfigField[]> = {
  ashby: [
    {
      key: 'board_identifier',
      label: 'Identificador do board',
      required: true,
      hint: 'O slug em jobs.ashbyhq.com/<identificador>.',
    },
    { key: 'company_name', label: 'Nome da empresa', required: false, hint: 'Opcional.' },
  ],
  lever: [
    {
      key: 'site_identifier',
      label: 'Identificador do site',
      required: true,
      hint: 'O slug em jobs.lever.co/<identificador>.',
    },
    {
      key: 'api_region',
      label: 'Região da API',
      required: true,
      hint: 'eu só para boards hospedados na instância europeia.',
      options: ['global', 'eu'],
    },
    { key: 'company_name', label: 'Nome da empresa', required: false, hint: 'Opcional.' },
  ],
  greenhouse: [
    {
      key: 'board_token',
      label: 'Token do board',
      required: true,
      hint: 'O slug em boards.greenhouse.io/<token>.',
    },
    { key: 'company_name', label: 'Nome da empresa', required: false, hint: 'Opcional.' },
  ],
  remotive: [],
  manual: [],
}

const typeLabels: Record<SourceType, string> = {
  ashby: 'Ashby',
  lever: 'Lever',
  greenhouse: 'Greenhouse',
  remotive: 'Remotive',
  manual: 'Manual (entrada avulsa de vaga)',
}

interface Draft {
  sourceType: SourceType
  name: string
  schedule: string
  priority: string
  requestsPerSecond: string
  maxRetries: string
  configuration: Record<string, string>
  extra: string
}

const emptyDraft: Draft = {
  sourceType: 'greenhouse',
  name: '',
  schedule: '',
  priority: '100',
  requestsPerSecond: '',
  maxRetries: '',
  configuration: { api_region: 'global' },
  extra: '',
}

/** `chave=valor`, uma por linha. Linhas vazias são ignoradas; o resto precisa do `=`. */
function parseExtra(value: string): Record<string, string> | string {
  const entries: Record<string, string> = {}
  for (const [index, raw] of value.split('\n').entries()) {
    const line = raw.trim()
    if (!line) continue
    const separator = line.indexOf('=')
    if (separator <= 0) return `Linha ${index + 1}: use chave=valor.`
    entries[line.slice(0, separator).trim()] = line.slice(separator + 1).trim()
  }
  return entries
}

type Problems = Partial<Record<string, string>>

function validate(draft: Draft): Problems {
  const problems: Problems = {}
  if (!draft.name.trim()) problems.name = 'Dê um nome à fonte.'
  for (const field of configFields[draft.sourceType]) {
    if (field.required && !draft.configuration[field.key]?.trim()) {
      problems[`configuration.${field.key}`] = `${field.label} é obrigatório para este tipo.`
    }
  }
  if (draft.schedule.trim() && draft.schedule.trim().split(/\s+/).length !== 5) {
    problems.schedule = 'Use as cinco partes de um crontab, como 0 */6 * * *.'
  }
  const priority = Number(draft.priority)
  if (!Number.isInteger(priority) || priority < 0) {
    problems.priority = 'Prioridade é um inteiro a partir de zero.'
  }
  for (const [key, value] of [
    ['rate_limit_policy.requests_per_second', draft.requestsPerSecond],
    ['rate_limit_policy.max_retries', draft.maxRetries],
  ] as const) {
    if (value.trim() && !Number.isFinite(Number(value))) problems[key] = 'Use um número.'
  }
  const extra = parseExtra(draft.extra)
  if (typeof extra === 'string') problems.configuration = extra
  return problems
}

interface SourceCreateFormProps {
  /** Starts the form on a type, as the manual intake does when no manual source exists. */
  initialType?: SourceType
  onCreated: (source: SourceDefinition) => void
  onCancel: () => void
}

export function SourceCreateForm({ initialType, onCreated, onCancel }: SourceCreateFormProps) {
  const [draft, setDraft] = useState<Draft>({
    ...emptyDraft,
    sourceType: initialType ?? emptyDraft.sourceType,
  })
  const [problems, setProblems] = useState<Problems>({})
  const create = useCreateSource()

  // Um erro do servidor com campo conhecido vai para o campo; o resto aparece uma vez,
  // acima das ações. O que foi digitado fica onde estava nos dois casos.
  const serverField =
    create.error instanceof FieldError ? create.error.field.split('.').slice(0, 2).join('.') : null
  const problemFor = (key: string) =>
    problems[key] ?? (serverField === key ? create.error?.message : undefined)
  const shownKeys = new Set([
    'name',
    'source_type',
    'schedule',
    'priority',
    'configuration',
    'rate_limit_policy.requests_per_second',
    'rate_limit_policy.max_retries',
    ...configFields[draft.sourceType].map((field) => `configuration.${field.key}`),
  ])
  const placed =
    serverField !== null && (shownKeys.has(serverField) || serverField === 'rate_limit_policy')
  const unplaced = create.error && !placed ? create.error.message : null

  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((current) => ({ ...current, [key]: value }))
  }

  function updateConfig(key: string, value: string) {
    setDraft((current) => ({
      ...current,
      configuration: { ...current.configuration, [key]: value },
    }))
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const found = validate(draft)
    setProblems(found)
    if (Object.keys(found).length > 0) return
    const extra = parseExtra(draft.extra) as Record<string, string>
    const configuration: Record<string, string> = { ...extra }
    for (const field of configFields[draft.sourceType]) {
      const value = draft.configuration[field.key]?.trim()
      if (value) configuration[field.key] = value
    }
    const rateLimitPolicy: Record<string, number> = {}
    if (draft.requestsPerSecond.trim()) {
      rateLimitPolicy.requests_per_second = Number(draft.requestsPerSecond)
    }
    if (draft.maxRetries.trim()) rateLimitPolicy.max_retries = Number(draft.maxRetries)
    create.mutate(
      {
        sourceType: draft.sourceType,
        name: draft.name.trim(),
        schedule: draft.schedule.trim() || null,
        priority: Number(draft.priority),
        rateLimitPolicy,
        configuration,
      },
      { onSuccess: onCreated },
    )
  }

  const external = draft.sourceType !== 'manual'

  return (
    <form
      aria-labelledby="new-source-title"
      className="rounded-2xl border border-line bg-surface p-5"
      noValidate
      onSubmit={submit}
    >
      <h2 className="text-section" id="new-source-title">
        Nova fonte
      </h2>
      <p className="mt-2 max-w-2xl text-sm text-subtle">
        {external
          ? 'A fonte nasce desabilitada. Para executar, ela precisa de evidência confirmada, data de revisão, termos revisados e collector testado — registrados na homologação, depois de criada.'
          : 'Fonte manual não coleta nada sozinha: ela recebe as vagas que você registrar. Nasce desabilitada; habilite-a na homologação para registrar vagas.'}
      </p>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <Field error={problemFor('source_type')} label="Tipo">
          <select
            className={controlClassName}
            onChange={(event) => update('sourceType', event.target.value as SourceType)}
            value={draft.sourceType}
          >
            {sourceTypes.map((type) => (
              <option key={type} value={type}>
                {typeLabels[type]}
              </option>
            ))}
          </select>
        </Field>
        <Field error={problemFor('name')} label="Nome">
          <input
            className={controlClassName}
            onChange={(event) => update('name', event.target.value)}
            required
            value={draft.name}
          />
        </Field>

        {configFields[draft.sourceType].map((field) => (
          <Field
            error={problemFor(`configuration.${field.key}`)}
            hint={field.hint}
            key={field.key}
            label={field.required ? field.label : `${field.label} (opcional)`}
          >
            {field.options ? (
              <select
                className={controlClassName}
                onChange={(event) => updateConfig(field.key, event.target.value)}
                value={draft.configuration[field.key] ?? field.options[0]}
              >
                {field.options.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            ) : (
              <input
                className={controlClassName}
                onChange={(event) => updateConfig(field.key, event.target.value)}
                required={field.required}
                value={draft.configuration[field.key] ?? ''}
              />
            )}
          </Field>
        ))}

        <Field
          error={problemFor('schedule')}
          hint="Crontab de cinco partes, no fuso do worker. Vazio: só executa quando pedido."
          label="Agendamento (opcional)"
        >
          <input
            className={controlClassName}
            onChange={(event) => update('schedule', event.target.value)}
            placeholder="0 */6 * * *"
            value={draft.schedule}
          />
        </Field>
        <Field
          error={problemFor('priority')}
          hint="Menor executa antes quando várias vencem juntas."
          label="Prioridade"
        >
          <input
            className={controlClassName}
            inputMode="numeric"
            min={0}
            onChange={(event) => update('priority', event.target.value)}
            type="number"
            value={draft.priority}
          />
        </Field>
        {external && (
          <>
            <Field
              error={
                problemFor('rate_limit_policy.requests_per_second') ??
                (serverField === 'rate_limit_policy' ? create.error?.message : undefined)
              }
              hint="Opcional. Vazio usa o padrão do collector."
              label="Requisições por segundo"
            >
              <input
                className={controlClassName}
                inputMode="decimal"
                onChange={(event) => update('requestsPerSecond', event.target.value)}
                value={draft.requestsPerSecond}
              />
            </Field>
            <Field
              error={problemFor('rate_limit_policy.max_retries')}
              hint="Opcional, de 0 a 5."
              label="Tentativas máximas"
            >
              <input
                className={controlClassName}
                inputMode="numeric"
                onChange={(event) => update('maxRetries', event.target.value)}
                value={draft.maxRetries}
              />
            </Field>
          </>
        )}
        <Field
          className="sm:col-span-2"
          error={problemFor('configuration')}
          hint="Opcional, chave=valor por linha. Segredo não entra aqui: o servidor recusa senha, token de acesso ou chave de API."
          label="Outros campos de configuração"
        >
          <textarea
            className={`${controlClassName} font-mono text-xs`}
            onChange={(event) => update('extra', event.target.value)}
            rows={2}
            value={draft.extra}
          />
        </Field>
      </div>

      {unplaced && (
        <ErrorState className="mt-5">{unplaced}</ErrorState>
      )}

      <div className="mt-5 flex flex-wrap gap-3">
        <Button disabled={create.isPending} type="submit">
          {create.isPending ? 'Criando…' : 'Criar fonte desabilitada'}
        </Button>
        <Button onClick={onCancel} variant="secondary">
          Cancelar
        </Button>
      </div>
    </form>
  )
}
