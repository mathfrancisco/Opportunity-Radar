import { Link } from 'react-router-dom'
import { PageShell } from '../components/PageShell'
import { type FailingSource, type Overview } from '../features/dashboard/api'
import { useOverview } from '../features/dashboard/useOverview'

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
