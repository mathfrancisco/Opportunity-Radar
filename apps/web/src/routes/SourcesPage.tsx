import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../components/Button'
import { PrimaryText, SecondaryText, DateTimeCell } from '../components/cells'
import { DataTable } from '../components/DataTable'
import { FilterBar } from '../components/FilterBar'
import { FilterPill } from '../components/FilterPill'
import { ManualIntakePanel } from '../components/ManualIntakePanel'
import { PageShell } from '../components/PageShell'
import { PanelSkeleton, TableSkeleton } from '../components/skeletons'
import { EmptyState, ErrorState } from '../components/states'
import { SourceControlsPanel } from '../components/SourceControlsPanel'
import { SourceCreateForm } from '../components/SourceCreateForm'
import { StatusBadge } from '../components/StatusBadge'
import { Unavailable } from '../components/Unavailable'
import { SearchInput } from '../components/SearchInput'
import { type SourceHealth, type SourceType } from '../features/sources/api'
import { runStatusLabels, runStatusTones } from '../features/sources/states'
import {
  useRunSource,
  useSourceCoverage,
  useSourceHealth,
  useSourceRuns,
} from '../features/sources/useSources'

function formatDate(value: string | null) {
  if (!value) return <Unavailable reason="nunca executada" />
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? (
    <Unavailable reason="data inválida" />
  ) : (
    parsed.toLocaleString('pt-BR')
  )
}

function formatDuration(seconds: number | null) {
  if (seconds === null) return <Unavailable reason="nunca executada" />
  if (seconds < 60) return `${seconds.toFixed(1)} s`
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`
}

function RunStatus({ status }: { status: string | null }) {
  return (
    <StatusBadge
      absent="Nunca executada"
      labels={runStatusLabels}
      tones={runStatusTones}
      value={status}
    />
  )
}

function RunHistory({ sourceId, id }: { sourceId: string; id: string }) {
  const runs = useSourceRuns(sourceId)

  if (runs.isPending) {
    return <p className="mt-4 text-sm text-subtle">Carregando execuções…</p>
  }
  if (runs.isError) {
    return (
      <p className="mt-4 text-sm text-danger-ink">
        Não foi possível carregar o histórico desta fonte.
      </p>
    )
  }
  if (!runs.data || runs.data.length === 0) {
    return <p className="mt-4 text-sm text-subtle">Nenhuma execução registrada.</p>
  }
  return (
    <DataTable
      caption="Execuções recentes desta fonte"
      className="mt-4"
      columns={['Status', 'Origem', 'Início', 'Itens', 'Erro']}
      id={id}
      stickyFirstColumn
    >
      {runs.data.map((run) => (
            <tr key={run.id}>
              <td>
                <RunStatus status={run.status} />
              </td>
              <td>{run.executionTrigger}</td>
              <td>{formatDate(run.startedAt)}</td>
              <td>
                {run.itemsPersisted} persistidos / {run.itemsSeen} vistos
                {run.itemsSkipped > 0 && ` · ${run.itemsSkipped} repetidos`}
                {run.itemsInvalid > 0 && ` · ${run.itemsInvalid} inválidos`}
              </td>
              <td className="text-subtle">
                {run.errorCode ? (
                  `${run.errorCode}: ${run.errorSummary ?? ''}`
                ) : (
                  <Unavailable reason="sem erro" />
                )}
              </td>
            </tr>
      ))}
    </DataTable>
  )
}

const sourceColumns = ['Fonte', 'Estado', 'Última execução', 'Itens', 'Agendamento', 'Ações']

const sourceStateOptions = [
  { value: 'all', label: 'Todas' },
  { value: 'failing', label: 'Com falha ou parcial' },
  { value: 'enabled', label: 'Habilitadas' },
] as const

type SourceStateFilter = (typeof sourceStateOptions)[number]['value']

function matchesSourceState(source: SourceHealth, state: SourceStateFilter) {
  if (state === 'failing') {
    return source.lastRunStatus === 'FAILED' || source.lastRunStatus === 'PARTIAL'
  }
  if (state === 'enabled') return source.enabled
  return true
}

/**
 * One source as a table row, plus a full-width row under it while a panel (controls,
 * manual intake, run history) is open. Each row owns its `useRunSource`, so the result of
 * "Executar agora" stays with the source that was run.
 */
function SourceRows({
  source,
  expanded,
  onToggle,
}: {
  source: SourceHealth
  expanded: boolean
  onToggle: () => void
}) {
  const run = useRunSource()
  const blocked = !source.enabled
  const manual = source.sourceType === 'manual'
  const runHistoryId = `runs-${source.sourceDefinitionId}`
  const controlsId = `controls-${source.sourceDefinitionId}`
  const intakeId = `intake-panel-${source.sourceDefinitionId}`
  const [panel, setPanel] = useState<'controls' | 'intake' | null>(null)
  const toggle = (next: 'controls' | 'intake') =>
    setPanel((current) => (current === next ? null : next))
  const seniority = Object.entries(source.seniorityCounts)
  const showPanels = panel !== null || expanded

  return (
    <>
      <tr>
        <td className="min-w-48 align-top">
          <PrimaryText>{source.name}</PrimaryText>
          <SecondaryText>{source.sourceType}</SecondaryText>
          {source.lastRunError && (
            <p className="break-anywhere mt-2 rounded-control border border-danger-line bg-danger-surface p-2 text-caption text-danger-ink">
              {source.lastRunErrorCode ? `${source.lastRunErrorCode}: ` : ''}
              {source.lastRunError}
            </p>
          )}
          {run.isError && <p className="mt-2 text-caption text-danger-ink">{run.error.message}</p>}
          {run.isSuccess && (
            <p className="mt-2 text-caption text-subtle">
              Execução {run.data.status} · {run.data.itemsPersisted} itens persistidos.
            </p>
          )}
        </td>
        <td className="align-top">
          <RunStatus status={source.lastRunStatus} />
          <SecondaryText className="mt-1">
            {source.enabled ? 'Habilitada' : 'Desabilitada'} · evidência {source.evidenceStatus}
          </SecondaryText>
          <SecondaryText>
            termos {source.termsReviewed ? 'revisados' : 'não revisados'} · collector{' '}
            {source.collectorLocalTested ? 'homologado' : 'não homologado'}
          </SecondaryText>
        </td>
        <td className="align-top">
          {source.lastRunFinishedAt ? (
            <DateTimeCell value={source.lastRunFinishedAt} />
          ) : (
            <Unavailable reason="nunca executada" />
          )}
          <SecondaryText className="mt-1">{formatDuration(source.lastRunDurationSeconds)}</SecondaryText>
        </td>
        <td className="align-top">
          {source.lastRunItemsPersisted === null ? (
            <Unavailable reason="nunca executada" />
          ) : (
            <PrimaryText>{source.lastRunItemsPersisted}</PrimaryText>
          )}
          <SecondaryText>
            {seniority.length === 0
              ? 'sem vagas normalizadas'
              : seniority.map(([level, count]) => `${level} ${count}`).join(' · ')}
          </SecondaryText>
        </td>
        <td className="align-top text-muted">{source.schedule ?? 'manual'}</td>
        <td className="min-w-48 align-top">
          <div className="flex flex-wrap items-center gap-2">
            {manual ? (
              <Button
                aria-controls={intakeId}
                aria-expanded={panel === 'intake'}
                disabled={blocked}
                onClick={() => toggle('intake')}
                size="sm"
                variant="secondary"
              >
                Registrar vaga
              </Button>
            ) : (
              <Button
                disabled={blocked || run.isPending}
                onClick={() => run.mutate(source.sourceDefinitionId)}
                size="sm"
                variant="secondary"
              >
                {run.isPending ? 'Executando…' : 'Executar agora'}
              </Button>
            )}
            <details className="relative">
              <summary className="h-8 cursor-pointer rounded-control border border-line-strong bg-surface px-3 py-1.5 text-sm font-medium text-ink hover:border-ink max-md:min-h-11">
                Mais ações
              </summary>
              <div className="mt-2 flex min-w-48 flex-wrap items-center gap-2 rounded-control border border-line bg-panel p-2">
                <Button
                  aria-controls={controlsId}
                  aria-expanded={panel === 'controls'}
                  onClick={() => toggle('controls')}
                  size="sm"
                  variant="secondary"
                >
                  {panel === 'controls' ? 'Fechar homologação' : 'Homologação'}
                </Button>
                <Button
                  aria-controls={runHistoryId}
                  aria-expanded={expanded}
                  onClick={onToggle}
                  size="sm"
                  variant="secondary"
                >
                  {expanded ? 'Ocultar execuções' : 'Ver execuções'}
                </Button>
                {blocked && (
                  <p className="w-full text-caption text-subtle">
                    {manual
                      ? 'Fonte desabilitada: habilite na homologação para registrar vagas.'
                      : 'Fonte desabilitada: habilite na homologação após revisar termos e testar o collector.'}
                  </p>
                )}
              </div>
            </details>
          </div>
        </td>
      </tr>
      {showPanels && (
        <tr>
          <td className="bg-panel" colSpan={sourceColumns.length}>
            {panel === 'controls' && (
              <div id={controlsId}>
                <SourceControlsPanel sourceId={source.sourceDefinitionId} />
              </div>
            )}
            {panel === 'intake' && !blocked && (
              <div id={intakeId}>
                <ManualIntakePanel sourceId={source.sourceDefinitionId} />
              </div>
            )}
            {expanded && <RunHistory id={runHistoryId} sourceId={source.sourceDefinitionId} />}
          </td>
        </tr>
      )}
    </>
  )
}

export function SourcesPage() {
  const health = useSourceHealth()
  const coverage = useSourceCoverage()
  const [expanded, setExpanded] = useState<string | null>(null)
  const [creating, setCreating] = useState<SourceType | null>(null)
  const [created, setCreated] = useState<string | null>(null)
  const [sourceState, setSourceState] = useState<SourceStateFilter>('all')
  const [sourceSearch, setSourceSearch] = useState('')
  const hasManual = health.data?.items.some((item) => item.sourceType === 'manual') ?? true
  const normalizedSearch = sourceSearch.trim().toLocaleLowerCase('pt-BR')
  const visibleSources =
    health.data?.items.filter(
      (source) =>
        matchesSourceState(source, sourceState) &&
        (normalizedSearch.length === 0 ||
          source.name.toLocaleLowerCase('pt-BR').includes(normalizedSearch) ||
          source.sourceType.toLocaleLowerCase('pt-BR').includes(normalizedSearch)),
    ) ?? []
  const hasLocalFilters = sourceState !== 'all' || normalizedSearch.length > 0

  return (
    <PageShell
      actions={
        creating === null ? (
          <Button onClick={() => setCreating('greenhouse')} variant="secondary">
            Adicionar fonte
          </Button>
        ) : undefined
      }
      current="/sources"
      eyebrow="Aquisição"
      title="Fontes e execuções"
      description="O que cada fonte produziu na última execução, e o que fazer quando ela falha. Uma fonte só executa depois de habilitada."
    >
      {/* A cobertura é uma consulta própria e chega antes ou depois da lista; sem o espaço
          reservado, a que chega por último empurra a outra. */}
      {coverage.isPending && (
        <div className="mt-8">
          <PanelSkeleton label="Carregando a cobertura…" />
        </div>
      )}
      {coverage.data && (
        <section className="mt-8 grid gap-3 rounded-control border border-line bg-panel p-5 text-sm sm:grid-cols-3">
          <p><span className="text-muted">Catálogo</span><br /><strong>{coverage.data.catalogCompanies}</strong> empresas · {coverage.data.catalogSourceRecords} registros</p>
          <p><span className="text-muted">Propostas / homologadas</span><br /><strong>{coverage.data.proposedSources}</strong> / {coverage.data.homologatedSources}</p>
          <p><span className="text-muted">Habilitadas / elegíveis</span><br /><strong>{coverage.data.enabledSources}</strong> / {coverage.data.eligibleSources}</p>
        </section>
      )}
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Link
          className="text-sm font-medium text-ink underline decoration-accent decoration-2 underline-offset-4"
          to="/sources/homologation-queue"
        >
          Fila de homologação
        </Link>
        {created && (
          <p className="text-sm text-success-ink" role="status">
            Fonte “{created}” criada, desabilitada. A homologação dela está na linha abaixo.
          </p>
        )}
      </div>
      {creating === null && !hasManual && (
        <p className="mt-4 max-w-2xl rounded-control border border-line bg-panel p-4 text-sm text-subtle">
          Para registrar uma vaga avulsa é preciso uma fonte manual, e ainda não existe
          nenhuma.{' '}
          <button
            className="font-medium text-ink underline decoration-accent decoration-2 underline-offset-4"
            onClick={() => setCreating('manual')}
            type="button"
          >
            Criar a fonte manual
          </button>
        </p>
      )}
      {creating !== null && (
        <div className="mt-4">
          <SourceCreateForm
            initialType={creating}
            key={creating}
            onCancel={() => setCreating(null)}
            onCreated={(source) => {
              setCreating(null)
              setCreated(source.name)
            }}
          />
        </div>
      )}

      <div className="mt-6 grid gap-3">
        {health.isPending && <TableSkeleton columns={sourceColumns.length} label="Carregando fontes…" />}
        {health.isError && (
          <ErrorState onRetry={() => void health.refetch()}>Não foi possível carregar as fontes.</ErrorState>
        )}
        {health.data?.items.length === 0 && (
          <EmptyState>Nenhuma fonte cadastrada.</EmptyState>
        )}
        {health.data && health.data.items.length > 0 && (
          <>
            <FilterBar
              className="mt-0"
              label="Filtros da lista de fontes"
              search={
                <SearchInput
                  id="source-search"
                  label="Buscar fontes"
                  onChange={setSourceSearch}
                  onSubmit={() => undefined}
                  placeholder="Nome ou tipo"
                  value={sourceSearch}
                />
              }
            >
              <FilterPill
                defaultValue="all"
                id="source-state"
                label="Estado"
                onChange={(value) => setSourceState(value as SourceStateFilter)}
                options={sourceStateOptions}
                value={sourceState}
              />
              {hasLocalFilters && (
                <Button
                  onClick={() => {
                    setSourceState('all')
                    setSourceSearch('')
                  }}
                  size="sm"
                  variant="secondary"
                >
                  Limpar filtros
                </Button>
              )}
            </FilterBar>
            <p className="text-sm text-muted">
              Exibindo {visibleSources.length} de {health.data.items.length} fontes carregadas.
              {' '}{health.data.failing} com falha na última execução.
            </p>
            {visibleSources.length === 0 ? (
              <EmptyState>Nenhuma fonte corresponde aos filtros desta lista.</EmptyState>
            ) : (
              <DataTable caption="Fontes" columns={sourceColumns}>
                {visibleSources.map((source) => (
                <SourceRows
                  expanded={expanded === source.sourceDefinitionId}
                  key={source.sourceDefinitionId}
                  onToggle={() =>
                    setExpanded((current) =>
                      current === source.sourceDefinitionId
                        ? null
                        : source.sourceDefinitionId,
                    )
                  }
                  source={source}
                />
                ))}
              </DataTable>
            )}
          </>
        )}
      </div>
    </PageShell>
  )
}
