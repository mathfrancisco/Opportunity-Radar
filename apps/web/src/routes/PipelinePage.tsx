import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Chip } from '../components/Chip'
import { PageShell } from '../components/PageShell'
import { Pagination } from '../components/Pagination'
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
const pageSize = 12

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

function ApplicationCard({ application }: { application: Application }) {
  const due = formatDate(application.nextActionAt)
  return (
    <Card as="li" className="text-sm">
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
    </Card>
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
                <div className="rounded-control border border-line bg-surface p-5" key={card}>
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

function Board({
  applications,
  stages,
  emptyMessage,
}: {
  applications: Application[]
  stages: ApplicationStage[]
  emptyMessage: string
}) {
  const byStage = new Map<string, Application[]>()
  for (const application of applications) {
    byStage.set(application.currentStage, [
      ...(byStage.get(application.currentStage) ?? []),
      application,
    ])
  }
  const columns = stages.filter((stage) => (byStage.get(stage) ?? []).length > 0)

  if (columns.length === 0) {
    return (
      <EmptyState>{emptyMessage}</EmptyState>
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
              <ApplicationCard application={application} key={application.id} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

const closedStages = applicationStages.filter((stage) => !activeStages.includes(stage))

export function PipelinePage() {
  const [activePage, setActivePage] = useState(1)
  const [closedPage, setClosedPage] = useState(1)
  const active = useApplications({
    status: 'ACTIVE',
    limit: pageSize,
    offset: (activePage - 1) * pageSize,
  })
  const closed = useApplications({
    status: 'CLOSED',
    limit: pageSize,
    offset: (closedPage - 1) * pageSize,
  })
  const [view, setView] = useState<'active' | 'closed'>('active')
  const selected = view === 'active' ? active : closed
  const selectedPage = view === 'active' ? activePage : closedPage
  const setSelectedPage = view === 'active' ? setActivePage : setClosedPage
  const selectedStages = view === 'active' ? activeStages : closedStages
  const selectedDescription =
    view === 'active'
      ? 'Candidaturas em andamento, organizadas pela etapa atual.'
      : 'Candidaturas finalizadas, preservadas para consulta do histórico.'

  return (
    <PageShell
      current="/applications"
      eyebrow="Acompanhamento"
      title="Candidaturas"
      description="Cada candidatura com o estágio em que está e o que você deve fazer a seguir. A oportunidade segue o ciclo dela; a candidatura segue o seu."
    >
      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <div aria-label="Visão das candidaturas" className="flex flex-wrap gap-2" role="group">
          <Button
            aria-pressed={view === 'active'}
            onClick={() => setView('active')}
            size="sm"
            variant={view === 'active' ? 'primary' : 'secondary'}
          >
            Em andamento{active.data ? ` (${active.data.total})` : ''}
          </Button>
          <Button
            aria-pressed={view === 'closed'}
            onClick={() => setView('closed')}
            size="sm"
            variant={view === 'closed' ? 'primary' : 'secondary'}
          >
            Encerradas{closed.data ? ` (${closed.data.total})` : ''}
          </Button>
        </div>
        {selected.data && <Chip>{selected.data.total} no total</Chip>}
      </div>

      <section aria-live="polite" className="mt-5" id="pipeline-view">
        <h2 className="text-section">{view === 'active' ? 'Em andamento' : 'Encerradas'}</h2>
        <p className="mt-1 text-sm text-muted">{selectedDescription}</p>
        <div className="mt-5">
          {selected.isPending && <BoardSkeleton />}
          {selected.isError && (
            <ErrorState onRetry={() => void selected.refetch()}>
              Não foi possível carregar as candidaturas {view === 'active' ? 'em andamento' : 'encerradas'}.
            </ErrorState>
          )}
          {selected.data && (
            <>
              <Board
                applications={selected.data.items}
                emptyMessage={
                  view === 'active'
                    ? 'Nenhuma candidatura em andamento. Comece pela inbox: abra uma oportunidade e registre o interesse.'
                    : 'Nenhuma candidatura encerrada até agora.'
                }
                stages={selectedStages}
              />
              <Pagination
                className="mt-6"
                itemLabel="candidaturas"
                label={`Paginação de candidaturas ${view === 'active' ? 'em andamento' : 'encerradas'}`}
                onPageChange={setSelectedPage}
                page={selectedPage}
                pageSize={selected.data.limit || pageSize}
                total={selected.data.total}
              />
            </>
          )}
        </div>
      </section>
    </PageShell>
  )
}
