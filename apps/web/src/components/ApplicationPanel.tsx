import { type FormEvent, useState } from 'react'
import { Button } from './Button'
import { Card } from './Card'
import { ConflictNotice, EmptyState, ErrorState, LoadingState } from './states'
import { ConflictError } from '../lib/api'
import { Field, controlClassName } from './Field'
import {
  type Application,
  type StageHistoryEntry,
  stageLabels,
  type ApplicationStage,
} from '../features/pipeline/api'
import {
  useOpportunityApplication,
  useSetNextAction,
  useStartApplication,
  useTransitionApplication,
} from '../features/pipeline/usePipeline'

function label(stage: string) {
  return stageLabels[stage as ApplicationStage] ?? stage
}

function formatDate(value: string | null) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString('pt-BR')
}

/** `datetime-local` wants `YYYY-MM-DDTHH:mm` in local time, not an ISO instant. */
function toLocalInput(value: string | null) {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return ''
  const offset = parsed.getTimezoneOffset() * 60_000
  return new Date(parsed.getTime() - offset).toISOString().slice(0, 16)
}

function History({ entries }: { entries: StageHistoryEntry[] }) {
  return (
    <ol className="mt-4 grid gap-2">
      {entries.map((entry) => (
        <li className="rounded-2xl border border-line bg-surface p-4 text-sm" key={entry.id}>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-medium">
              {entry.fromStage ? `${label(entry.fromStage)} → ` : ''}
              {label(entry.toStage)}
            </span>
            <span className="text-muted">{formatDate(entry.occurredAt)}</span>
          </div>
          {entry.notes && <p className="mt-2 text-subtle">{entry.notes}</p>}
        </li>
      ))}
    </ol>
  )
}

function Tracker({
  application,
  opportunityId,
  onReload,
}: {
  application: Application
  opportunityId: string
  /** Re-reads the candidacy after a conflict, so the operator decides on the new version. */
  onReload: () => void
}) {
  const transition = useTransitionApplication(opportunityId)
  const nextAction = useSetNextAction(opportunityId)
  const [actionText, setActionText] = useState(application.nextAction ?? '')
  const [actionDue, setActionDue] = useState(toLocalInput(application.nextActionAt))
  const closed = application.status === 'CLOSED'

  function saveNextAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    nextAction.mutate({
      applicationId: application.id,
      expectedVersion: application.version,
      nextAction: actionText.trim() || null,
      nextActionAt: actionDue ? new Date(actionDue).toISOString() : null,
    })
  }

  return (
    <Card>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <span className="text-lg font-semibold">{label(application.currentStage)}</span>
        <span className="text-sm text-muted">
          Iniciada em {formatDate(application.startedAt)}
          {application.appliedAt ? ` · enviada em ${formatDate(application.appliedAt)}` : ''}
          {closed ? ` · encerrada em ${formatDate(application.closedAt)}` : ''}
        </span>
      </div>

      {closed ? (
        <p className="mt-4 text-sm text-subtle">
          Candidatura encerrada como {label(application.outcome ?? 'CLOSED')}. O histórico
          continua disponível, e a oportunidade pode receber uma nova candidatura.
        </p>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap gap-2">
            {application.allowedTransitions.map((stage) => (
              <Button
                disabled={transition.isPending}
                key={stage}
                onClick={() =>
                  transition.mutate({
                    applicationId: application.id,
                    stage,
                    expectedVersion: application.version,
                  })
                }
                size="sm"
                variant="secondary"
              >
                {label(stage)}
              </Button>
            ))}
          </div>
          {transition.isError &&
            (transition.error instanceof ConflictError ? (
              <ConflictNotice className="mt-3" onReload={onReload}>
                {transition.error.message}
              </ConflictNotice>
            ) : (
              <p className="mt-3 text-sm text-danger-ink">{transition.error.message}</p>
            ))}

          <form className="mt-6 grid gap-3 sm:grid-cols-[2fr_1fr_auto]" onSubmit={saveNextAction}>
            <Field label="Próxima ação">
              <input
                className={controlClassName}
                onChange={(event) => setActionText(event.target.value)}
                placeholder="Enviar follow-up ao recrutador"
                value={actionText}
              />
            </Field>
            <Field label="Quando">
              <input
                className={controlClassName}
                onChange={(event) => setActionDue(event.target.value)}
                type="datetime-local"
                value={actionDue}
              />
            </Field>
            <Button className="self-end" disabled={nextAction.isPending} type="submit">
              Salvar
            </Button>
          </form>
          {nextAction.isError &&
            (nextAction.error instanceof ConflictError ? (
              <ConflictNotice className="mt-3" onReload={onReload}>
                {nextAction.error.message}
              </ConflictNotice>
            ) : (
              <p className="mt-3 text-sm text-danger-ink">{nextAction.error.message}</p>
            ))}
        </>
      )}

      {application.notes && (
        <p className="mt-4 text-sm text-subtle">{application.notes}</p>
      )}

      <h3 className="mt-6 text-sm font-semibold">Histórico</h3>
      <History entries={application.history} />
    </Card>
  )
}

export function ApplicationPanel({ opportunityId }: { opportunityId: string }) {
  const application = useOpportunityApplication(opportunityId)
  const start = useStartApplication(opportunityId)

  if (application.isPending) {
    return (
      <LoadingState>Carregando candidatura…</LoadingState>
    )
  }
  if (application.isError) {
    return (
      <ErrorState onRetry={() => void application.refetch()}>Não foi possível carregar a candidatura.</ErrorState>
    )
  }
  if (application.data === null) {
    return (
      <EmptyState>
        <div className="flex flex-wrap gap-3">
          <Button
            disabled={start.isPending}
            onClick={() => start.mutate({ opportunityId, stage: 'INTERESTED' })}
          >
            {start.isPending ? 'Iniciando…' : 'Registrar interesse'}
          </Button>
          <Button
            disabled={start.isPending}
            onClick={() => start.mutate({ opportunityId, stage: 'APPLIED' })}
            variant="secondary"
          >
            Já me candidatei
          </Button>
        </div>
        <p className="mt-3 text-sm text-subtle">
          A candidatura é acompanhada em separado da oportunidade: encerrar uma não
          encerra a outra.
        </p>
        {start.isError &&
          (start.error instanceof ConflictError ? (
            // 409 aqui é uma candidatura ativa que já existe: reler mostra qual é.
            <ConflictNotice className="mt-3" onReload={() => void application.refetch()}>
              {start.error.message}
            </ConflictNotice>
          ) : (
            <p className="mt-3 text-sm text-danger-ink">{start.error.message}</p>
          ))}
      </EmptyState>
    )
  }
  return (
    <Tracker
      application={application.data}
      onReload={() => void application.refetch()}
      opportunityId={opportunityId}
    />
  )
}
