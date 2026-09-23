import { useState } from 'react'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { DataTable } from '../components/DataTable'
import { ManualIntakePanel } from '../components/ManualIntakePanel'
import { PageShell } from '../components/PageShell'
import { CardListSkeleton, PanelSkeleton } from '../components/skeletons'
import { EmptyState, ErrorState } from '../components/states'
import { SourceControlsPanel } from '../components/SourceControlsPanel'
import { SourceCreateForm } from '../components/SourceCreateForm'
import { StatusBadge } from '../components/StatusBadge'
import { Unavailable } from '../components/Unavailable'
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
            <tr className="border-t border-divider" key={run.id}>
              <td className="px-4 py-3">
                <RunStatus status={run.status} />
              </td>
              <td className="px-4 py-3">{run.executionTrigger}</td>
              <td className="px-4 py-3">{formatDate(run.startedAt)}</td>
              <td className="px-4 py-3">
                {run.itemsPersisted} persistidos / {run.itemsSeen} vistos
                {run.itemsSkipped > 0 && ` · ${run.itemsSkipped} repetidos`}
                {run.itemsInvalid > 0 && ` · ${run.itemsInvalid} inválidos`}
              </td>
              <td className="px-4 py-3 text-subtle">
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

function SourceCard({
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

  return (
    <Card as="article">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">
            {source.name}{' '}
            <span className="font-normal text-muted">({source.sourceType})</span>
          </h2>
          <p className="mt-1 text-sm text-muted">
            {source.enabled ? 'Habilitada' : 'Desabilitada'} · evidência{' '}
            {source.evidenceStatus} · termos{' '}
            {source.termsReviewed ? 'revisados' : 'não revisados'} · collector{' '}
            {source.collectorLocalTested ? 'homologado' : 'não homologado'}
          </p>
        </div>
        <RunStatus status={source.lastRunStatus} />
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-muted">Última execução</dt>
          <dd className="mt-1 font-medium">{formatDate(source.lastRunFinishedAt)}</dd>
        </div>
        <div>
          <dt className="text-muted">Duração</dt>
          <dd className="mt-1 font-medium">
            {formatDuration(source.lastRunDurationSeconds)}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Itens persistidos</dt>
          <dd className="mt-1 font-medium">
            {source.lastRunItemsPersisted === null ? (
              <Unavailable reason="nunca executada" />
            ) : (
              source.lastRunItemsPersisted
            )}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Agendamento</dt>
          <dd className="mt-1 font-medium">{source.schedule ?? 'manual'}</dd>
        </div>
      </dl>

      <p className="mt-4 text-xs text-muted">
        Senioridade: {Object.entries(source.seniorityCounts).length === 0
          ? 'sem vagas normalizadas'
          : Object.entries(source.seniorityCounts)
              .map(([level, count]) => `${level} ${count}`)
              .join(' · ')}
      </p>

      {source.lastRunError && (
        <p className="break-anywhere mt-4 rounded-2xl border border-danger-line bg-danger-surface p-4 text-sm text-danger-ink">
          {source.lastRunErrorCode ? `${source.lastRunErrorCode}: ` : ''}
          {source.lastRunError}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {manual ? (
          <Button
            aria-controls={intakeId}
            aria-expanded={panel === 'intake'}
            disabled={blocked}
            onClick={() => toggle('intake')}
          >
            Registrar vaga
          </Button>
        ) : (
          <Button
            disabled={blocked || run.isPending}
            onClick={() => run.mutate(source.sourceDefinitionId)}
          >
            {run.isPending ? 'Executando…' : 'Executar agora'}
          </Button>
        )}
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
          <span className="text-xs text-muted">
            {manual
              ? 'Fonte desabilitada: habilite na homologação para registrar vagas.'
              : 'Fonte desabilitada: habilite na homologação, depois de revisar termos e testar o collector.'}
          </span>
        )}
      </div>

      {run.isError && (
        <p className="mt-3 text-sm text-danger-ink">{run.error.message}</p>
      )}
      {run.isSuccess && (
        <p className="mt-3 text-sm text-subtle">
          Execução {run.data.status} · {run.data.itemsPersisted} itens persistidos.
        </p>
      )}

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
    </Card>
  )
}

export function SourcesPage() {
  const health = useSourceHealth()
  const coverage = useSourceCoverage()
  const [expanded, setExpanded] = useState<string | null>(null)
  const [creating, setCreating] = useState<SourceType | null>(null)
  const [created, setCreated] = useState<string | null>(null)
  const hasManual = health.data?.items.some((item) => item.sourceType === 'manual') ?? true

  return (
    <PageShell
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
        <section className="mt-8 grid gap-3 rounded-2xl border border-line bg-panel p-5 text-sm sm:grid-cols-3">
          <p><span className="text-muted">Catálogo</span><br /><strong>{coverage.data.catalogCompanies}</strong> empresas · {coverage.data.catalogSourceRecords} registros</p>
          <p><span className="text-muted">Propostas / homologadas</span><br /><strong>{coverage.data.proposedSources}</strong> / {coverage.data.homologatedSources}</p>
          <p><span className="text-muted">Habilitadas / elegíveis</span><br /><strong>{coverage.data.enabledSources}</strong> / {coverage.data.eligibleSources}</p>
        </section>
      )}
      <div className="mt-8 flex flex-wrap items-center gap-3">
        {creating === null && (
          <Button onClick={() => setCreating('greenhouse')}>Nova fonte</Button>
        )}
        {created && (
          <p className="text-sm text-success-ink" role="status">
            Fonte “{created}” criada, desabilitada. A homologação dela está no cartão abaixo.
          </p>
        )}
      </div>
      {creating === null && !hasManual && (
        <p className="mt-4 max-w-2xl rounded-2xl border border-line bg-panel p-4 text-sm text-subtle">
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

      <div className="mt-8 grid gap-3">
        {health.isPending && (
          <CardListSkeleton label="Carregando fontes…" />
        )}
        {health.isError && (
          <ErrorState onRetry={() => void health.refetch()}>Não foi possível carregar as fontes.</ErrorState>
        )}
        {health.data?.items.length === 0 && (
          <EmptyState>Nenhuma fonte cadastrada.</EmptyState>
        )}
        {health.data && health.data.items.length > 0 && (
          <>
            <p className="text-sm text-muted">
              {health.data.total} fonte{health.data.total === 1 ? '' : 's'} ·{' '}
              {health.data.failing} com falha na última execução.
            </p>
            {health.data.items.map((source) => (
              <SourceCard
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
          </>
        )}
      </div>
    </PageShell>
  )
}
