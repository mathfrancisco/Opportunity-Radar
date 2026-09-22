import { type FormEvent, useState } from 'react'
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
}: {
  application: Application
  opportunityId: string
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
    <div className="rounded-2xl border border-line bg-surface p-5">
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
              <button
                className="rounded-xl border border-line-strong px-4 py-2 text-sm font-medium hover:border-ink disabled:cursor-not-allowed disabled:opacity-40"
                disabled={transition.isPending}
                key={stage}
                onClick={() =>
                  transition.mutate({
                    applicationId: application.id,
                    stage,
                    expectedVersion: application.version,
                  })
                }
                type="button"
              >
                {label(stage)}
              </button>
            ))}
          </div>
          {transition.isError && (
            <p className="mt-3 text-sm text-danger-ink">{transition.error.message}</p>
          )}

          <form className="mt-6 grid gap-3 sm:grid-cols-[2fr_1fr_auto]" onSubmit={saveNextAction}>
            <label className="text-sm">
              <span className="text-muted">Próxima ação</span>
              <input
                className="mt-1 w-full rounded-xl border border-line-strong bg-surface px-4 py-2"
                onChange={(event) => setActionText(event.target.value)}
                placeholder="Enviar follow-up ao recrutador"
                value={actionText}
              />
            </label>
            <label className="text-sm">
              <span className="text-muted">Quando</span>
              <input
                className="mt-1 w-full rounded-xl border border-line-strong bg-surface px-4 py-2"
                onChange={(event) => setActionDue(event.target.value)}
                type="datetime-local"
                value={actionDue}
              />
            </label>
            <button
              className="self-end rounded-xl bg-ink px-5 py-2 text-sm font-semibold text-white hover:bg-ink-hover disabled:opacity-40"
              disabled={nextAction.isPending}
              type="submit"
            >
              Salvar
            </button>
          </form>
          {nextAction.isError && (
            <p className="mt-3 text-sm text-danger-ink">{nextAction.error.message}</p>
          )}
        </>
      )}

      {application.notes && (
        <p className="mt-4 text-sm text-subtle">{application.notes}</p>
      )}

      <h3 className="mt-6 text-sm font-semibold">Histórico</h3>
      <History entries={application.history} />
    </div>
  )
}

export function ApplicationPanel({ opportunityId }: { opportunityId: string }) {
  const application = useOpportunityApplication(opportunityId)
  const start = useStartApplication(opportunityId)

  if (application.isPending) {
    return (
      <p className="rounded-2xl bg-info-surface p-5 text-info-ink">Carregando candidatura…</p>
    )
  }
  if (application.isError) {
    return (
      <div className="rounded-2xl bg-danger-surface-strong p-5 text-danger-ink">
        <p>Não foi possível carregar a candidatura.</p>
        <button
          className="mt-3 font-semibold underline"
          onClick={() => void application.refetch()}
          type="button"
        >
          Tentar novamente
        </button>
      </div>
    )
  }
  if (application.data === null) {
    return (
      <div className="rounded-2xl border border-dashed border-line-strong p-5">
        <div className="flex flex-wrap gap-3">
          <button
            className="rounded-xl bg-ink px-5 py-3 text-sm font-semibold text-white hover:bg-ink-hover disabled:opacity-40"
            disabled={start.isPending}
            onClick={() => start.mutate({ opportunityId, stage: 'INTERESTED' })}
            type="button"
          >
            {start.isPending ? 'Iniciando…' : 'Registrar interesse'}
          </button>
          <button
            className="rounded-xl border border-line-strong px-5 py-3 text-sm font-medium hover:border-ink disabled:opacity-40"
            disabled={start.isPending}
            onClick={() => start.mutate({ opportunityId, stage: 'APPLIED' })}
            type="button"
          >
            Já me candidatei
          </button>
        </div>
        <p className="mt-3 text-sm text-subtle">
          A candidatura é acompanhada em separado da oportunidade: encerrar uma não
          encerra a outra.
        </p>
        {start.isError && (
          <p className="mt-3 text-sm text-danger-ink">{start.error.message}</p>
        )}
      </div>
    )
  }
  return <Tracker application={application.data} opportunityId={opportunityId} />
}
