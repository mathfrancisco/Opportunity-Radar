import { type FormEvent, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { PageShell } from '../components/PageShell'
import { type InboxItem, type InboxOrder, inboxOrders } from '../features/dashboard/api'
import { useInbox } from '../features/dashboard/useInbox'
import { type ApplicationStage, stageLabels } from '../features/pipeline/api'

const pageSize = 25

const verdictLabels: Record<string, string> = {
  HIGH_PRIORITY: 'Alta prioridade',
  RECOMMENDED: 'Recomendada',
  WATCHLIST: 'Observação',
  REVIEW_REQUIRED: 'Revisão necessária',
  LOW_MATCH: 'Baixa aderência',
  INELIGIBLE: 'Inelegível',
}

const orderLabels: Record<InboxOrder, string> = {
  priority: 'Prioridade',
  recency: 'Mais recentes',
  score: 'Maior score',
}

const workModes = ['REMOTE', 'HYBRID', 'ONSITE', 'UNKNOWN']
const lifecycleStatuses = ['DISCOVERED', 'ACTIVE', 'STALE', 'CLOSED']

const verdictTone: Record<string, string> = {
  HIGH_PRIORITY: 'border-[#b6d36a] bg-[#eef6d8] text-[#42571c]',
  RECOMMENDED: 'border-[#b6d36a] bg-[#f3f8e6] text-[#42571c]',
  REVIEW_REQUIRED: 'border-[#e3cf9a] bg-[#fbf3e2] text-[#7a5a16]',
  WATCHLIST: 'border-[#c8d4c8] bg-[#f2f5ef] text-[#41594f]',
  LOW_MATCH: 'border-[#c8d4c8] bg-[#f2f5ef] text-[#6d827b]',
  INELIGIBLE: 'border-[#e8cfc6] bg-[#fdf3f0] text-[#9b3e2e]',
}

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
  if (!verdict) {
    return (
      <span className="inline-flex rounded-full border border-dashed border-[#c8d4c8] px-3 py-1 text-xs text-[#6d827b]">
        Não avaliada
      </span>
    )
  }
  const tone = verdictTone[verdict] ?? 'border-[#c8d4c8] bg-[#f2f5ef] text-[#41594f]'
  return (
    <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${tone}`}>
      {verdictLabels[verdict] ?? verdict}
    </span>
  )
}

function ItemCard({ item }: { item: InboxItem }) {
  return (
    <article className="rounded-2xl border border-[#dce4dc] bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">
            <Link
              className="underline decoration-[#d7f06f] decoration-2 underline-offset-4"
              to={`/opportunities/${item.opportunityId}`}
            >
              {item.title}
            </Link>
          </h2>
          <p className="mt-1 text-sm text-[#6d827b]">
            {display(item.companyName)} · {display(item.location)}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <VerdictBadge verdict={item.verdict} />
          {item.applied && (
            <span className="inline-flex rounded-full border border-[#b6d36a] bg-[#eef6d8] px-3 py-1 text-xs font-medium text-[#42571c]">
              Candidatura: {stageLabels[item.applicationStage as ApplicationStage] ??
                item.applicationStage}
            </span>
          )}
          <span className="text-2xl font-semibold tracking-[-0.03em]">
            {formatScore(item.score)}
          </span>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-[#6d827b]">Modalidade</dt>
          <dd className="mt-1 font-medium">{item.workMode}</dd>
        </div>
        <div>
          <dt className="text-[#6d827b]">Senioridade</dt>
          <dd className="mt-1 font-medium">{item.seniority}</dd>
        </div>
        <div>
          <dt className="text-[#6d827b]">Status</dt>
          <dd className="mt-1 font-medium">{item.lifecycleStatus}</dd>
        </div>
        <div>
          <dt className="text-[#6d827b]">Publicada</dt>
          <dd className="mt-1 font-medium">{formatDate(item.publishedAt)}</dd>
        </div>
      </dl>

      {item.isStale && (
        <p className="mt-4 rounded-xl border border-[#e3cf9a] bg-[#fbf3e2] p-3 text-sm text-[#7a5a16]" role="status">
          Esta avaliação usa uma versão anterior do perfil ou da oportunidade. A
          reavaliação está pendente; o resultado anterior continua disponível.
          {item.assessmentProfileVersionId && item.currentProfileVersionId && (
            <> Perfil avaliado: {item.assessmentProfileVersionId.slice(0, 8)} · perfil atual: {item.currentProfileVersionId.slice(0, 8)}.</>
          )}
        </p>
      )}

      {item.analysisStatus && item.analysisStatus !== 'AI_COMPLETED' && (
        <p className="mt-4 text-sm text-[#7a5a16]">
          Análise semântica indisponível ({item.analysisStatus}). A decisão determinística
          permanece completa.
        </p>
      )}
      {item.analysisSummary && (
        <p className="mt-4 text-sm leading-6 text-[#547068]">{item.analysisSummary}</p>
      )}
      {item.analysisRecommendedReview === true && (
        <p className="mt-2 text-sm font-medium text-[#7a5a16]">
          A análise sugere revisão humana antes de aplicar.
        </p>
      )}
    </article>
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
      <form className="mt-8 flex max-w-xl gap-3" onSubmit={submitSearch} role="search">
        <label className="sr-only" htmlFor="inbox-search">
          Buscar oportunidades
        </label>
        <input
          className="min-w-0 flex-1 rounded-xl border border-[#c8d4c8] bg-white px-4 py-3 outline-none focus:border-[#17322d] focus:ring-2 focus:ring-[#d7f06f]"
          id="inbox-search"
          onChange={(event) => setSearchInput(event.target.value)}
          placeholder="Título ou empresa"
          value={searchInput}
        />
        <button
          className="rounded-xl bg-[#17322d] px-5 py-3 font-semibold text-white hover:bg-[#25483f] focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-[#d7f06f]"
          type="submit"
        >
          Buscar
        </button>
      </form>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="text-sm">
          <span className="text-[#6d827b]">Verdict</span>
          <select
            className="mt-1 w-full rounded-xl border border-[#c8d4c8] bg-white px-3 py-2"
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
        </label>

        <label className="text-sm">
          <span className="text-[#6d827b]">Modalidade</span>
          <select
            className="mt-1 w-full rounded-xl border border-[#c8d4c8] bg-white px-3 py-2"
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
        </label>

        <label className="text-sm">
          <span className="text-[#6d827b]">Status</span>
          <select
            className="mt-1 w-full rounded-xl border border-[#c8d4c8] bg-white px-3 py-2"
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
        </label>

        <label className="text-sm">
          <span className="text-[#6d827b]">Score mínimo</span>
          <input
            className="mt-1 w-full rounded-xl border border-[#c8d4c8] bg-white px-3 py-2"
            max={100}
            min={0}
            onChange={(event) => update({ minimum_score: event.target.value })}
            type="number"
            value={minimumScore}
          />
        </label>

        <label className="text-sm">
          <span className="text-[#6d827b]">Ordenar por</span>
          <select
            className="mt-1 w-full rounded-xl border border-[#c8d4c8] bg-white px-3 py-2"
            onChange={(event) => update({ order: event.target.value })}
            value={order}
          >
            {inboxOrders.map((value) => (
              <option key={value} value={value}>
                {orderLabels[value]}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="mt-4 flex items-center gap-2 text-sm text-[#547068]">
        <input
          checked={onlyAssessed}
          className="h-4 w-4"
          onChange={(event) => update({ only_assessed: event.target.checked ? 'true' : null })}
          type="checkbox"
        />
        Somente oportunidades já avaliadas
      </label>

      {companyId && (
        <p className="mt-4 text-sm text-[#547068]">
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

      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        <span className="text-[#6d827b]">Candidatura</span>
        {[
          { value: '', label: 'Todas' },
          { value: 'true', label: 'Já aplicada' },
          { value: 'false', label: 'Ainda não aplicada' },
        ].map((option) => (
          <button
            className={`rounded-full border px-4 py-2 font-medium ${
              appliedFilter === option.value
                ? 'border-[#17322d] bg-[#17322d] text-white'
                : 'border-[#c8d4c8] bg-white hover:border-[#17322d]'
            }`}
            key={option.value || 'all'}
            onClick={() => update({ applied: option.value || null })}
            type="button"
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="mt-8 grid gap-3" aria-live="polite">
        {inbox.isPending && (
          <p className="rounded-2xl bg-[#eef3df] p-5 text-[#5c694e]">
            Carregando oportunidades…
          </p>
        )}
        {inbox.isError && (
          <div className="rounded-2xl bg-[#f9e4df] p-5 text-[#9b3e2e]">
            <p>Não foi possível carregar a inbox.</p>
            <button
              className="mt-3 font-semibold underline"
              onClick={() => void inbox.refetch()}
              type="button"
            >
              Tentar novamente
            </button>
          </div>
        )}
        {inbox.data?.items.length === 0 && (
          <p className="rounded-2xl border border-dashed border-[#c8d4c8] p-8 text-[#547068]">
            Nenhuma oportunidade encontrada com esses filtros.
          </p>
        )}
        {inbox.data && inbox.data.items.length > 0 && (
          <>
            <p className="text-sm text-[#6d827b]">
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
                <button
                  className="rounded-xl border border-[#c8d4c8] px-4 py-2 font-medium disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={page === 1}
                  onClick={() => update({ page: String(page - 1) })}
                  type="button"
                >
                  Anterior
                </button>
                <span className="text-sm text-[#6d827b]">
                  Página {page} de {totalPages}
                </span>
                <button
                  className="rounded-xl border border-[#c8d4c8] px-4 py-2 font-medium disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={page >= totalPages}
                  onClick={() => update({ page: String(page + 1) })}
                  type="button"
                >
                  Próxima
                </button>
              </nav>
            )}
          </>
        )}
      </div>
    </PageShell>
  )
}
