import { useState } from 'react'
import { PageShell } from '../components/PageShell'
import { type SourceHealth } from '../features/sources/api'
import {
  useRunSource,
  useSourceCoverage,
  useSourceHealth,
  useSourceRuns,
} from '../features/sources/useSources'

const statusTone: Record<string, string> = {
  SUCCEEDED: 'border-success-line bg-success-surface text-success-ink',
  PARTIAL: 'border-warning-line bg-warning-surface text-warning-ink',
  FAILED: 'border-danger-line bg-danger-surface text-danger-ink',
  RUNNING: 'border-line-strong bg-canvas text-neutral-ink',
  PENDING: 'border-line-strong bg-canvas text-neutral-ink',
  CANCELLED: 'border-line-strong bg-canvas text-muted',
}

function formatDate(value: string | null) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString('pt-BR')
}

function formatDuration(seconds: number | null) {
  if (seconds === null) return '—'
  if (seconds < 60) return `${seconds.toFixed(1)} s`
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`
}

function StatusBadge({ status }: { status: string | null }) {
  if (status === null) {
    return (
      <span className="inline-flex rounded-full border border-dashed border-line-strong px-3 py-1 text-xs text-muted">
        Nunca executada
      </span>
    )
  }
  const tone = statusTone[status] ?? 'border-line-strong bg-canvas text-neutral-ink'
  return (
    <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${tone}`}>
      {status}
    </span>
  )
}

function RunHistory({ sourceId }: { sourceId: string }) {
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
    <div className="mt-4 overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-canvas text-xs uppercase tracking-[0.08em] text-muted">
          <tr>
            <th className="px-4 py-3 font-semibold">Status</th>
            <th className="px-4 py-3 font-semibold">Origem</th>
            <th className="px-4 py-3 font-semibold">Início</th>
            <th className="px-4 py-3 font-semibold">Itens</th>
            <th className="px-4 py-3 font-semibold">Erro</th>
          </tr>
        </thead>
        <tbody>
          {runs.data.map((run) => (
            <tr className="border-t border-divider" key={run.id}>
              <td className="px-4 py-3">
                <StatusBadge status={run.status} />
              </td>
              <td className="px-4 py-3">{run.executionTrigger}</td>
              <td className="px-4 py-3">{formatDate(run.startedAt)}</td>
              <td className="px-4 py-3">
                {run.itemsPersisted} persistidos / {run.itemsSeen} vistos
                {run.itemsSkipped > 0 && ` · ${run.itemsSkipped} repetidos`}
                {run.itemsInvalid > 0 && ` · ${run.itemsInvalid} inválidos`}
              </td>
              <td className="px-4 py-3 text-subtle">
                {run.errorCode ? `${run.errorCode}: ${run.errorSummary ?? ''}` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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

  return (
    <article className="rounded-2xl border border-line bg-surface p-5">
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
        <StatusBadge status={source.lastRunStatus} />
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
            {source.lastRunItemsPersisted === null ? '—' : source.lastRunItemsPersisted}
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
        <p className="mt-4 rounded-2xl border border-danger-line bg-danger-surface p-4 text-sm text-danger-ink">
          {source.lastRunErrorCode ? `${source.lastRunErrorCode}: ` : ''}
          {source.lastRunError}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          className="rounded-xl bg-ink px-5 py-3 text-sm font-semibold text-white hover:bg-ink-hover disabled:cursor-not-allowed disabled:opacity-40"
          disabled={blocked || run.isPending}
          onClick={() => run.mutate(source.sourceDefinitionId)}
          type="button"
        >
          {run.isPending ? 'Executando…' : 'Executar agora'}
        </button>
        <button
          className="rounded-xl border border-line-strong px-4 py-2 text-sm font-medium"
          onClick={onToggle}
          type="button"
        >
          {expanded ? 'Ocultar execuções' : 'Ver execuções'}
        </button>
        {blocked && (
          <span className="text-xs text-muted">
            Fonte desabilitada: habilite após revisar termos e homologar o collector.
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

      {expanded && <RunHistory sourceId={source.sourceDefinitionId} />}
    </article>
  )
}

export function SourcesPage() {
  const health = useSourceHealth()
  const coverage = useSourceCoverage()
  const [expanded, setExpanded] = useState<string | null>(null)

  return (
    <PageShell
      current="/sources"
      eyebrow="Aquisição"
      title="Fontes e execuções"
      description="O que cada fonte produziu na última execução, e o que fazer quando ela falha. Uma fonte só executa depois de habilitada."
    >
      {coverage.data && (
        <section className="mt-8 grid gap-3 rounded-2xl border border-line bg-panel p-5 text-sm sm:grid-cols-3">
          <p><span className="text-muted">Catálogo</span><br /><strong>{coverage.data.catalogCompanies}</strong> empresas · {coverage.data.catalogSourceRecords} registros</p>
          <p><span className="text-muted">Propostas / homologadas</span><br /><strong>{coverage.data.proposedSources}</strong> / {coverage.data.homologatedSources}</p>
          <p><span className="text-muted">Habilitadas / elegíveis</span><br /><strong>{coverage.data.enabledSources}</strong> / {coverage.data.eligibleSources}</p>
        </section>
      )}
      <div className="mt-8 grid gap-3" aria-live="polite">
        {health.isPending && (
          <p className="rounded-2xl bg-info-surface p-5 text-info-ink">Carregando fontes…</p>
        )}
        {health.isError && (
          <div className="rounded-2xl bg-danger-surface-strong p-5 text-danger-ink">
            <p>Não foi possível carregar as fontes.</p>
            <button
              className="mt-3 font-semibold underline"
              onClick={() => void health.refetch()}
              type="button"
            >
              Tentar novamente
            </button>
          </div>
        )}
        {health.data?.items.length === 0 && (
          <p className="rounded-2xl border border-dashed border-line-strong p-8 text-subtle">
            Nenhuma fonte cadastrada.
          </p>
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
