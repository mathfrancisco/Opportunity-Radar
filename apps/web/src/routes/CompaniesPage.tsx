import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Chip } from '../components/Chip'
import { PrimaryText, SecondaryText } from '../components/cells'
import { CompanyForm } from '../components/CompanyForm'
import { DataTable } from '../components/DataTable'
import { FilterBar } from '../components/FilterBar'
import { PageShell } from '../components/PageShell'
import { PageSizeSelect } from '../components/PageSizeSelect'
import { Pagination } from '../components/Pagination'
import { SearchInput } from '../components/SearchInput'
import { CardListSkeleton, TableSkeleton } from '../components/skeletons'
import { EmptyState, ErrorState } from '../components/states'
import { type Company } from '../features/companies/api'
import { useCompanies, useRegisterCompany } from '../features/companies/useCompanies'
import { useMediaQuery } from '../lib/useMediaQuery'

const defaultPageSize = 25
// The endpoint accepts page_size up to 100 (companies.py).
const pageSizeOptions = [10, 25, 50, 100] as const
const tableColumns = ['Empresa', 'Prioridade', 'Status', 'Verificação', 'Fontes']

const priorityLabels: Record<string, string> = {
  high: 'Alta',
  normal: 'Normal',
  low: 'Baixa',
}

const statusLabels: Record<string, string> = {
  active: 'Ativa',
  paused: 'Pausada',
  backlog: 'Em fila',
}

const verificationLabels: Record<string, string> = {
  VERIFIED: 'Verificada',
  PENDING: 'Pendente',
  UNVERIFIED: 'Não verificada',
  unknown: 'Não informada',
  unverified: 'Não verificada',
  ats_identified: 'ATS identificado',
  careers_confirmed: 'Carreiras confirmadas',
  backlog: 'Em fila de homologação',
}

function display(value: string | number | null | undefined) {
  return value === undefined || value === null || value === '' ? '—' : value
}

function sourceNames(company: Company) {
  if (!company.sources?.length) return 'Nenhuma fonte cadastrada'
  return company.sources
    .map((source) => {
      const name = source.name ?? source.url ?? 'Fonte sem nome'
      return source.status ? `${name} (${sourceStatusLabels[source.status] ?? source.status})` : name
    })
    .join(', ')
}

/** A value as an outlined chip; a missing one stays a plain dash. */
function ValueChip({
  value,
  labels,
}: {
  value: string | number | null | undefined
  labels?: Record<string, string>
}) {
  const shown = display(value)
  if (shown === '—') return <span className="text-muted">—</span>
  const key = String(shown)
  return <Chip>{labels?.[key] ?? key}</Chip>
}

const sourceStatusLabels: Record<string, string> = {
  VERIFIED: 'Verificada',
  PENDING: 'Pendente',
  UNVERIFIED: 'Não verificada',
  unverified: 'Não verificada',
  ats_identified: 'ATS identificado',
  careers_confirmed: 'Carreiras confirmadas',
  backlog: 'Em fila de homologação',
}

function CompanyLink({ company }: { company: Company }) {
  return (
    <Link
      className="underline decoration-accent decoration-2 underline-offset-4"
      to={`/companies/${company.id}`}
    >
      {company.name}
    </Link>
  )
}

function CompanyList({ companies, isDesktop }: { companies: Company[]; isDesktop: boolean }) {
  if (isDesktop) {
    return (
      <DataTable caption="Empresas" columns={tableColumns}>
        {companies.map((company) => (
          <tr key={company.id}>
            <td>
              <PrimaryText>
                <CompanyLink company={company} />
              </PrimaryText>
              <SecondaryText>{display(company.domain)}</SecondaryText>
            </td>
            <td>
              <ValueChip labels={priorityLabels} value={company.priority} />
            </td>
            <td>
              <ValueChip labels={statusLabels} value={company.status} />
            </td>
            <td>
              <ValueChip labels={verificationLabels} value={company.verificationState} />
            </td>
            <td className="break-anywhere max-w-64 text-muted">{sourceNames(company)}</td>
          </tr>
        ))}
      </DataTable>
    )
  }
  return (
    <div className="grid gap-3">
      {companies.map((company) => (
        <Card as="article" key={company.id}>
          <h2 className="font-semibold">
            <CompanyLink company={company} />
          </h2>
          <p className="mt-1 text-sm text-muted">{display(company.domain)}</p>
          <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-3 text-sm">
            <div>
              <dt className="text-muted">Prioridade</dt>
              <dd className="mt-1">
                <ValueChip labels={priorityLabels} value={company.priority} />
              </dd>
            </div>
            <div>
              <dt className="text-muted">Status</dt>
              <dd className="mt-1">
                <ValueChip labels={statusLabels} value={company.status} />
              </dd>
            </div>
            <div>
              <dt className="text-muted">Verificação</dt>
              <dd className="mt-1">
                <ValueChip labels={verificationLabels} value={company.verificationState} />
              </dd>
            </div>
          </dl>
          <p className="mt-4 text-sm text-muted">
            <span className="font-medium text-ink">Fontes: </span>
            {sourceNames(company)}
          </p>
        </Card>
      ))}
    </div>
  )
}

export function CompaniesPage() {
  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<number>(defaultPageSize)
  const [priority, setPriority] = useState('')
  const [status, setStatus] = useState('')
  const [verification, setVerification] = useState('')
  const isDesktop = useMediaQuery('(min-width: 768px)')
  const companies = useCompanies({ page, pageSize, q: query })
  const register = useRegisterCompany()
  const [creating, setCreating] = useState(false)

  function submit() {
    setQuery(input.trim())
    setPage(1)
  }

  const visibleCompanies = (companies.data?.items ?? []).filter((company) =>
    (!priority || String(company.priority) === priority) &&
    (!status || company.status === status) &&
    (!verification || company.verificationState === verification),
  )
  const hasLocalFilters = Boolean(priority || status || verification)

  return (
    <PageShell
      current="/companies"
      eyebrow="Catálogo local"
      title="Empresas"
      description="Consulte as empresas monitoradas e as fontes associadas a cada uma."
    >
      <div className="mt-8">
        {creating ? (
          <CompanyForm
            company={null}
            error={register.error}
            onCancel={() => {
              register.reset()
              setCreating(false)
            }}
            onSubmit={(input) =>
              register.mutate(input, { onSuccess: () => setCreating(false) })
            }
            pending={register.isPending}
          />
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => setCreating(true)}>Nova empresa</Button>
            {register.data && (
              <p className="text-sm text-success-ink" role="status">
                {register.data.outcome === 'created'
                  ? 'Empresa cadastrada: '
                  : 'O nome já era conhecido, e a empresa existente respondeu: '}
                <Link
                  className="font-medium text-ink underline decoration-accent decoration-2 underline-offset-4"
                  to={`/companies/${register.data.company.id}`}
                >
                  {register.data.company.name}
                </Link>
                {register.data.outcome === 'matched' &&
                  (register.data.aliasesAdded > 0
                    ? ` — ${register.data.aliasesAdded} alias novo${register.data.aliasesAdded === 1 ? '' : 's'} registrado${register.data.aliasesAdded === 1 ? '' : 's'}.`
                    : ' — nenhum alias novo, o nome digitado já estava registrado.')}
              </p>
            )}
          </div>
        )}
      </div>

      <FilterBar
        label="Busca de empresas"
        search={
          <SearchInput
            id="company-search"
            label="Buscar empresas"
            onChange={setInput}
            onSubmit={submit}
            placeholder="Nome ou domínio"
            value={input}
          />
        }
      >
        <label className="sr-only" htmlFor="company-priority">Prioridade</label>
        <select
          className="h-9 rounded-control border border-line-strong bg-surface px-3 text-sm text-ink max-md:min-h-11"
          id="company-priority"
          onChange={(event) => setPriority(event.target.value)}
          value={priority}
        >
          <option value="">Todas as prioridades</option>
          <option value="high">Prioridade alta</option>
          <option value="normal">Prioridade normal</option>
          <option value="low">Prioridade baixa</option>
        </select>
        <label className="sr-only" htmlFor="company-status">Status</label>
        <select
          className="h-9 rounded-control border border-line-strong bg-surface px-3 text-sm text-ink max-md:min-h-11"
          id="company-status"
          onChange={(event) => setStatus(event.target.value)}
          value={status}
        >
          <option value="">Todos os status</option>
          <option value="active">Ativas</option>
          <option value="paused">Pausadas</option>
          <option value="backlog">Em fila</option>
        </select>
        <label className="sr-only" htmlFor="company-verification">Verificação</label>
        <select
          className="h-9 rounded-control border border-line-strong bg-surface px-3 text-sm text-ink max-md:min-h-11"
          id="company-verification"
          onChange={(event) => setVerification(event.target.value)}
          value={verification}
        >
          <option value="">Qualquer verificação</option>
          <option value="ats_identified">ATS identificado</option>
          <option value="careers_confirmed">Carreiras confirmadas</option>
          <option value="backlog">Em fila de homologação</option>
        </select>
        {hasLocalFilters && (
          <Button
            onClick={() => {
              setPriority('')
              setStatus('')
              setVerification('')
            }}
            variant="secondary"
          >
            Limpar filtros
          </Button>
        )}
      </FilterBar>

      <div className="mt-6">
        {companies.isPending &&
          (isDesktop ? (
            <TableSkeleton columns={tableColumns.length} label="Carregando empresas…" />
          ) : (
            <CardListSkeleton label="Carregando empresas…" />
          ))}
        {companies.isError && (
          <ErrorState onRetry={() => void companies.refetch()}>Não foi possível carregar as empresas.</ErrorState>
        )}
        {companies.data?.items.length === 0 && (
          <EmptyState>Nenhuma empresa encontrada{query ? ` para “${query}”` : ''}.</EmptyState>
        )}
        {companies.data && companies.data.items.length > 0 && (
          <>
            <p className="mb-3 text-sm text-muted">
              {companies.data.total} empresa
              {companies.data.total === 1 ? '' : 's'} encontrada
              {companies.data.total === 1 ? '' : 's'}.
              {hasLocalFilters && (
                <span className="block mt-1">
                  {visibleCompanies.length} de {companies.data.items.length} exibida
                  {visibleCompanies.length === 1 ? '' : 's'} nesta página após os filtros.
                </span>
              )}
            </p>
            {visibleCompanies.length > 0 ? (
              <CompanyList companies={visibleCompanies} isDesktop={isDesktop} />
            ) : (
              <EmptyState>Nenhuma empresa desta página corresponde aos filtros selecionados.</EmptyState>
            )}
            <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
              <Pagination
                className="min-w-0 flex-1"
                itemLabel="empresas"
                label="Paginação de empresas"
                onPageChange={setPage}
                page={page}
                pageSize={pageSize}
                total={companies.data.total}
              />
              <PageSizeSelect
                id="companies-page-size"
                onChange={(size) => {
                  setPageSize(size)
                  setPage(1)
                }}
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
