import { type FormEvent, useState } from 'react'
import {
  type CompanyDetailSource,
  type ProposalOutcome,
  supportedAts,
} from '../features/companies/api'
import { useSaveCompanySource } from '../features/companies/useCompanies'
import { ConflictError, FieldError } from '../lib/api'
import { Button } from './Button'
import { Field, controlClassName } from './Field'
import { ConflictNotice, ErrorState } from './states'

const keyHints: Record<string, string> = {
  ashby: 'O slug em jobs.ashbyhq.com/<chave>.',
  lever: 'O slug em jobs.lever.co/<chave>.',
  greenhouse: 'O slug em boards.greenhouse.io/<chave>.',
}

interface CompanySourceFormProps {
  companyId: string
  /** Null registers a new ATS record; a source corrects that one. */
  source: CompanySourceFormSource | null
  onSaved: (proposalOutcome: ProposalOutcome) => void
  onCancel: () => void
  onReload: () => void
}

type CompanySourceFormSource = Pick<
  CompanyDetailSource,
  'id' | 'name' | 'url' | 'externalKey' | 'version'
>

/**
 * Registers or corrects where a company publishes its jobs.
 *
 * The record is what a source proposal is built from, and the evidence note is what a
 * reviewer reads before homologating that proposal — which is why it is required, and why
 * a correction asks for a new note instead of silently keeping the old one.
 */
export function CompanySourceForm({
  companyId,
  source,
  onSaved,
  onCancel,
  onReload,
}: CompanySourceFormProps) {
  const [sourceType, setSourceType] = useState(
    source && (supportedAts as readonly string[]).includes(source.name) ? source.name : 'greenhouse',
  )
  const [endpoint, setEndpoint] = useState(source?.url ?? '')
  const [externalKey, setExternalKey] = useState(source?.externalKey ?? '')
  const [evidenceNote, setEvidenceNote] = useState('')
  const [problems, setProblems] = useState<Record<string, string>>({})
  const save = useSaveCompanySource(companyId)

  const field = save.error instanceof FieldError ? save.error.field : null
  const problemFor = (key: string) =>
    problems[key] ?? (field === key ? save.error?.message : undefined)
  const placed = ['source_type', 'endpoint', 'external_key', 'evidence_note']
  const unplaced =
    save.error && !(save.error instanceof ConflictError) && !placed.includes(field ?? '')
      ? save.error.message
      : null

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const found: Record<string, string> = {}
    if (!/^https?:\/\/\S+$/i.test(endpoint.trim())) {
      found.endpoint = 'Use o endereço completo onde o board foi visto.'
    }
    if (!externalKey.trim()) found.external_key = 'A chave identifica o board no ATS.'
    if (!evidenceNote.trim()) {
      found.evidence_note = source
        ? 'Diga por que a correção é necessária e onde a nova chave foi confirmada.'
        : 'Diga onde e como o board foi confirmado.'
    }
    setProblems(found)
    if (Object.keys(found).length > 0) return
    save.mutate(
      {
        sourceId: source?.id ?? null,
        expectedVersion: source?.version ?? null,
        sourceType,
        endpoint: endpoint.trim(),
        externalKey: externalKey.trim(),
        evidenceNote: evidenceNote.trim(),
      },
      { onSuccess: (result) => onSaved(result.proposalOutcome) },
    )
  }

  const titleId = source ? `correct-source-${source.id}` : `new-source-${companyId}`

  return (
    <form
      aria-labelledby={titleId}
      className="rounded-2xl border border-line bg-surface p-5"
      noValidate
      onSubmit={submit}
    >
      <h3 className="font-semibold" id={titleId}>
        {source ? 'Corrigir o ATS registrado' : 'Registrar o ATS da empresa'}
      </h3>
      <p className="mt-1 max-w-2xl text-sm text-subtle">
        O registro não coleta nada. Ele é a base para propor uma fonte, e a fonte proposta
        nasce desabilitada: ainda passa por evidência confirmada, termos revisados e collector
        testado antes de executar.
      </p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field error={problemFor('source_type')} label="ATS">
          <select
            className={controlClassName}
            onChange={(event) => setSourceType(event.target.value)}
            value={sourceType}
          >
            {supportedAts.map((ats) => (
              <option key={ats} value={ats}>
                {ats}
              </option>
            ))}
          </select>
        </Field>
        <Field error={problemFor('external_key')} hint={keyHints[sourceType]} label="Chave no ATS">
          <input
            className={controlClassName}
            onChange={(event) => setExternalKey(event.target.value)}
            value={externalKey}
          />
        </Field>
        <Field
          className="sm:col-span-2"
          error={problemFor('endpoint')}
          hint="Onde o board foi visto. A tela não visita o endereço."
          label="Endereço do board"
        >
          <input
            className={controlClassName}
            inputMode="url"
            onChange={(event) => setEndpoint(event.target.value)}
            placeholder="https://"
            value={endpoint}
          />
        </Field>
        <Field
          className="sm:col-span-2"
          error={problemFor('evidence_note')}
          hint="É o que um revisor lê antes de homologar a fonte proposta."
          label={source ? 'Motivo da correção' : 'Nota de evidência'}
        >
          <textarea
            className={controlClassName}
            onChange={(event) => setEvidenceNote(event.target.value)}
            rows={3}
            value={evidenceNote}
          />
        </Field>
      </div>

      {save.error instanceof ConflictError && (
        <ConflictNotice
          className="mt-4"
          onReload={() => {
            save.reset()
            onReload()
          }}
        >
          O registro mudou depois que você o abriu. Recarregue para ver a versão atual — o que
          você digitou continua aqui.
        </ConflictNotice>
      )}
      {unplaced && <ErrorState className="mt-4">{unplaced}</ErrorState>}

      <div className="mt-4 flex flex-wrap gap-3">
        <Button disabled={save.isPending} type="submit">
          {save.isPending ? 'Salvando…' : source ? 'Salvar correção' : 'Registrar ATS'}
        </Button>
        <Button onClick={onCancel} variant="secondary">
          Cancelar
        </Button>
      </div>
    </form>
  )
}
