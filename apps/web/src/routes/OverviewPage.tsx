import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Card } from '../components/Card'
import { DataTable } from '../components/DataTable'
import { PageShell } from '../components/PageShell'
import { EmptyState, ErrorState, LoadingState } from '../components/states'
import { StatusBadge } from '../components/StatusBadge'
import { Unavailable } from '../components/Unavailable'
import {
  type FailingSource,
  type Overview,
  type SourceMetrics,
  type SourceMetricsWindow,
} from '../features/dashboard/api'
import { useOverview, useSourceMetrics } from '../features/dashboard/useOverview'
import { verdictCountLabels, verdictOrder } from '../features/matching/verdicts'
import { coverageLabels, coverageTones } from '../features/sources/states'

function Tile({
  label,
  value,
  hint,
  to,
}: {
  label: string
  value: string
  hint?: string
  to?: string
}) {
  const body = (
    <>
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-2 text-3xl font-semibold tracking-[-0.03em]">{value}</p>
      {hint && <p className="mt-2 text-sm text-subtle">{hint}</p>}
    </>
  )
  if (to) {
    return (
      <Link
        className="rounded-2xl border border-line bg-surface p-5 transition hover:border-ink"
        to={to}
      >
        {body}
      </Link>
    )
  }
  return <Card>{body}</Card>
}

function FailingSources({ sources }: { sources: FailingSource[] }) {
  if (sources.length === 0) {
    return (
      <EmptyState>Nenhuma fonte falhou na última execução.</EmptyState>
    )
  }
  return (
    <ul className="grid gap-3">
      {sources.map((source) => (
        <li
          className="rounded-2xl border border-danger-line bg-danger-surface p-5"
          key={source.sourceDefinitionId}
        >
          <p className="font-semibold">
            {source.name}{' '}
            <span className="font-normal text-muted">({source.sourceType})</span>
          </p>
          <p className="mt-1 text-sm text-danger-ink">
            Última execução: {source.lastRunStatus ?? 'desconhecida'}
            {source.lastRunFinishedAt
              ? ` em ${new Date(source.lastRunFinishedAt).toLocaleString('pt-BR')}`
              : ''}
          </p>
          {source.lastRunError && (
            <p className="mt-2 text-sm text-subtle">{source.lastRunError}</p>
          )}
        </li>
      ))}
    </ul>
  )
}

/** A window with no run behind it has no rate, and a rate of zero is a different fact. */
function percent(value: number | null) {
  return value === null ? (
    <Unavailable reason="sem execução na janela" />
  ) : (
    `${(value * 100).toFixed(1)}%`
  )
}

function seconds(value: number | null) {
  return value === null ? (
    <Unavailable reason="sem execução na janela" />
  ) : (
    `${value.toFixed(1)} s`
  )
}

function SourceMetricsRow({ source }: { source: SourceMetrics }) {
  const { seniority } = source
  const knownLevels = Object.entries(seniority.counts)
    .filter(([level]) => level !== 'UNKNOWN')
    .sort(([, a], [, b]) => b - a)
  const mappings = Object.keys(seniority.mappingVersions)
  return (
    <tr className="border-t border-divider align-top">
      <td className="min-w-40 px-4 py-3">
        <p className="break-anywhere font-medium">{source.name}</p>
        <p className="text-xs text-muted">{source.sourceType}</p>
        {source.incidentOpen && (
          <p className="mt-1 text-xs font-semibold text-danger-ink">Incidente aberto</p>
        )}
      </td>
      <td className="px-4 py-3">
        <StatusBadge
          labels={coverageLabels}
          tones={coverageTones}
          value={source.coverageState}
        />
      </td>
      <td className="px-4 py-3 text-sm">
        {source.runs} execuç{source.runs === 1 ? 'ão' : 'ões'}
        <br />
        <span className="text-xs text-muted">
          {source.itemsPersisted} persistidos / {source.itemsSeen} vistos
        </span>
      </td>
      <td className="px-4 py-3 text-sm">
        <span className="text-xs text-muted">erro</span> {percent(source.errorRate)}
        <br />
        <span className="text-xs text-muted">dedupe</span> {percent(source.dedupeRate)}
        <br />
        <span className="text-xs text-muted">p95</span> {seconds(source.latencyP95Seconds)}
      </td>
      <td className="px-4 py-3 text-sm">
        {Object.keys(source.errorsByCode).length === 0 ? (
          <Unavailable reason="nenhum erro registrado" />
        ) : (
          <ul className="text-xs">
            {Object.entries(source.errorsByCode).map(([code, total]) => (
              <li key={code}>
                {code}: {total}
              </li>
            ))}
          </ul>
        )}
      </td>
      <td className="px-4 py-3 text-sm">
        {seniority.total === 0 ? (
          <span className="text-muted">sem vagas normalizadas na janela</span>
        ) : (
          <>
            <p>
              UNKNOWN {seniority.unknown} (
              {(seniority.percentages.UNKNOWN ?? 0).toFixed(1)}%) · conhecidas{' '}
              {seniority.known}
            </p>
            {knownLevels.length > 0 && (
              <p className="mt-1 text-xs text-muted">
                {knownLevels
                  .map(
                    ([level, total]) =>
                      `${level} ${total} (${(seniority.percentages[level] ?? 0).toFixed(1)}%)`,
                  )
                  .join(' · ')}
              </p>
            )}
            <p className="mt-1 text-xs text-muted">
              mapeamento {mappings.length > 0 ? mappings.join(', ') : 'sem procedência'}
              {Object.keys(seniority.evidence).length > 0 &&
                ` · evidência ${Object.entries(seniority.evidence)
                  .map(([origin, total]) => `${origin} ${total}`)
                  .join(' · ')}`}
            </p>
          </>
        )}
      </td>
    </tr>
  )
}

function SourceMetricsTable({ window }: { window: SourceMetricsWindow }) {
  if (window.sources.length === 0) {
    return (
      <EmptyState>Nenhuma fonte cadastrada.</EmptyState>
    )
  }
  return (
    <DataTable
      caption={`Métricas por fonte na janela de ${window.window}`}
      columns={['Fonte', 'Cobertura', 'Volume', 'Taxas', 'Erros por código', 'Senioridade']}
      stickyFirstColumn
    >
      {window.sources.map((source) => (
        <SourceMetricsRow key={source.sourceDefinitionId} source={source} />
      ))}
    </DataTable>
  )
}

function SourceMetricsSection() {
  const metrics = useSourceMetrics()
  const [selected, setSelected] = useState('24h')
  const windows = metrics.data?.windows ?? []
  const active = windows.find((item) => item.window === selected) ?? windows[0]

  return (
    <section className="mt-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Métricas operacionais por fonte</h2>
        <div className="flex gap-2">
          {windows.map((item) => (
            <button
              aria-pressed={item.window === active?.window}
              className={`rounded-full border px-4 py-2 text-sm ${
                item.window === active?.window
                  ? 'border-ink bg-ink text-white'
                  : 'border-line-strong bg-surface'
              }`}
              key={item.window}
              onClick={() => setSelected(item.window)}
              type="button"
            >
              {item.window === '24h' ? '24 horas' : '7 dias'}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-4">
        {metrics.isPending && (
          <LoadingState>Carregando métricas…</LoadingState>
        )}
        {metrics.isError && (
          <ErrorState onRetry={() => void metrics.refetch()}>Não foi possível carregar as métricas por fonte.</ErrorState>
        )}
        {active && <SourceMetricsTable window={active} />}
      </div>
    </section>
  )
}

function Summary({ overview }: { overview: Overview }) {
  const verdicts = verdictOrder.filter((verdict) => overview.verdictCounts[verdict] > 0)
  return (
    <>
      <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          label={`Novas (${overview.newOpportunityWindowDays} dias)`}
          value={String(overview.newOpportunities)}
          hint={`${overview.opportunitiesActive} ativas de ${overview.opportunitiesTotal}`}
          to="/inbox?order=recency"
        />
        <Tile
          label="Alta prioridade"
          value={String(overview.verdictCounts.HIGH_PRIORITY ?? 0)}
          to="/inbox?verdict=HIGH_PRIORITY"
        />
        <Tile
          label="Recomendadas"
          value={String(overview.verdictCounts.RECOMMENDED ?? 0)}
          to="/inbox?verdict=RECOMMENDED"
        />
        <Tile
          label="Fontes com falha"
          value={String(overview.sourcesFailing)}
          hint={`${overview.sourcesEnabled} habilitadas de ${overview.sourcesTotal}`}
        />
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          label="Avaliadas"
          value={String(overview.assessedOpportunities)}
          hint="Com decisão determinística registrada"
          to="/inbox?only_assessed=true"
        />
        <Tile
          label="Análises degradadas"
          value={String(overview.analysesDegraded)}
          hint="Ollama indisponível, fora do contrato ou desligado"
        />
        <Tile
          label="Itens brutos pendentes"
          value={String(overview.pendingNormalizations)}
          hint="Preservados, ainda sem normalização"
        />
        <Tile
          label="Candidaturas ativas"
          value={String(overview.applicationsActive)}
          hint={`${overview.followUpsDue} follow-up${
            overview.followUpsDue === 1 ? '' : 's'
          } nos próximos ${overview.followUpWindowDays} dias`}
          to="/applications"
        />
      </div>

      {verdicts.length > 0 && (
        <section className="mt-10">
          <h2 className="text-lg font-semibold">Decisões por verdict</h2>
          <ul className="mt-4 flex flex-wrap gap-3">
            {verdicts.map((verdict) => (
              <li key={verdict}>
                <Link
                  className="flex items-baseline gap-2 rounded-full border border-line-strong bg-surface px-4 py-2 text-sm hover:border-ink"
                  to={`/inbox?verdict=${verdict}`}
                >
                  <span className="text-subtle">{verdictCountLabels[verdict] ?? verdict}</span>
                  <span className="font-semibold">{overview.verdictCounts[verdict]}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-10">
        <h2 className="text-lg font-semibold">Saúde das fontes</h2>
        <div className="mt-4">
          <FailingSources sources={overview.failingSources} />
        </div>
      </section>

      <SourceMetricsSection />
    </>
  )
}

export function OverviewPage() {
  const overview = useOverview()

  return (
    <PageShell
      current="/"
      eyebrow="Radar local"
      title="Visão geral"
      description="O estado do ciclo completo: o que chegou, o que já foi decidido e o que precisa de atenção."
      footer="Descubra oportunidades, preserve evidências e decida com contexto."
    >
      <div>
        {overview.isPending && (
          <LoadingState className="mt-8">Carregando o resumo…</LoadingState>
        )}
        {overview.isError && (
          <ErrorState className="mt-8" onRetry={() => void overview.refetch()}>Não foi possível carregar o resumo.</ErrorState>
        )}
        {overview.data && <Summary overview={overview.data} />}
      </div>
    </PageShell>
  )
}
