import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PageShell } from '../components/PageShell'
import {
  type FailingSource,
  type Overview,
  type SourceMetrics,
  type SourceMetricsWindow,
} from '../features/dashboard/api'
import { useOverview, useSourceMetrics } from '../features/dashboard/useOverview'

const coverageLabels: Record<string, string> = {
  NOT_ENABLED: 'Não habilitada',
  CONFIGURATION_BLOCKED: 'Bloqueada por homologação',
  NOT_SCHEDULED: 'Sem agendamento',
  NOT_RUN: 'Não executou na janela',
  SUCCEEDED_ZERO: 'Sucesso sem vagas',
  SUCCEEDED: 'Saudável',
  PARTIAL: 'Degradada',
  FAILED: 'Falhou',
  CANCELLED: 'Cancelada',
}

const coverageTone: Record<string, string> = {
  SUCCEEDED: 'border-[#b6d36a] bg-[#eef6d8] text-[#42571c]',
  SUCCEEDED_ZERO: 'border-[#c8d4c8] bg-[#f2f5ef] text-[#41594f]',
  PARTIAL: 'border-[#e3cf9a] bg-[#fbf3e2] text-[#7a5a16]',
  FAILED: 'border-[#e8cfc6] bg-[#fdf3f0] text-[#9b3e2e]',
}

const verdictLabels: Record<string, string> = {
  HIGH_PRIORITY: 'Alta prioridade',
  RECOMMENDED: 'Recomendadas',
  WATCHLIST: 'Observação',
  REVIEW_REQUIRED: 'Revisão necessária',
  LOW_MATCH: 'Baixa aderência',
  INELIGIBLE: 'Inelegíveis',
}

const verdictOrder = [
  'HIGH_PRIORITY',
  'RECOMMENDED',
  'REVIEW_REQUIRED',
  'WATCHLIST',
  'LOW_MATCH',
  'INELIGIBLE',
]

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
      <p className="text-sm text-[#6d827b]">{label}</p>
      <p className="mt-2 text-3xl font-semibold tracking-[-0.03em]">{value}</p>
      {hint && <p className="mt-2 text-sm text-[#547068]">{hint}</p>}
    </>
  )
  if (to) {
    return (
      <Link
        className="rounded-2xl border border-[#dce4dc] bg-white p-5 transition hover:border-[#17322d]"
        to={to}
      >
        {body}
      </Link>
    )
  }
  return <div className="rounded-2xl border border-[#dce4dc] bg-white p-5">{body}</div>
}

function FailingSources({ sources }: { sources: FailingSource[] }) {
  if (sources.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-[#c8d4c8] p-5 text-[#547068]">
        Nenhuma fonte falhou na última execução.
      </p>
    )
  }
  return (
    <ul className="grid gap-3">
      {sources.map((source) => (
        <li
          className="rounded-2xl border border-[#e8cfc6] bg-[#fdf3f0] p-5"
          key={source.sourceDefinitionId}
        >
          <p className="font-semibold">
            {source.name}{' '}
            <span className="font-normal text-[#6d827b]">({source.sourceType})</span>
          </p>
          <p className="mt-1 text-sm text-[#9b3e2e]">
            Última execução: {source.lastRunStatus ?? 'desconhecida'}
            {source.lastRunFinishedAt
              ? ` em ${new Date(source.lastRunFinishedAt).toLocaleString('pt-BR')}`
              : ''}
          </p>
          {source.lastRunError && (
            <p className="mt-2 text-sm text-[#547068]">{source.lastRunError}</p>
          )}
        </li>
      ))}
    </ul>
  )
}

function percent(value: number | null) {
  return value === null ? 'sem dados' : `${(value * 100).toFixed(1)}%`
}

function seconds(value: number | null) {
  return value === null ? 'sem dados' : `${value.toFixed(1)} s`
}

function SourceMetricsRow({ source }: { source: SourceMetrics }) {
  const tone = coverageTone[source.coverageState] ?? 'border-[#c8d4c8] bg-[#f2f5ef] text-[#41594f]'
  const { seniority } = source
  const knownLevels = Object.entries(seniority.counts)
    .filter(([level]) => level !== 'UNKNOWN')
    .sort(([, a], [, b]) => b - a)
  const mappings = Object.keys(seniority.mappingVersions)
  return (
    <tr className="border-t border-[#e4ebe4] align-top">
      <td className="px-4 py-3">
        <p className="font-medium">{source.name}</p>
        <p className="text-xs text-[#6d827b]">{source.sourceType}</p>
        {source.incidentOpen && (
          <p className="mt-1 text-xs font-semibold text-[#9b3e2e]">Incidente aberto</p>
        )}
      </td>
      <td className="px-4 py-3">
        <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${tone}`}>
          {coverageLabels[source.coverageState] ?? source.coverageState}
        </span>
      </td>
      <td className="px-4 py-3 text-sm">
        {source.runs} execuç{source.runs === 1 ? 'ão' : 'ões'}
        <br />
        <span className="text-xs text-[#6d827b]">
          {source.itemsPersisted} persistidos / {source.itemsSeen} vistos
        </span>
      </td>
      <td className="px-4 py-3 text-sm">
        <span className="text-xs text-[#6d827b]">erro</span> {percent(source.errorRate)}
        <br />
        <span className="text-xs text-[#6d827b]">dedupe</span> {percent(source.dedupeRate)}
        <br />
        <span className="text-xs text-[#6d827b]">p95</span> {seconds(source.latencyP95Seconds)}
      </td>
      <td className="px-4 py-3 text-sm">
        {Object.keys(source.errorsByCode).length === 0 ? (
          <span className="text-[#6d827b]">—</span>
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
          <span className="text-[#6d827b]">sem vagas normalizadas na janela</span>
        ) : (
          <>
            <p>
              UNKNOWN {seniority.unknown} (
              {(seniority.percentages.UNKNOWN ?? 0).toFixed(1)}%) · conhecidas{' '}
              {seniority.known}
            </p>
            {knownLevels.length > 0 && (
              <p className="mt-1 text-xs text-[#6d827b]">
                {knownLevels
                  .map(
                    ([level, total]) =>
                      `${level} ${total} (${(seniority.percentages[level] ?? 0).toFixed(1)}%)`,
                  )
                  .join(' · ')}
              </p>
            )}
            <p className="mt-1 text-xs text-[#6d827b]">
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
      <p className="rounded-2xl border border-dashed border-[#c8d4c8] p-5 text-[#547068]">
        Nenhuma fonte cadastrada.
      </p>
    )
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-[#f2f5ef] text-xs uppercase tracking-[0.08em] text-[#6d827b]">
          <tr>
            <th className="px-4 py-3 font-semibold">Fonte</th>
            <th className="px-4 py-3 font-semibold">Cobertura</th>
            <th className="px-4 py-3 font-semibold">Volume</th>
            <th className="px-4 py-3 font-semibold">Taxas</th>
            <th className="px-4 py-3 font-semibold">Erros por código</th>
            <th className="px-4 py-3 font-semibold">Senioridade</th>
          </tr>
        </thead>
        <tbody>
          {window.sources.map((source) => (
            <SourceMetricsRow key={source.sourceDefinitionId} source={source} />
          ))}
        </tbody>
      </table>
    </div>
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
                  ? 'border-[#17322d] bg-[#17322d] text-white'
                  : 'border-[#c8d4c8] bg-white'
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
      <div className="mt-4" aria-live="polite">
        {metrics.isPending && (
          <p className="rounded-2xl bg-[#eef3df] p-5 text-[#5c694e]">
            Carregando métricas…
          </p>
        )}
        {metrics.isError && (
          <div className="rounded-2xl bg-[#f9e4df] p-5 text-[#9b3e2e]">
            <p>Não foi possível carregar as métricas por fonte.</p>
            <button
              className="mt-3 font-semibold underline"
              onClick={() => void metrics.refetch()}
              type="button"
            >
              Tentar novamente
            </button>
          </div>
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
                  className="flex items-baseline gap-2 rounded-full border border-[#c8d4c8] bg-white px-4 py-2 text-sm hover:border-[#17322d]"
                  to={`/inbox?verdict=${verdict}`}
                >
                  <span className="text-[#547068]">{verdictLabels[verdict] ?? verdict}</span>
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
      <div aria-live="polite">
        {overview.isPending && (
          <p className="mt-8 rounded-2xl bg-[#eef3df] p-5 text-[#5c694e]">
            Carregando o resumo…
          </p>
        )}
        {overview.isError && (
          <div className="mt-8 rounded-2xl bg-[#f9e4df] p-5 text-[#9b3e2e]">
            <p>Não foi possível carregar o resumo.</p>
            <button
              className="mt-3 font-semibold underline"
              onClick={() => void overview.refetch()}
              type="button"
            >
              Tentar novamente
            </button>
          </div>
        )}
        {overview.data && <Summary overview={overview.data} />}
      </div>
    </PageShell>
  )
}
