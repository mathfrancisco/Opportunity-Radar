import { type FormEvent, useEffect, useId, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { Chip } from '../components/Chip'
import { PrimaryText, SecondaryText } from '../components/cells'
import { DataTable } from '../components/DataTable'
import { FirstRunGuide } from '../components/FirstRunGuide'
import { FilterBar } from '../components/FilterBar'
import { FilterPill } from '../components/FilterPill'
import { ChevronDownIcon } from '../components/icons'
import { NuggetMeter } from '../components/ui/NuggetMeter'
import { PageSizeSelect } from '../components/PageSizeSelect'
import { Pagination } from '../components/Pagination'
import { Field, controlClassName } from '../components/Field'
import { PageShell } from '../components/PageShell'
import { CardListSkeleton, TableSkeleton } from '../components/skeletons'
import { EmptyState, ErrorState } from '../components/states'
import { SearchInput } from '../components/SearchInput'
import { StatusBadge } from '../components/StatusBadge'
import {
  type InboxItem,
  type InboxOrder,
  estimatedDateHint,
  inboxOrders,
} from '../features/dashboard/api'
import { useInbox } from '../features/dashboard/useInbox'
import { nuggetsFromScore } from '../features/matching/nuggets'
import { verdictLabels, verdictTones } from '../features/matching/verdicts'
import { useActiveProfile } from '../features/profile/useProfile'
import { useMarkRelevance } from '../features/opportunities/useOpportunity'
import { type ApplicationStage, stageLabels } from '../features/pipeline/api'
import { roleFamilies } from '../features/dashboard/roleFamilies'
import { opportunityLabel, seniorityLabels, workModeLabels } from '../features/opportunities/labels'
import type { SavedSearch, SavedSearchFilters } from '../features/saved-searches/api'
import {
  useCreateSavedSearch,
  useDeleteSavedSearch,
  useOpenSavedSearch,
  useRenameSavedSearch,
  useSavedSearches,
} from '../features/saved-searches/useSavedSearches'

const defaultPageSize = 25
const pageSizeOptions = [10, 25, 50, 100] as const

const orderLabels: Record<InboxOrder, string> = {
  priority: 'Prioridade',
  recency: 'Mais recentes',
  score: 'Maior score',
}

const workModes = ['REMOTE', 'HYBRID', 'ONSITE', 'UNKNOWN']
const lifecycleStatuses = ['DISCOVERED', 'ACTIVE', 'STALE', 'CLOSED']
const seniorities = [
  'INTERN',
  'JUNIOR',
  'MID',
  'SENIOR',
  'STAFF',
  'LEAD',
  'MANAGER',
  'DIRECTOR',
  'UNKNOWN',
]
const lifecycleLabels: Record<string, string> = {
  DISCOVERED: 'Descoberta', ACTIVE: 'Ativa', STALE: 'Desatualizada', CLOSED: 'Encerrada',
}

function display(value: string | null) {
  return value === null || value === '' ? '—' : value
}

function formatDate(value: string | null) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleDateString('pt-BR')
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

/**
 * The score as a ten-nugget meter with the score in words beside it. Without a score the meter
 * is absent and the text says so; the verdict name is always written next to it by `VerdictBadge`.
 */
function ScoreMeter({ score }: { score: string | null }) {
  const met = nuggetsFromScore(score)
  if (score === null || met === null) return <span className="text-body-sm text-muted">Sem avaliação</span>
  return (
    <NuggetMeter
      label={`${Math.round(Number(score))} de 100`}
      met={met}
      missed={10 - met}
    />
  )
}

const duplicateTone = 'border-warning-line bg-warning-surface text-warning-ink'
const appliedTone = 'border-success-line bg-success-surface text-success-ink'

function StartupChip({ item }: { item: InboxItem }) {
  if (!item.startupStrength) return null
  return (
    <span data-testid="startup-badge">
      <Chip tone="border-accent bg-surface text-ink">
        Startup{item.startupBatch ? ` · YC ${item.startupBatch}` : ''}
        {item.startupStrength === 'weak' ? ' (sinal fraco)' : ''}
      </Chip>
    </span>
  )
}

/**
 * One row of the comparison table; below `md` the same row is a card. The explicit ARIA roles
 * keep row and cell semantics when the table is laid out as `display: block`. Everything that
 * decides (verdict, duplicate, startup) stays in the row.
 */
function ItemRow({ item }: { item: InboxItem }) {
  const mark = useMarkRelevance(item.opportunityId)
  return (
    <tr className="align-top" role="row">
      <td className="xl:min-w-56" role="cell">
        <PrimaryText className="break-anywhere">
          <Link
            className="inline-flex min-h-11 items-center underline decoration-accent decoration-2 underline-offset-4"
            to={`/opportunities/${item.opportunityId}`}
          >
            {item.title}
          </Link>
        </PrimaryText>
        <SecondaryText className="break-anywhere">
          {display(item.companyName)} · {display(item.location)}
        </SecondaryText>
        {item.analysisSummary && (
          <span data-testid="inbox-reason" className="mt-1 block break-anywhere text-caption text-ink">
            {item.analysisSummary}
          </span>
        )}
        {(item.hasPendingDuplicate || item.startupStrength || item.siblingCount > 0) && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {item.siblingCount > 0 && (
              <span data-testid="sibling-chip">
                <Chip tone="border-line bg-surface text-ink">
                  +{item.siblingCount} {item.siblingCount === 1 ? 'local' : 'locais'}
                </Chip>
              </span>
            )}
            {item.hasPendingDuplicate && <Chip tone={duplicateTone}>Possível duplicata</Chip>}
            <StartupChip item={item} />
          </div>
        )}
      </td>
      <td role="cell">
        <div className="flex flex-wrap items-center gap-2 xl:flex-col xl:items-start xl:gap-1.5">
          <ScoreMeter score={item.score} />
          <VerdictBadge verdict={item.verdict} />
          {item.applied && (
            <Chip tone={appliedTone}>
              Candidatura: {stageLabels[item.applicationStage as ApplicationStage] ??
                item.applicationStage}
            </Chip>
          )}
        </div>
      </td>
      <td className="xl:max-w-64" role="cell">
        <PrimaryText className="font-medium">
          {opportunityLabel(item.workMode, workModeLabels)} · {opportunityLabel(item.seniority, seniorityLabels)}
        </PrimaryText>
        <SecondaryText>Status {lifecycleLabels[item.lifecycleStatus] ?? 'Em revisão'}</SecondaryText>
        {item.isStale && (
          <SecondaryText className="mt-1.5 text-warning-ink">
            <span role="status">
              Esta avaliação usa uma versão anterior do perfil ou da vaga. A
              reavaliação está pendente; o resultado anterior continua disponível.
              {item.assessmentProfileVersionId && item.currentProfileVersionId && (
                <> Perfil avaliado: {item.assessmentProfileVersionId.slice(0, 8)} · perfil atual: {item.currentProfileVersionId.slice(0, 8)}.</>
              )}
            </span>
          </SecondaryText>
        )}
        {item.analysisStatus && item.analysisStatus !== 'AI_COMPLETED' && (
          <div className="mt-1.5 text-caption text-warning-ink">
            <p>A IA não leu esta vaga. O match ao lado continua valendo.</p>
            <details className="mt-1">
              <summary className="cursor-pointer">Detalhe técnico</summary>
              <p>{item.analysisStatus}</p>
            </details>
          </div>
        )}
        {item.analysisRecommendedReview === true && (
          <SecondaryText className="mt-1 font-medium text-warning-ink">
            A leitura da IA sugere revisar antes de se candidatar.
          </SecondaryText>
        )}
      </td>
      <td className="xl:whitespace-nowrap" role="cell">
        <span className="text-caption text-muted xl:hidden">Publicada </span>
        {formatDate(item.recencyEffectiveDate)}
        {item.dateIsEstimated && (
          <span title={estimatedDateHint(item.recencyBasis)}>
            <SecondaryText>(estimada)</SecondaryText>
          </span>
        )}
      </td>
      <td role="cell">
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={mark.isPending}
            onClick={() => mark.mutate({ relevant: true })}
            size="sm"
          >
            Relevante
          </Button>
          <Button
            disabled={mark.isPending}
            onClick={() => mark.mutate({ relevant: false })}
            size="sm"
            variant="secondary"
          >
            Não é para mim
          </Button>
        </div>
      </td>
    </tr>
  )
}

const tableColumns = ['Vaga', 'Score e decisão', 'Sinais', 'Publicada', 'Ações']

function filtersFromParams(params: URLSearchParams): SavedSearchFilters {
  const filters: SavedSearchFilters = {}
  for (const key of new Set(params.keys())) {
    if (key === 'page' || key === 'size') continue
    const values = params.getAll(key)
    filters[key] = values.length > 1 ? values : values[0]
  }
  return filters
}

function paramsFromFilters(filters: SavedSearchFilters): URLSearchParams {
  const next = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (Array.isArray(value)) value.forEach((item) => next.append(key, item))
    else next.set(key, String(value))
  }
  return next
}

/** Card F20-34: nome e filtros/termo atuais viram uma busca salva reaberta depois. */
export function SaveSearchForm({ filters, term }: { filters: SavedSearchFilters; term: string }) {
  const [name, setName] = useState('')
  const create = useCreateSavedSearch()

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    create.mutate(
      { name: trimmed, term: term || null, filters },
      { onSuccess: () => setName('') },
    )
  }

  return (
    <form className="mt-4 flex flex-wrap items-end gap-2" onSubmit={submit}>
      <Field label="Salvar esta busca">
        <input
          className={controlClassName}
          onChange={(event) => setName(event.target.value)}
          placeholder="Nome da busca"
          type="text"
          value={name}
        />
      </Field>
      <Button disabled={create.isPending || name.trim() === ''} type="submit">
        Salvar
      </Button>
      {create.isError && (
        <p className="text-sm text-danger-ink">Não foi possível salvar esta busca.</p>
      )}
    </form>
  )
}

function SavedSearchRow({
  savedSearch,
  onApply,
}: {
  savedSearch: SavedSearch
  onApply: (filters: SavedSearchFilters) => void
}) {
  const open = useOpenSavedSearch()
  const rename = useRenameSavedSearch(savedSearch.id)
  const remove = useDeleteSavedSearch()
  const [renaming, setRenaming] = useState(false)
  const [name, setName] = useState(savedSearch.name)

  if (renaming) {
    return (
      <li className="flex items-center gap-2 rounded-full border border-line-strong bg-surface px-3 py-1 text-sm">
        <input
          className="w-32 rounded border border-line-strong px-2 py-1 text-sm"
          onChange={(event) => setName(event.target.value)}
          value={name}
        />
        <button
          className="font-medium underline"
          onClick={() => {
            const trimmed = name.trim()
            if (trimmed) rename.mutate(trimmed)
            setRenaming(false)
          }}
          type="button"
        >
          Confirmar
        </button>
        <button onClick={() => setRenaming(false)} type="button">
          Cancelar
        </button>
      </li>
    )
  }

  return (
    <li className="flex items-center gap-2 rounded-full border border-line-strong bg-surface px-3 py-1 text-sm">
      <button
        className="font-medium underline"
        onClick={() => {
          onApply(savedSearch.filters)
          open.mutate(savedSearch.id)
        }}
        type="button"
      >
        {savedSearch.name}
      </button>
      <button onClick={() => setRenaming(true)} type="button">
        Renomear
      </button>
      <button onClick={() => remove.mutate(savedSearch.id)} type="button">
        Remover
      </button>
    </li>
  )
}

export function SavedSearches({ onApply }: { onApply: (filters: SavedSearchFilters) => void }) {
  const searches = useSavedSearches()
  if (!searches.data || searches.data.length === 0) return null
  return (
    <div className="mt-2">
      <p className="text-sm font-medium">Buscas salvas</p>
      <ul className="mt-2 flex flex-wrap gap-3">
        {searches.data.map((savedSearch) => (
          <SavedSearchRow key={savedSearch.id} onApply={onApply} savedSearch={savedSearch} />
        ))}
      </ul>
    </div>
  )
}

/**
 * "Buscas salvas" (D12): a disclosure button at the right of the filter bar. Esc closes it
 * and hands the focus back to the button; a press outside closes it too.
 */
export function SavedSearchesMenu({
  filters,
  term,
  onApply,
}: {
  filters: SavedSearchFilters
  term: string
  onApply: (filters: SavedSearchFilters) => void
}) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const panelId = useId()

  useEffect(() => {
    if (!open) return
    function outside(event: MouseEvent) {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', outside)
    return () => document.removeEventListener('mousedown', outside)
  }, [open])

  return (
    <div
      className="relative"
      onKeyDown={(event) => {
        if (event.key === 'Escape' && open) {
          setOpen(false)
          button.current?.focus()
        }
      }}
      ref={root}
    >
      <button
        aria-controls={panelId}
        aria-expanded={open}
        className="inline-flex h-8 items-center gap-1.5 rounded-control border border-line-strong bg-surface px-3 text-body-sm font-medium text-ink hover:border-ink max-md:h-11"
        onClick={() => setOpen((value) => !value)}
        ref={button}
        type="button"
      >
        Buscas salvas
        <ChevronDownIcon />
      </button>
      <div
        className="absolute right-0 z-10 mt-1 w-80 max-w-[calc(100vw-2rem)] rounded-control border border-line bg-surface p-4"
        hidden={!open}
        id={panelId}
      >
        {open && (
          <>
            <SavedSearches
              onApply={(next) => {
                onApply(next)
                setOpen(false)
              }}
            />
            <SaveSearchForm filters={filters} term={term} />
          </>
        )}
      </div>
    </div>
  )
}

function InboxSearch({
  search,
  onSubmit,
}: {
  search: string
  onSubmit: (value: string) => void
}) {
  const [searchInput, setSearchInput] = useState(search)

  return (
    <SearchInput
      fullWidth
      id="inbox-search"
      label="Buscar oportunidades"
      onChange={setSearchInput}
      onSubmit={() => onSubmit(searchInput.trim())}
      placeholder="Título ou empresa"
      value={searchInput}
    />
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
  const rawSize = Number(params.get('size'))
  const pageSize = (pageSizeOptions as readonly number[]).includes(rawSize)
    ? rawSize
    : defaultPageSize
  const allAreas = params.get('all_areas') === 'true'
  const areaFilter = params.getAll('area')
  const seniority = params.get('seniority') ?? ''
  const salaryMin = params.get('salary_min') ?? ''
  const salaryMax = params.get('salary_max') ?? ''
  const source = params.get('source') ?? ''
  const allowedCountry = params.get('allowed_country') ?? ''
  // Card F20-61: absent parameter means "filtered", matching the server's own
  // default — only an explicit `only_recent=false` (the "mostrar tudo" click) turns
  // the filter off.
  const onlyRecent = params.get('only_recent') !== 'false'
  // Card F48-16: window lens. '' is the 30-day default; `novas` narrows it to 14 days;
  // `abertas` shows whatever the source's last complete run still saw, no date limit.
  const lensParam = params.get('lens')
  const recencyLens: '' | 'novas' | 'abertas' =
    lensParam === 'novas' || lensParam === 'abertas' ? lensParam : ''
  // Card F20-54: display/filter only, never changes score or verdict.
  const onlyStartups = params.get('only_startups') === 'true'
  const activeFilterCount = [
    verdict,
    companyId,
    workMode,
    lifecycleStatus,
    minimumScore,
    onlyAssessed,
    appliedFilter,
    order !== 'priority',
    allAreas,
    ...areaFilter,
    seniority,
    salaryMin,
    salaryMax,
    source,
    allowedCountry,
    !onlyRecent,
    recencyLens,
    onlyStartups,
  ].filter(Boolean).length
  const advancedFilterCount = [
    companyId,
    lifecycleStatus,
    minimumScore,
    onlyAssessed,
    appliedFilter,
    allAreas,
    ...areaFilter,
    seniority,
    salaryMin,
    salaryMax,
    source,
    allowedCountry,
    !onlyRecent,
    onlyStartups,
  ].filter(Boolean).length
  const [searchReset, setSearchReset] = useState(0)
  const [advancedFiltersOpen, setAdvancedFiltersOpen] = useState(advancedFilterCount > 0)

  const profile = useActiveProfile()
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
    roleFamilies: allAreas || areaFilter.length === 0 ? undefined : areaFilter,
    allAreas,
    seniorities: seniority ? [seniority] : undefined,
    salaryMin: salaryMin || undefined,
    salaryMax: salaryMax || undefined,
    sourceDefinitionIds: source ? [source] : undefined,
    allowedCountry: allowedCountry || undefined,
    onlyRecent,
    recencyWindowDays: recencyLens === 'novas' ? 14 : undefined,
    openAtSource: recencyLens === 'abertas',
    onlyStartups,
  })

  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === '') next.delete(key)
      else next.set(key, value)
    }
    if (!('page' in changes)) next.delete('page')
    setParams(next)
  }

  function toggleArea(code: string) {
    const next = new URLSearchParams(params)
    next.delete('all_areas')
    const current = next.getAll('area')
    next.delete('area')
    const updated = current.includes(code)
      ? current.filter((item) => item !== code)
      : [...current, code]
    updated.forEach((item) => next.append('area', item))
    next.delete('page')
    setParams(next)
  }

  function showAllAreas() {
    const next = new URLSearchParams(params)
    next.delete('area')
    next.set('all_areas', 'true')
    next.delete('page')
    setParams(next)
  }

  function submitSearch(value: string) {
    update({ search: value })
  }

  function applySavedSearch(filters: SavedSearchFilters) {
    const next = paramsFromFilters(filters)
    setSearchReset((value) => value + 1)
    setParams(next)
  }

  function clearFilters() {
    const next = new URLSearchParams()
    // The search text is an explicit lookup rather than a faceted filter, and the page size is
    // a display preference. Retain both while returning every filter to its server default.
    if (search) next.set('search', search)
    if (pageSize !== defaultPageSize) next.set('size', String(pageSize))
    setParams(next)
  }

  return (
    <PageShell
      actions={
        <SavedSearchesMenu
          filters={filtersFromParams(params)}
          onApply={applySavedSearch}
          term={search}
        />
      }
      current="/inbox"
      eyebrow="Decidir"
      title="Inbox"
      description={
        inbox.data
          ? `${inbox.data.total} ${inbox.data.total === 1 ? 'vaga' : 'vagas'} para decidir.`
          : undefined
      }
    >
      <FilterBar
        search={
          <InboxSearch key={JSON.stringify([search, searchReset])} search={search} onSubmit={submitSearch} />
        }
        variant="toolbar"
      >
        <FilterPill
          id="inbox-verdict"
          label="Decisão"
          onChange={(value) => update({ verdict: value })}
          options={[
            { value: '', label: 'Todas' },
            ...Object.entries(verdictLabels).map(([value, label]) => ({ value, label })),
          ]}
          value={verdict}
        />
        <FilterPill
          id="inbox-work-mode"
          label="Modalidade"
          onChange={(value) => update({ work_mode: value })}
          options={[
            { value: '', label: 'Todas' },
            ...workModes.map((value) => ({ value, label: opportunityLabel(value, workModeLabels) })),
          ]}
          value={workMode}
        />
        <FilterPill
          defaultValue="priority"
          id="inbox-order"
          label="Ordenar por"
          onChange={(value) => update({ order: value })}
          options={inboxOrders.map((value) => ({ value, label: orderLabels[value] }))}
          value={order}
        />
        <FilterPill
          id="inbox-recency-lens"
          label="Recência"
          onChange={(value) => update({ lens: value || null })}
          options={[
            { value: '', label: 'Últimos 30 dias' },
            { value: 'novas', label: 'Novas (14 dias)' },
            { value: 'abertas', label: 'Abertas na fonte' },
          ]}
          value={recencyLens}
        />
      </FilterBar>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <p aria-live="polite" className="text-caption text-muted">
          {activeFilterCount === 0
            ? 'Nenhum filtro ativo'
            : `${activeFilterCount} filtro${activeFilterCount === 1 ? '' : 's'} ativo${
                activeFilterCount === 1 ? '' : 's'
              }`}
        </p>
        {activeFilterCount > 0 && (
          <button
            className="text-caption font-medium text-subtle underline hover:text-ink"
            onClick={clearFilters}
            type="button"
          >
            Limpar filtros
          </button>
        )}
      </div>

      <details
        className="mt-3 rounded-control border border-line bg-panel px-3 py-2"
        onToggle={(event) => setAdvancedFiltersOpen(event.currentTarget.open)}
        open={advancedFiltersOpen}
      >
        <summary className="cursor-pointer text-sm font-medium text-subtle">
          Filtros avançados
          {advancedFilterCount > 0 &&
            ` (${advancedFilterCount} ativo${advancedFilterCount === 1 ? '' : 's'})`}
        </summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <FilterPill
            id="inbox-status"
            label="Status"
            onChange={(value) => update({ lifecycle_status: value })}
            options={[
              { value: '', label: 'Todos' },
              ...lifecycleStatuses.map((value) => ({ value, label: value })),
            ]}
            value={lifecycleStatus}
          />
          <FilterPill
            id="inbox-seniority"
            label="Senioridade"
            onChange={(value) => update({ seniority: value })}
            options={[
              { value: '', label: 'Todas' },
              ...seniorities.map((value) => ({ value, label: opportunityLabel(value, seniorityLabels) })),
            ]}
            value={seniority}
          />
          <FilterPill
            id="inbox-applied"
            label="Candidatura"
            onChange={(value) => update({ applied: value || null })}
            options={appliedOptions}
            value={appliedFilter}
          />
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

          <Field label="Remuneração mínima">
            <input
              className={controlClassName}
              min={0}
              onChange={(event) => update({ salary_min: event.target.value })}
              type="number"
              value={salaryMin}
            />
          </Field>

          <Field label="Remuneração máxima">
            <input
              className={controlClassName}
              min={0}
              onChange={(event) => update({ salary_max: event.target.value })}
              type="number"
              value={salaryMax}
            />
          </Field>

          <Field label="Fonte (id)">
            <input
              className={controlClassName}
              onChange={(event) => update({ source: event.target.value })}
              placeholder="uuid da fonte"
              type="text"
              value={source}
            />
          </Field>

          <Field label="País permitido">
            <input
              className={controlClassName}
              onChange={(event) =>
                update({ allowed_country: event.target.value.trim().toUpperCase() })
              }
              placeholder="ISO, ex.: BR"
              type="text"
              value={allowedCountry}
            />
          </Field>
        </div>

      <label className="mt-4 flex items-center gap-2 text-sm text-subtle max-md:min-h-11">
        <input
          checked={onlyAssessed}
          className="h-4 w-4"
          onChange={(event) => update({ only_assessed: event.target.checked ? 'true' : null })}
          type="checkbox"
        />
        Somente oportunidades já avaliadas
      </label>

      <label className="mt-2 flex items-center gap-2 text-sm text-subtle max-md:min-h-11">
        <input
          checked={onlyRecent}
          className="h-4 w-4"
          onChange={(event) =>
            update({ only_recent: event.target.checked ? null : 'false' })
          }
          type="checkbox"
        />
        Mostrar só vagas dos últimos 30 dias (estágio, trainee e vagas com prazo de
        candidatura continuam visíveis)
      </label>

      <label className="mt-2 flex items-center gap-2 text-sm text-subtle max-md:min-h-11">
        <input
          checked={onlyStartups}
          className="h-4 w-4"
          onChange={(event) => update({ only_startups: event.target.checked ? 'true' : null })}
          type="checkbox"
        />
        Só startups (empresas com sinal de startup registrado)
      </label>

      <fieldset className="mt-4" aria-describedby="area-filter-hint">
        <legend className="text-sm font-medium">Área</legend>
        <p className="text-sm text-muted" id="area-filter-hint">
          Sem marcação, usa as áreas de interesse do perfil. Vagas fora do filtro nunca são
          apagadas — continuam buscáveis.
        </p>
        <div className="mt-2 flex flex-wrap gap-4">
          {roleFamilies.map((family) => (
            <label className="flex items-center gap-2 text-sm max-md:min-h-11" key={family.code}>
              <input
                checked={!allAreas && areaFilter.includes(family.code)}
                className="h-4 w-4"
                onChange={() => toggleArea(family.code)}
                type="checkbox"
              />
              {family.label}
            </label>
          ))}
        </div>
        {(allAreas || areaFilter.length > 0 || (inbox.data && inbox.data.offFilterCount > 0)) && (
          <p className="mt-2 text-sm text-subtle">
            {allAreas ? (
              'Mostrando todas as áreas.'
            ) : (
              <>
                {inbox.data ? inbox.data.offFilterCount : 0} vaga
                {inbox.data?.offFilterCount === 1 ? '' : 's'} em outras áreas.{' '}
                <button className="font-medium underline" onClick={showAllAreas} type="button">
                  Ver todas
                </button>
              </>
            )}
          </p>
        )}
      </fieldset>

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
      </details>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        {inbox.data?.items.some((item) => item.isStale) ? (
          <p className="text-sm text-warning-ink" role="status">
            Há avaliações desatualizadas; os resultados anteriores continuam identificados.
          </p>
        ) : <span />}
        <Button onClick={() => void inbox.refetch()} size="sm" variant="secondary">
          Atualizar resultados
        </Button>
      </div>

      <aside className="mt-4 rounded-panel border border-line bg-surface px-4 py-3 text-sm text-subtle" aria-label="Como interpretar as avaliações">
        Score, veredito e elegibilidade vêm de regras fixas. Fatores ausentes ou
        desconhecidos pedem revisão; a leitura da IA, quando existe, é consultiva e
        não altera o match. Resultados desatualizados permanecem identificados até nova avaliação.
      </aside>

      <div className="mt-5 grid gap-3">
        {inbox.isPending && (
          <>
            {/* One skeleton per breakpoint, the hidden one out of the accessibility tree. */}
            <div className="hidden xl:block">
              <TableSkeleton columns={tableColumns.length} label="Carregando vagas…" />
            </div>
            <div className="xl:hidden">
              <CardListSkeleton count={5} label="Carregando vagas…" />
            </div>
          </>
        )}
        {inbox.isError && (
          <ErrorState onRetry={() => void inbox.refetch()}>Não foi possível carregar a inbox.</ErrorState>
        )}
        {inbox.data?.items.length === 0 &&
          (activeFilterCount === 0 && !search ? (
            profile.data === null ? (
              <FirstRunGuide />
            ) : (
            <EmptyState>
              Nada novo para decidir. A próxima coleta acontece no próximo ciclo.
            </EmptyState>
            )
          ) : (
            <EmptyState>Nenhuma vaga encontrada com esses filtros.</EmptyState>
          ))}
        {inbox.data && inbox.data.items.length > 0 && (
          <>
            <p className="text-sm text-muted">
              {inbox.data.total} vaga{inbox.data.total === 1 ? '' : 's'} encontrada
              {inbox.data.total === 1 ? '' : 's'}.
            </p>
            <DataTable caption="Vagas" columns={tableColumns} stackBelowXl>
              {inbox.data.items.map((item) => (
                <ItemRow item={item} key={item.opportunityId} />
              ))}
            </DataTable>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
              <Pagination
                className="min-w-0 flex-1"
                itemLabel="oportunidades"
                label="Paginação de oportunidades"
                onPageChange={(next) => update({ page: next === 1 ? null : String(next) })}
                page={page}
                pageSize={pageSize}
                total={inbox.data.total}
              />
              <PageSizeSelect
                id="inbox-page-size"
                onChange={(size) =>
                  update({ size: size === defaultPageSize ? null : String(size) })
                }
                options={pageSizeOptions}
                value={pageSize}
              />
            </div>
          </>
        )}
      </div>
    </PageShell>
  )
}
