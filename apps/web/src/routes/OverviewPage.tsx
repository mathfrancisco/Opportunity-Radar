import { type ReactNode, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card } from '../components/Card'
import { DataTable } from '../components/DataTable'
import { PageShell } from '../components/PageShell'
import { Bone, Skeleton, TableSkeleton } from '../components/skeletons'
import { EmptyState, ErrorState } from '../components/states'
import { StatusBadge } from '../components/StatusBadge'
import { Toolbar } from '../components/Toolbar'
import { Unavailable } from '../components/Unavailable'
import {
  type FailingSource,
  type Overview,
  type SourceMetrics,
  type SourceMetricsWindow,
} from '../features/dashboard/api'
import {
  useAnalysisMetrics,
  useOverview,
  useSourceMetrics,
} from '../features/dashboard/useOverview'
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
      <p className="mt-2 text-metric">{value}</p>
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

/**
 * O que a tabela abaixo diz, em uma linha.
 *
 * Derivado das mesmas linhas que a tabela mostra, e não de uma segunda consulta: um resumo
 * que pode discordar da tabela logo abaixo dele é pior que nenhum resumo.
 */
function CoverageSummary({ window }: { window: SourceMetricsWindow }) {
  const tally = window.sources.reduce(
    (totals, source) => {
      if (source.coverageState === 'SUCCEEDED') totals.healthy += 1
      else if (source.coverageState === 'SUCCEEDED_ZERO') totals.empty += 1
      else if (source.coverageState === 'PARTIAL' || source.coverageState === 'FAILED')
        totals.degraded += 1
      else if (source.coverageState === 'NOT_RUN') totals.idle += 1
      else totals.inactive += 1
      return totals
    },
    { healthy: 0, empty: 0, degraded: 0, idle: 0, inactive: 0 },
  )
  return (
    <p className="text-sm text-subtle">
      <strong className="font-semibold text-ink">{tally.healthy}</strong> saudáveis ·{' '}
      <strong className="font-semibold text-ink">{tally.degraded}</strong> degradadas ·{' '}
      <strong className="font-semibold text-ink">{tally.empty}</strong> sem vagas ·{' '}
      <strong className="font-semibold text-ink">{tally.idle}</strong> sem execução na
      janela · <strong className="font-semibold text-ink">{tally.inactive}</strong> não
      habilitadas ou bloqueadas.
    </p>
  )
}

function SourceMetricsSection() {
  const metrics = useSourceMetrics()
  const [selected, setSelected] = useState('24h')
  const windows = metrics.data?.windows ?? []
  const active = windows.find((item) => item.window === selected) ?? windows[0]

  return (
    <section className="mt-section">
      {/* A altura mínima é a dos botões de janela, que só existem depois da resposta. */}
      <div className="flex min-h-10 flex-wrap items-center justify-between gap-3">
        <h2 className="text-section">Métricas operacionais por fonte</h2>
        <Toolbar
          label="Janela das métricas"
          onChange={setSelected}
          options={windows.map((item) => ({
            value: item.window,
            label: item.window === '24h' ? '24 horas' : '7 dias',
          }))}
          value={active?.window}
        />
      </div>
      <div className="mt-4">
        {metrics.isPending && (
          <>
            <Bone className="my-1 w-3/4" />
            <div className="mt-4">
              <TableSkeleton columns={6} label="Carregando métricas…" />
            </div>
          </>
        )}
        {metrics.isError && (
          <ErrorState onRetry={() => void metrics.refetch()}>Não foi possível carregar as métricas por fonte.</ErrorState>
        )}
        {active && (
          <>
            <CoverageSummary window={active} />
            <div className="mt-4">
              <SourceMetricsTable window={active} />
            </div>
          </>
        )}
      </div>
    </section>
  )
}

/**
 * Os três blocos antes dos números: decisão com quatro cartões, acervo e operação com
 * quatro linhas de apoio cada. Os títulos são os de verdade, porque não dependem do dado.
 */
function SummarySkeleton() {
  // Uma linha de apoio com dica quebra em duas fora da tela larga; sem dica, fica em uma.
  const supportLines = (hinted: boolean[]) => (
    <div className="mt-4 grid gap-3 sm:grid-cols-2">
      {hinted.map((hint, line) => (
        <div className="py-1" key={line}>
          <Bone className="w-3/4" />
          {hint && <Bone className="mt-3 w-1/2 lg:hidden" />}
        </div>
      ))}
    </div>
  )
  return (
    <Skeleton label="Carregando o resumo…">
      <section className="mt-8">
        <p className="text-section">Decisão de hoje</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((tile) => (
            <div className="rounded-2xl border border-line bg-surface p-5" key={tile}>
              <Bone className="w-24" />
              <Bone className="mt-4 h-8 w-12" />
              {/* O cartão de follow-up traz uma dica, e a linha de cartões cresce com ela. */}
              {tile === 3 && <Bone className="mt-4 w-28" />}
            </div>
          ))}
        </div>
        {/* As pílulas de veredito, que aparecem sempre que há alguma vaga avaliada. */}
        <div className="mt-3 flex flex-wrap gap-3">
          {[0, 1].map((pill) => (
            <span className="block h-9 w-36 rounded-full border border-line bg-surface" key={pill} />
          ))}
        </div>
      </section>
      <section className="mt-section">
        <p className="text-section">Acervo</p>
        <Bone className="mt-3 w-2/3" />
        {supportLines([true, true, true, false])}
      </section>
      <section className="mt-section">
        <p className="text-section">Operação</p>
        <Bone className="mt-3 w-1/2" />
        {supportLines([true, true, true])}
      </section>
    </Skeleton>
  )
}

/** Um número e o que ele significa, numa linha. Para o que se lê, não para o que se aciona. */
function SupportItem({
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
  const number = <span className="font-semibold text-ink">{value}</span>
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <dt className="text-muted">{label}</dt>
      <dd className="text-subtle">
        {to ? (
          <Link className="underline decoration-accent decoration-2 underline-offset-4" to={to}>
            {number}
          </Link>
        ) : (
          number
        )}
        {hint && <span className="ml-2 text-xs text-muted">{hint}</span>}
      </dd>
    </div>
  )
}

/**
 * Custo e atraso da análise do modelo atual em 7 dias. A janela atravessa trocas de modelo,
 * então só as linhas do modelo configurado entram: um p95 de dois modelos não descreve
 * nenhum.
 */
function AnalysisSupport() {
  const metrics = useAnalysisMetrics()
  const report = metrics.data
  const week = report?.windows.find((item) => item.window === '7d')
  const current = week?.models.find((item) => item.modelId === report?.currentModel)
  const inSeconds = (ms: number | null) =>
    ms === null ? 'indisponível' : `${(ms / 1000).toFixed(1)} s`

  let value = 'carregando…'
  if (metrics.isError) value = 'indisponível'
  else if (report && (!current || current.totalMsP50 === null))
    value = `sem análise medida · ${report.pending} na fila`
  else if (report && current)
    value =
      `p50 ${inSeconds(current.totalMsP50)} · p95 ${inSeconds(current.totalMsP95)} · ` +
      `${report.pending} na fila · ` +
      `${((current.failureRate ?? 0) * 100).toFixed(1)}% falhas`
  return (
    <SupportItem
      hint={report ? `${report.currentModel}, últimos 7 dias` : undefined}
      label="Análise"
      value={value}
    />
  )
}

function Block({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <section className="mt-section">
      <h2 className="text-section">{title}</h2>
      <p className="mt-1 text-sm text-muted">{description}</p>
      <div className="mt-4">{children}</div>
    </section>
  )
}

/**
 * O que exige decisão hoje.
 *
 * Primeiro bloco e o único com peso de cartão: se nada aqui pede ação, o operador pode
 * parar de ler a página, e a tela precisa deixar isso claro sem que ele desça até o fim.
 */
function PendingDecisions({ overview }: { overview: Overview }) {
  const highPriority = overview.verdictCounts.HIGH_PRIORITY ?? 0
  const recommended = overview.verdictCounts.RECOMMENDED ?? 0
  const pending = highPriority + recommended + overview.newOpportunities + overview.followUpsDue
  const verdicts = verdictOrder.filter((verdict) => overview.verdictCounts[verdict] > 0)

  return (
    <section className="mt-8">
      <h2 className="text-section">Decisão de hoje</h2>
      {pending === 0 ? (
        <p className="mt-4 rounded-2xl border border-success-line bg-success-surface p-5 text-success-ink">
          Nada exige decisão agora: sem vagas novas na janela, sem recomendações abertas e
          sem follow-up devido.
        </p>
      ) : (
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Tile
            label="Alta prioridade"
            value={String(highPriority)}
            to="/inbox?verdict=HIGH_PRIORITY"
          />
          <Tile
            label="Recomendadas"
            value={String(recommended)}
            to="/inbox?verdict=RECOMMENDED"
          />
          <Tile
            label={`Novas (${overview.newOpportunityWindowDays} dias)`}
            value={String(overview.newOpportunities)}
            to="/inbox?order=recency"
          />
          <Tile
            label="Follow-ups devidos"
            value={String(overview.followUpsDue)}
            hint={`Próximos ${overview.followUpWindowDays} dias`}
            to="/applications"
          />
        </div>
      )}

      {verdicts.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-3">
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
      )}
    </section>
  )
}

function Summary({ overview }: { overview: Overview }) {
  return (
    <>
      <PendingDecisions overview={overview} />

      <Block
        description="O que o radar já coletou e decidiu, e que continua disponível para consulta."
        title="Acervo"
      >
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <SupportItem
            hint={`de ${overview.opportunitiesTotal} no total`}
            label="Oportunidades ativas"
            value={String(overview.opportunitiesActive)}
          />
          <SupportItem
            hint="Com decisão determinística registrada"
            label="Avaliadas"
            to="/inbox?only_assessed=true"
            value={String(overview.assessedOpportunities)}
          />
          <SupportItem
            hint="Preservados, ainda sem normalização"
            label="Itens brutos pendentes"
            value={String(overview.pendingNormalizations)}
          />
          <SupportItem
            label="Candidaturas ativas"
            to="/applications"
            value={String(overview.applicationsActive)}
          />
        </dl>
      </Block>

      <Block
        description="Como o ciclo está passando quando ninguém está olhando."
        title="Operação"
      >
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <SupportItem
            hint={`de ${overview.sourcesEnabled} habilitadas, ${overview.sourcesTotal} no catálogo`}
            label="Fontes com falha na última execução"
            value={String(overview.sourcesFailing)}
          />
          <SupportItem
            hint="Ollama indisponível, fora do contrato ou desligado"
            label="Análises degradadas"
            value={String(overview.analysesDegraded)}
          />
          <AnalysisSupport />
        </dl>
        <div className="mt-block">
          <FailingSources sources={overview.failingSources} />
        </div>
        <SourceMetricsSection />
      </Block>
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
          <SummarySkeleton />
        )}
        {overview.isError && (
          <ErrorState className="mt-8" onRetry={() => void overview.refetch()}>Não foi possível carregar o resumo.</ErrorState>
        )}
        {overview.data && <Summary overview={overview.data} />}
      </div>
    </PageShell>
  )
}
