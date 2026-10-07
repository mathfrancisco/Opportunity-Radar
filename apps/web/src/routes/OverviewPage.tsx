import { useQueries } from '@tanstack/react-query'
import { type ReactNode, useState } from 'react'
import { Link } from 'react-router-dom'
import { ButtonLink } from '../components/Button'
import { Card } from '../components/Card'
import { Chip } from '../components/Chip'
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
import { type SavedSearchFilters, getSavedSearchNewCount } from '../features/saved-searches/api'
import { useOpenSavedSearch, useSavedSearches } from '../features/saved-searches/useSavedSearches'
import { coverageLabels, coverageTones } from '../features/sources/states'

function savedSearchInboxLink(filters: SavedSearchFilters): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (Array.isArray(value)) value.forEach((item) => params.append(key, item))
    else params.set(key, value)
  }
  const query = params.toString()
  return query ? `/inbox?${query}` : '/inbox'
}

/** Uma ação possível: o que é, quantos, e para onde leva. A linha inteira é o link. */
function ActionRow({
  label,
  value,
  hint,
  to,
}: {
  label: string
  value: string
  hint?: string
  to: string
}) {
  return (
    <li className="border-b border-divider last:border-b-0">
      <Link
        className="flex items-center justify-between gap-4 p-4 hover:bg-accent-surface max-md:min-h-11"
        to={to}
      >
        <span className="min-w-0">
          <span className="block font-medium text-ink">{label}</span>
          {hint && <span className="block text-sm text-muted">{hint}</span>}
        </span>
        <span className="text-metric-sm tabular-nums text-ink">{value}</span>
      </Link>
    </li>
  )
}

/** Um número que leva a uma ação, em destaque. Os demais números ficam em `SupportItem`. */
function MetricBlock({
  label,
  value,
  hint,
  to,
}: {
  label: string
  value: string
  hint?: string
  to: string
}) {
  return (
    <div className="rounded-panel border border-line bg-panel p-4">
      <p className="text-metric tabular-nums text-ink">{value}</p>
      <p className="mt-1 text-sm">
        <Link className="underline decoration-accent decoration-2 underline-offset-4" to={to}>
          {label}
        </Link>
      </p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  )
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
          className="rounded-control border border-danger-line bg-danger-surface p-5"
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
    <tr className="align-top">
      <td className="min-w-40">
        <p className="break-anywhere font-medium">{source.name}</p>
        <p className="text-xs text-muted">{source.sourceType}</p>
        {source.incidentOpen && (
          <p className="mt-1 text-xs font-semibold text-danger-ink">Incidente aberto</p>
        )}
      </td>
      <td>
        <StatusBadge
          labels={coverageLabels}
          tones={coverageTones}
          value={source.coverageState}
        />
      </td>
      <td>
        {source.runs} execuç{source.runs === 1 ? 'ão' : 'ões'}
        <br />
        <span className="text-xs text-muted">
          {source.itemsPersisted} persistidos / {source.itemsSeen} vistos
        </span>
      </td>
      <td>
        <span className="text-xs text-muted">erro</span> {percent(source.errorRate)}
        <br />
        <span className="text-xs text-muted">dedupe</span> {percent(source.dedupeRate)}
        <br />
        <span className="text-xs text-muted">p95</span> {seconds(source.latencyP95Seconds)}
      </td>
      <td>
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
      <td>
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
  const generatedAt = metrics.data?.generatedAt

  const metricContext = active
    ? `Janela: ${active.window}. ${
        generatedAt
          ? `Consolidado em ${new Date(generatedAt).toLocaleString('pt-BR')}.`
          : 'O horário de consolidação não foi informado.'
      }`
    : 'Selecione uma janela quando as métricas estiverem disponíveis.'

  return (
    <section
      aria-labelledby="metricas-operacionais-titulo"
      className="mt-10"
      id="metricas-operacionais"
    >
      {/* A altura mínima é a dos botões de janela, que só existem depois da resposta. */}
      <div className="flex min-h-10 flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-section" id="metricas-operacionais-titulo">
            Métricas operacionais por fonte
          </h2>
          <p className="mt-1 text-xs text-muted">{metricContext}</p>
        </div>
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
 * A decisão e o acervo lado a lado e a operação abaixo, como a página pronta. Os títulos
 * são os de verdade, porque não dependem do dado.
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
      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <section>
          <p className="text-section">Decisão de hoje</p>
          <div className="mt-4 rounded-panel border border-line bg-surface">
            {[0, 1, 2, 3].map((row) => (
              <div
                className="flex items-center justify-between gap-4 border-b border-divider p-4 last:border-b-0"
                key={row}
              >
                <Bone className="w-40" />
                <Bone className="h-6 w-8" />
              </div>
            ))}
          </div>
        </section>
        <section>
          <p className="text-section">Acervo</p>
          <div className="mt-4 grid gap-3">
            {[0, 1].map((block) => (
              <div className="rounded-panel border border-line bg-panel p-4" key={block}>
                <Bone className="h-8 w-12" />
                <Bone className="mt-3 w-32" />
              </div>
            ))}
          </div>
          {supportLines([true, true, false])}
        </section>
      </div>
      <section className="mt-10 border-t border-line pt-8">
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

/**
 * Card F20-20: saldo diário, taxa de fallback e breaker por modelo, nas últimas 24 h.
 *
 * Some when AI is disabled or nothing was called in the window: the card still explains
 * why there is nothing to show, instead of disappearing silently.
 */
function AIUsageCard() {
  const metrics = useAnalysisMetrics()
  const ai = metrics.data?.ai
  const percent = (value: number | null) => (value === null ? '—' : `${(value * 100).toFixed(0)}%`)

  if (metrics.isError) {
    return (
      <Card>
        <p className="text-sm text-muted">IA (Groq)</p>
        <p className="mt-2 text-sm text-subtle">Não foi possível carregar as métricas de IA.</p>
      </Card>
    )
  }
  if (!ai || ai.state !== 'enabled') {
    return (
      <Card>
        <p className="text-sm text-muted">IA (Groq)</p>
        <p className="mt-2 text-sm text-subtle">
          {ai?.state === 'blocked_by_configuration'
            ? 'Bloqueada por configuração: falta a chave da Groq.'
            : 'Desligada (AI_ENABLED=false).'}
        </p>
      </Card>
    )
  }
  if (ai.byModel.length === 0) {
    return (
      <Card>
        <p className="text-sm text-muted">IA (Groq)</p>
        <p className="mt-2 text-sm text-subtle">
          Nenhuma chamada nas últimas {ai.windowHours} h.
        </p>
      </Card>
    )
  }

  return (
    <Card>
      <p className="text-sm text-muted">IA (Groq) · últimas {ai.windowHours} h</p>
      <ul className="mt-3 space-y-3">
        {ai.byModel.map((model) => {
          const used = model.dayRequestsLimit
            ? Math.min(1, model.dayRequestsUsed / model.dayRequestsLimit)
            : null
          const breakerOpen = model.breaker !== 'closed'
          return (
            <li key={model.model}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate text-sm font-medium">{model.model}</span>
                {breakerOpen && (
                  <Chip tone="border-danger-line bg-danger-surface text-danger-ink">
                    breaker {model.breaker}
                  </Chip>
                )}
              </div>
              {used !== null && (
                <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-line">
                  <div
                    className="h-full rounded-full bg-ink"
                    style={{ width: `${(used * 100).toFixed(0)}%` }}
                  />
                </div>
              )}
              <p className="mt-1 text-xs text-subtle">
                {model.dayRequestsUsed}
                {model.dayRequestsLimit ? ` / ${model.dayRequestsLimit}` : ''} req hoje ·
                {' '}fallback {percent(model.fallbackRate)} · 429 {percent(model.rateLimitedRate)}
              </p>
            </li>
          )
        })}
      </ul>
      {ai.cacheHitRate !== null && (
        <p className="mt-3 text-xs text-subtle">Cache hit: {percent(ai.cacheHitRate)}</p>
      )}
    </Card>
  )
}

function Block({
  title,
  description,
  children,
  id,
  className = '',
}: {
  title: string
  description: string
  children: ReactNode
  id: string
  className?: string
}) {
  return (
    <section aria-labelledby={`${id}-title`} className={`scroll-mt-6 ${className}`.trim()} id={id}>
      <h2 className="text-section" id={`${id}-title`}>
        {title}
      </h2>
      <p className="mt-1 text-sm text-muted">{description}</p>
      <div className="mt-4">{children}</div>
    </section>
  )
}

/**
 * O que exige decisão hoje.
 *
 * Primeiro bloco e coluna larga: se nada aqui pede ação, o operador pode parar de ler a
 * página, e a tela precisa deixar isso claro sem que ele desça até o fim.
 */
/** Card F20-34: só as buscas salvas com vaga nova desde a última abertura aparecem aqui. */
export function SavedSearchesWithNews() {
  const searches = useSavedSearches()
  const open = useOpenSavedSearch()
  const counts = useQueries({
    queries: (searches.data ?? []).map((savedSearch) => ({
      queryKey: ['saved-search-new-count', savedSearch.id],
      queryFn: () => getSavedSearchNewCount(savedSearch.id),
      enabled: searches.data !== undefined,
    })),
  })

  const withNews = (searches.data ?? []).flatMap((savedSearch, index) => {
    const count = counts[index]?.data
    return count ? [{ savedSearch, count }] : []
  })

  if (withNews.length === 0) return null

  return (
    <div className="mt-4">
      <h3 className="text-body-sm font-medium">Buscas salvas com novidade</h3>
      <DataTable
        caption="Buscas salvas com vagas novas"
        className="mt-2"
        columns={['Busca', 'Vagas novas']}
      >
        {withNews.map(({ savedSearch, count }) => (
          <tr key={savedSearch.id}>
            <td>
              <Link
                className="font-medium underline decoration-accent decoration-2 underline-offset-4"
                onClick={() => open.mutate(savedSearch.id)}
                to={savedSearchInboxLink(savedSearch.filters)}
              >
                {savedSearch.name}
              </Link>
            </td>
            <td className="font-semibold">{count}</td>
          </tr>
        ))}
      </DataTable>
    </div>
  )
}

function PendingDecisions({ overview }: { overview: Overview }) {
  const highPriority = overview.verdictCounts.HIGH_PRIORITY ?? 0
  const recommended = overview.verdictCounts.RECOMMENDED ?? 0
  const pending = highPriority + recommended + overview.newOpportunities + overview.followUpsDue
  const verdicts = verdictOrder.filter((verdict) => overview.verdictCounts[verdict] > 0)

  return (
    <section aria-labelledby="decisao-de-hoje-title" className="scroll-mt-6" id="decisao-de-hoje">
      <h2 className="text-section" id="decisao-de-hoje-title">
        Decisão de hoje
      </h2>
      {pending === 0 ? (
        <p className="mt-4 rounded-panel border border-success-line bg-success-surface p-5 text-success-ink">
          Nada exige decisão agora: sem vagas novas na janela, sem recomendações abertas e
          sem follow-up devido.
        </p>
      ) : (
        <ul className="mt-4 rounded-panel border border-line bg-surface">
          <ActionRow
            label="Alta prioridade"
            to="/inbox?verdict=HIGH_PRIORITY"
            value={String(highPriority)}
          />
          <ActionRow
            label="Recomendadas"
            to="/inbox?verdict=RECOMMENDED"
            value={String(recommended)}
          />
          <ActionRow
            label={`Novas (${overview.newOpportunityWindowDays} dias)`}
            to="/inbox?order=recency"
            value={String(overview.newOpportunities)}
          />
          <ActionRow
            hint={`Próximos ${overview.followUpWindowDays} dias`}
            label="Follow-ups devidos"
            to="/applications"
            value={String(overview.followUpsDue)}
          />
        </ul>
      )}

      {verdicts.length > 0 && (
        <DataTable
          caption="Vagas avaliadas por decisão"
          className="mt-4"
          columns={['Decisão', 'Vagas']}
        >
          {verdicts.map((verdict) => (
            <tr key={verdict}>
              <td>
                <Link
                  className="underline decoration-accent decoration-2 underline-offset-4"
                  to={`/inbox?verdict=${verdict}`}
                >
                  {verdictCountLabels[verdict] ?? verdict}
                </Link>
              </td>
              <td className="font-semibold tabular-nums">{overview.verdictCounts[verdict]}</td>
            </tr>
          ))}
        </DataTable>
      )}

      <StartupShortcut />

      <SavedSearchesWithNews />
    </section>
  )
}

/** Card F20-54: shortcut to the Inbox filtered to companies with startup evidence.
 * Display/filter only — it never changes any score or verdict. */
export function StartupShortcut() {
  return (
    <p className="mt-3 text-sm">
      <Link
        className="underline decoration-accent decoration-2 underline-offset-4"
        to="/inbox?only_startups=true"
      >
        Ver só startups
      </Link>
    </p>
  )
}

function Summary({ overview }: { overview: Overview }) {
  return (
    <>
      <nav aria-label="Seções da visão geral" className="flex flex-wrap gap-2">
        {[
          ['#decisao-de-hoje', 'Decisão de hoje'],
          ['#acervo', 'Acervo'],
          ['#operacao', 'Operação'],
        ].map(([href, label]) => (
          <a
            className="rounded-full border border-line-strong bg-surface px-3 py-1 text-sm font-medium text-subtle hover:border-ink hover:text-ink max-md:min-h-11"
            href={href}
            key={href}
          >
            {label}
          </a>
        ))}
      </nav>

      {/* Decisão na coluna larga, números que levam a uma ação na estreita: nessa ordem no DOM. */}
      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <PendingDecisions overview={overview} />

        <Block
          description="O que o radar já coletou e decidiu, e que continua disponível para consulta."
          id="acervo"
          title="Acervo"
        >
          <div className="grid gap-3">
            <MetricBlock
              hint="Com decisão determinística registrada"
              label="Avaliadas"
              to="/inbox?only_assessed=true"
              value={String(overview.assessedOpportunities)}
            />
            <MetricBlock
              label="Candidaturas ativas"
              to="/applications"
              value={String(overview.applicationsActive)}
            />
          </div>
          <dl className="mt-5 grid gap-3 text-sm">
            <SupportItem
              hint={`de ${overview.opportunitiesTotal} no total`}
              label="Oportunidades ativas"
              value={String(overview.opportunitiesActive)}
            />
            <SupportItem
              hint="Preservados, ainda sem normalização"
              label="Itens brutos pendentes"
              value={String(overview.pendingNormalizations)}
            />
            <SupportItem
              hint={
                overview.precisionPercent === null
                  ? `sem marcação suficiente · ${overview.companiesCovered} de ${overview.companiesWithAts} empresas cobertas`
                  : `(${overview.precisionMarkedCount} marcadas) · ${overview.companiesCovered} de ${overview.companiesWithAts} empresas cobertas`
              }
              label={`${overview.newOpportunityWindowDays} dias: vagas novas`}
              value={String(overview.newOpportunities)}
            />
            {overview.precisionPercent !== null && (
              <SupportItem
                hint={`${overview.precisionMarkedCount} marcadas`}
                label="Precisão da Inbox"
                value={`${Number(overview.precisionPercent).toFixed(0)}%`}
              />
            )}
          </dl>
        </Block>
      </div>

      {/* Operação por último e mais quieta: continua completa e acessível pelo salto acima. */}
      <Block
        className="mt-10 border-t border-line pt-8"
        description="Como o ciclo está passando quando ninguém está olhando."
        id="operacao"
        title="Operação"
      >
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <SupportItem
            hint={`de ${overview.sourcesEnabled} habilitadas, ${overview.sourcesTotal} no catálogo`}
            label="Fontes com falha na última execução"
            value={String(overview.sourcesFailing)}
          />
          <SupportItem
            hint="IA (Groq) indisponível, sem quota ou desligada"
            label="Análises degradadas"
            value={String(overview.analysesDegraded)}
          />
          <AnalysisSupport />
        </dl>
        <div className="mt-6">
          <FailingSources sources={overview.failingSources} />
        </div>
        <div className="mt-6">
          <AIUsageCard />
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
      actions={
        <ButtonLink to="/inbox">
          Abrir Inbox
        </ButtonLink>
      }
      current="/"
      eyebrow="Decidir"
      title="O que move sua busca esta semana?"
      description="Um ponto de partida calmo para escolher a próxima ação, com a origem dos dados à vista."
      footer="Descubra oportunidades, preserve evidências e decida com contexto."
    >
      <div>
        {overview.isPending && (
          <SummarySkeleton />
        )}
        {overview.isError && (
          <ErrorState onRetry={() => void overview.refetch()}>Não foi possível carregar o resumo.</ErrorState>
        )}
        {overview.data && <Summary overview={overview.data} />}
      </div>
    </PageShell>
  )
}
