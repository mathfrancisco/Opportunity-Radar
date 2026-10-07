import { useState } from 'react'
import { Link } from 'react-router-dom'
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
  const overdue = isOverdue(application.nextActionAt)
  return (
    <li className="break-words rounded-panel border border-l-4 border-line border-l-accent bg-surface p-3 text-sm">
      <Link
        className="font-medium underline decoration-accent decoration-2 underline-offset-4"
        to={`/opportunities/${application.opportunityId}`}
      >
        {application.opportunityTitle}
      </Link>
      <p className="mt-1 text-muted">{application.companyName ?? 'Empresa não informada'}</p>
      {application.nextAction ? (
        <p className={`mt-2 ${overdue ? 'text-danger-ink' : 'text-warning-ink'}`}>
          <span className="font-medium">Próxima ação:</span> {application.nextAction}
          {due ? ` · ${due}` : ''}
          {overdue ? ' · atrasada' : ''}
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
                <div className="rounded-panel border border-line bg-surface p-3" key={card}>
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
  const emptyStages = stages.filter((stage) => (byStage.get(stage) ?? []).length === 0)

  if (emptyStages.length === stages.length) {
    return <EmptyState>{emptyMessage}</EmptyState>
  }

  // Do `lg` para cima, todas as etapas na ordem do funil; a que não tem candidatura encolhe
  // para uma coluna estreita com nome e contagem. Abaixo, só as que têm candidatura, em
  // sequência, e a frase resume as ocultas para que a informação não se perca.
  return (
    <>
      <div
        aria-label="Candidaturas por etapa"
        className="grid gap-6 lg:flex lg:items-start lg:gap-4"
        role="group"
      >
        {stages.map((stage) => {
          const items = byStage.get(stage) ?? []
          const empty = items.length === 0
          return (
            <section
              aria-labelledby={`etapa-${stage}`}
              className={
                empty
                  ? 'max-lg:hidden lg:w-28 lg:flex-none lg:rounded-panel lg:border lg:border-dashed lg:border-line-strong lg:p-2'
                  : 'min-w-0 lg:flex-[1_1_9rem]'
              }
              data-empty={empty ? 'true' : undefined}
              key={stage}
            >
              <h3
                className={`flex justify-between gap-2 text-sm font-semibold ${
                  empty ? 'lg:flex-col lg:gap-0.5 lg:break-words' : 'border-b border-line pb-2'
                }`}
                id={`etapa-${stage}`}
              >
                <span>{stageLabels[stage]}</span>
                <span className="font-medium tabular-nums text-muted">{items.length}</span>
              </h3>
              {!empty && (
                <ul className="mt-3 grid gap-2">
                  {items.map((application) => (
                    <ApplicationCard application={application} key={application.id} />
                  ))}
                </ul>
              )}
            </section>
          )
        })}
      </div>
      {emptyStages.length > 0 && (
        <div className="mt-4 text-sm text-muted lg:hidden">
          <p>Sem candidaturas em:</p>
          <ul className="mt-1 list-disc pl-5">
            {emptyStages.map((stage) => (
              <li key={stage}>
                {stageLabels[stage]}: 0
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
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
      eyebrow="Decidir"
      title="Onde cada candidatura precisa de atenção?"
      description="Organize a próxima ação em cada etapa da sua busca. A oportunidade segue o ciclo dela; a candidatura segue o seu."
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line">
        <div aria-label="Visão das candidaturas" className="flex flex-wrap gap-5" role="group">
          {(
            [
              ['active', 'Em andamento', active.data?.total],
              ['closed', 'Encerradas', closed.data?.total],
            ] as const
          ).map(([value, label, total]) => (
            <button
              aria-pressed={view === value}
              className={`-mb-px border-b-[3px] px-0.5 py-2 text-sm font-semibold max-md:min-h-11 ${
                view === value
                  ? 'border-accent text-ink'
                  : 'border-transparent text-muted hover:text-ink'
              }`}
              key={value}
              onClick={() => setView(value)}
              type="button"
            >
              {label}
              {total !== undefined ? ` (${total})` : ''}
            </button>
          ))}
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
