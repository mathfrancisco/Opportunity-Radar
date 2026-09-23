import { Link } from 'react-router-dom'
import { PageShell } from '../components/PageShell'
import { Bone, Skeleton } from '../components/skeletons'
import { EmptyState, ErrorState } from '../components/states'
import {
  type Application,
  type ApplicationStage,
  applicationStages,
  stageLabels,
} from '../features/pipeline/api'
import { useApplications } from '../features/pipeline/usePipeline'

const activeStages: ApplicationStage[] = [
  'INTERESTED',
  'APPLIED',
  'SCREENING',
  'INTERVIEW',
  'TECHNICAL',
  'FINAL',
  'OFFER',
]

function formatDate(value: string | null) {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toLocaleDateString('pt-BR')
}

function isOverdue(value: string | null) {
  if (!value) return false
  const parsed = new Date(value)
  return !Number.isNaN(parsed.getTime()) && parsed.getTime() <= Date.now()
}

function Card({ application }: { application: Application }) {
  const due = formatDate(application.nextActionAt)
  return (
    <li className="rounded-2xl border border-line bg-surface p-4 text-sm">
      <Link
        className="font-medium underline decoration-accent decoration-2 underline-offset-4"
        to={`/opportunities/${application.opportunityId}`}
      >
        Ver oportunidade
      </Link>
      {application.nextAction ? (
        <p
          className={`mt-2 ${
            isOverdue(application.nextActionAt) ? 'text-danger-ink' : 'text-subtle'
          }`}
        >
          {application.nextAction}
          {due ? ` · ${due}` : ''}
        </p>
      ) : (
        <p className="mt-2 text-muted">Sem próxima ação definida.</p>
      )}
      <p className="mt-2 text-xs text-muted">
        {application.history.length} movimento
        {application.history.length === 1 ? '' : 's'} no histórico
      </p>
    </li>
  )
}

/** Three stage columns with two cards each: the board's shape before the board. */
function BoardSkeleton() {
  return (
    <Skeleton label="Carregando candidaturas…">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((column) => (
          <div key={column}>
            <div className="flex items-center justify-between py-1">
              <Bone className="w-28" />
              <Bone className="w-4" />
            </div>
            <div className="mt-3 grid gap-2">
              {[0, 1].map((card) => (
                <div className="rounded-2xl border border-line bg-surface p-4" key={card}>
                  <Bone className="w-24" />
                  <Bone className="mt-3 w-4/5" />
                  <Bone className="mt-3 w-1/2" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Skeleton>
  )
}

function Board({ applications }: { applications: Application[] }) {
  const byStage = new Map<string, Application[]>()
  for (const application of applications) {
    byStage.set(application.currentStage, [
      ...(byStage.get(application.currentStage) ?? []),
      application,
    ])
  }
  const columns = activeStages.filter((stage) => (byStage.get(stage) ?? []).length > 0)

  if (columns.length === 0) {
    return (
      <EmptyState>Nenhuma candidatura ativa. Comece pela inbox: abra uma oportunidade e registre o
        interesse.</EmptyState>
    )
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {columns.map((stage) => (
        <section key={stage}>
          <h2 className="flex items-baseline justify-between text-sm font-semibold">
            <span>{stageLabels[stage]}</span>
            <span className="text-muted">{(byStage.get(stage) ?? []).length}</span>
          </h2>
          <ul className="mt-3 grid gap-2">
            {(byStage.get(stage) ?? []).map((application) => (
              <Card application={application} key={application.id} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

function Closed({ applications }: { applications: Application[] }) {
  if (applications.length === 0) return null
  const counts = applicationStages
    .filter((stage) => !activeStages.includes(stage))
    .map((stage) => ({
      stage,
      total: applications.filter((item) => item.currentStage === stage).length,
    }))
    .filter((entry) => entry.total > 0)

  return (
    <section className="mt-section">
      <h2 className="text-section">Encerradas</h2>
      <ul className="mt-4 flex flex-wrap gap-3">
        {counts.map((entry) => (
          <li
            className="rounded-full border border-line-strong bg-surface px-4 py-2 text-sm"
            key={entry.stage}
          >
            <span className="text-subtle">{stageLabels[entry.stage]}</span>{' '}
            <span className="font-semibold">{entry.total}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function PipelinePage() {
  const active = useApplications({ status: 'ACTIVE' })
  const closed = useApplications({ status: 'CLOSED' })

  return (
    <PageShell
      current="/applications"
      eyebrow="Acompanhamento"
      title="Candidaturas"
      description="Cada candidatura com o estágio em que está e o que você deve fazer a seguir. A oportunidade segue o ciclo dela; a candidatura segue o seu."
    >
      <div className="mt-8">
        {active.isPending && (
          <BoardSkeleton />
        )}
        {active.isError && (
          <ErrorState onRetry={() => void active.refetch()}>Não foi possível carregar as candidaturas.</ErrorState>
        )}
        {active.data && <Board applications={active.data.items} />}
      </div>

      {closed.data && <Closed applications={closed.data.items} />}
    </PageShell>
  )
}
