import { type FormEvent, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Field, controlClassName } from '../components/Field'
import { PageShell } from '../components/PageShell'
import { CardListSkeleton } from '../components/skeletons'
import { EmptyState, ErrorState } from '../components/states'
import { SearchBar } from '../components/SearchBar'
import { StatusBadge } from '../components/StatusBadge'
import { Toolbar } from '../components/Toolbar'
import { type InboxItem, type InboxOrder, inboxOrders } from '../features/dashboard/api'
import { useInbox } from '../features/dashboard/useInbox'
import { verdictLabels, verdictTones } from '../features/matching/verdicts'
import { type ApplicationStage, stageLabels } from '../features/pipeline/api'

const pageSize = 25

const orderLabels: Record<InboxOrder, string> = {
  priority: 'Prioridade',
  recency: 'Mais recentes',
  score: 'Maior score',
}

const workModes = ['REMOTE', 'HYBRID', 'ONSITE', 'UNKNOWN']
const lifecycleStatuses = ['DISCOVERED', 'ACTIVE', 'STALE', 'CLOSED']

function display(value: string | null) {
  return value === null || value === '' ? '—' : value
}

function formatDate(value: string | null) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleDateString('pt-BR')
}

function formatScore(value: string | null) {
  if (value === null) return '—'
  const parsed = Number(value)
  return Number.isNaN(parsed) ? value : parsed.toFixed(1)
}

function VerdictBadge({ verdict }: { verdict: string | null }) {
  return (
    <StatusBadge
      absent="Não avaliada"
      labels={verdictLabels}
      tones={verdictTones}
      value={verdict}
    />
  )
}

const appliedOptions = [
  { value: '', label: 'Todas' },
  { value: 'true', label: 'Já aplicada' },
  { value: 'false', label: 'Ainda não aplicada' },
] as const

function ItemCard({ item }: { item: InboxItem }) {
  return (
    <Card as="article">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">
            <Link
              className="underline decoration-accent decoration-2 underline-offset-4"
              to={`/opportunities/${item.opportunityId}`}
            >
              {item.title}
            </Link>
          </h2>
          <p className="mt-1 text-sm text-muted">
            {display(item.companyName)} · {display(item.location)}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <VerdictBadge verdict={item.verdict} />
          {item.applied && (
            <span className="inline-flex rounded-full border border-success-line bg-success-surface px-3 py-1 text-xs font-medium text-success-ink">
              Candidatura: {stageLabels[item.applicationStage as ApplicationStage] ??
                item.applicationStage}
            </span>
          )}
          <span className="text-metric-sm">
            {formatScore(item.score)}
          </span>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-muted">Modalidade</dt>
          <dd className="mt-1 font-medium">{item.workMode}</dd>
        </div>
        <div>
          <dt className="text-muted">Senioridade</dt>
          <dd className="mt-1 font-medium">{item.seniority}</dd>
        </div>
        <div>
          <dt className="text-muted">Status</dt>
          <dd className="mt-1 font-medium">{item.lifecycleStatus}</dd>
        </div>
        <div>
          <dt className="text-muted">Publicada</dt>
          <dd className="mt-1 font-medium">{formatDate(item.publishedAt)}</dd>
        </div>
      </dl>

      {item.isStale && (
        <p className="mt-4 rounded-xl border border-warning-line bg-warning-surface p-3 text-sm text-warning-ink" role="status">
          Esta avaliação usa uma versão anterior do perfil ou da oportunidade. A
          reavaliação está pendente; o resultado anterior continua disponível.
          {item.assessmentProfileVersionId && item.currentProfileVersionId && (
            <> Perfil avaliado: {item.assessmentProfileVersionId.slice(0, 8)} · perfil atual: {item.currentProfileVersionId.slice(0, 8)}.</>
          )}
        </p>
      )}

      {item.analysisStatus && item.analysisStatus !== 'AI_COMPLETED' && (
        <p className="mt-4 text-sm text-warning-ink">
          Análise semântica indisponível ({item.analysisStatus}). A decisão determinística
          permanece completa.
        </p>
      )}
      {item.analysisSummary && (
        <p className="mt-4 text-prose text-subtle">{item.analysisSummary}</p>
      )}
      {item.analysisRecommendedReview === true && (
        <p className="mt-2 text-sm font-medium text-warning-ink">
          A análise sugere revisão humana antes de aplicar.
        </p>
      )}
    </Card>
  )
}

export function InboxPage() {
  const [params, setParams] = useSearchParams()
  const verdict = params.get('verdict') ?? ''
  const companyId = params.get('company_id') ?? ''
  const workMode = params.get('work_mode') ?? ''
  const lifecycleStatus = params.get('lifecycle_status') ?? ''
  const minimumScore = params.get('minimum_score') ?? ''
  const onlyAssessed = params.get('only_assessed') === 'true'
  const appliedFilter = params.get('applied') ?? ''
  const search = params.get('search') ?? ''
  const rawOrder = params.get('order') ?? 'priority'
  const order: InboxOrder = inboxOrders.includes(rawOrder as InboxOrder)
    ? (rawOrder as InboxOrder)
    : 'priority'
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)
  const [searchInput, setSearchInput] = useState(search)

  const inbox = useInbox({
    page,
    pageSize,
    verdicts: verdict ? [verdict] : undefined,
    minimumScore: minimumScore || undefined,
    companyId: companyId || undefined,
    workMode: workMode || undefined,
    lifecycleStatus: lifecycleStatus || undefined,
    onlyAssessed,
    applied: appliedFilter === '' ? undefined : appliedFilter === 'true',
    search: search || undefined,
    order,
  })
  const totalPages = inbox.data ? Math.max(1, Math.ceil(inbox.data.total / pageSize)) : 0

  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === '') next.delete(key)
      else next.set(key, value)
    }
    if (!('page' in changes)) next.delete('page')
    setParams(next)
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    update({ search: searchInput.trim() })
  }

  return (
    <PageShell
      current="/inbox"
      eyebrow="Decisão diária"
      title="Oportunidades"
      description="Tudo que o radar encontrou, com a decisão determinística mais recente de cada vaga. Oportunidades ainda não avaliadas continuam visíveis."
    >
      <SearchBar
        id="inbox-search"
        label="Buscar oportunidades"
        onChange={setSearchInput}
        onSubmit={submitSearch}
        placeholder="Título ou empresa"
        value={searchInput}
      />

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Field label="Verdict">
          <select
            className={controlClassName}
            onChange={(event) => update({ verdict: event.target.value })}
            value={verdict}
          >
            <option value="">Todos</option>
            {Object.entries(verdictLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Modalidade">
          <select
            className={controlClassName}
            onChange={(event) => update({ work_mode: event.target.value })}
            value={workMode}
          >
            <option value="">Todas</option>
            {workModes.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Status">
          <select
            className={controlClassName}
            onChange={(event) => update({ lifecycle_status: event.target.value })}
            value={lifecycleStatus}
          >
            <option value="">Todos</option>
            {lifecycleStatuses.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Score mínimo">
          <input
            className={controlClassName}
            max={100}
            min={0}
            onChange={(event) => update({ minimum_score: event.target.value })}
            type="number"
            value={minimumScore}
          />
        </Field>

        <Field label="Ordenar por">
          <select
            className={controlClassName}
            onChange={(event) => update({ order: event.target.value })}
            value={order}
          >
            {inboxOrders.map((value) => (
              <option key={value} value={value}>
                {orderLabels[value]}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <label className="mt-4 flex items-center gap-2 text-sm text-subtle">
        <input
          checked={onlyAssessed}
          className="h-4 w-4"
          onChange={(event) => update({ only_assessed: event.target.checked ? 'true' : null })}
          type="checkbox"
        />
        Somente oportunidades já avaliadas
      </label>

      {companyId && (
        <p className="mt-4 text-sm text-subtle">
          Filtrando por uma empresa.{' '}
          <button
            className="font-medium underline"
            onClick={() => update({ company_id: null })}
            type="button"
          >
            Remover filtro
          </button>
        </p>
      )}

      <Toolbar
        className="mt-4"
        label="Candidatura"
        onChange={(value) => update({ applied: value || null })}
        options={appliedOptions}
        showLabel
        value={appliedFilter}
      />

      <div className="mt-8 grid gap-3">
        {inbox.isPending && (
          <CardListSkeleton count={5} label="Carregando oportunidades…" />
        )}
        {inbox.isError && (
          <ErrorState onRetry={() => void inbox.refetch()}>Não foi possível carregar a inbox.</ErrorState>
        )}
        {inbox.data?.items.length === 0 && (
          <EmptyState>Nenhuma oportunidade encontrada com esses filtros.</EmptyState>
        )}
        {inbox.data && inbox.data.items.length > 0 && (
          <>
            <p className="text-sm text-muted">
              {inbox.data.total} oportunidade{inbox.data.total === 1 ? '' : 's'} encontrada
              {inbox.data.total === 1 ? '' : 's'}.
            </p>
            {inbox.data.items.map((item) => (
              <ItemCard item={item} key={item.opportunityId} />
            ))}
            {totalPages > 1 && (
              <nav
                aria-label="Paginação de oportunidades"
                className="mt-2 flex items-center justify-between gap-4"
              >
                <Button
                  disabled={page === 1}
                  onClick={() => update({ page: String(page - 1) })}
                  size="sm"
                  variant="secondary"
                >
                  Anterior
                </Button>
                <span className="text-sm text-muted">
                  Página {page} de {totalPages}
                </span>
                <Button
                  disabled={page >= totalPages}
                  onClick={() => update({ page: String(page + 1) })}
                  size="sm"
                  variant="secondary"
                >
                  Próxima
                </Button>
              </nav>
            )}
          </>
        )}
      </div>
    </PageShell>
  )
}
