import { type FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../components/Button'
import { CompanyForm } from '../components/CompanyForm'
import { PageShell } from '../components/PageShell'
import { CardListSkeleton, TableSkeleton } from '../components/skeletons'
import { EmptyState, ErrorState } from '../components/states'
import { SearchBar } from '../components/SearchBar'
import { type Company } from '../features/companies/api'
import { useCompanies, useRegisterCompany } from '../features/companies/useCompanies'

const pageSize = 25

function display(value: string | number | null | undefined) {
  return value === undefined || value === null || value === '' ? '—' : value
}

function sourceNames(company: Company) {
  if (!company.sources?.length) return 'Nenhuma fonte cadastrada'
  return company.sources
    .map((source) => {
      const name = source.name ?? source.url ?? 'Fonte sem nome'
      return source.status ? `${name} (${source.status})` : name
    })
    .join(', ')
}

function CompanyList({ companies }: { companies: Company[] }) {
  return (
    <>
      <div className="hidden overflow-hidden rounded-2xl border border-line md:block">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="bg-canvas text-overline uppercase text-muted">
            <tr>
              <th className="px-5 py-4 font-semibold" scope="col">Empresa</th>
              <th className="px-5 py-4 font-semibold" scope="col">Prioridade</th>
              <th className="px-5 py-4 font-semibold" scope="col">Status</th>
              <th className="px-5 py-4 font-semibold" scope="col">Verificação</th>
              <th className="px-5 py-4 font-semibold" scope="col">Fontes</th>
            </tr>
          </thead>
          <tbody>
            {companies.map((company) => (
              <tr className="border-t border-divider" key={company.id}>
                <td className="px-5 py-4">
                  <p className="font-semibold">
                    <Link
                      className="underline decoration-accent decoration-2 underline-offset-4"
                      to={`/companies/${company.id}`}
                    >
                      {company.name}
                    </Link>
                  </p>
                  <p className="mt-1 text-muted">{display(company.domain)}</p>
                </td>
                <td className="px-5 py-4">{display(company.priority)}</td>
                <td className="px-5 py-4">{display(company.status)}</td>
                <td className="px-5 py-4">{display(company.verificationState)}</td>
                <td className="break-anywhere max-w-64 px-5 py-4 text-subtle">
                  {sourceNames(company)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-3 md:hidden">
        {companies.map((company) => (
          <article className="rounded-2xl border border-line p-4" key={company.id}>
            <h2 className="font-semibold">
              <Link
                className="underline decoration-accent decoration-2 underline-offset-4"
                to={`/companies/${company.id}`}
              >
                {company.name}
              </Link>
            </h2>
            <p className="mt-1 text-sm text-muted">{display(company.domain)}</p>
            <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
              <div>
                <dt className="text-muted">Prioridade</dt>
                <dd className="mt-1 font-medium">{display(company.priority)}</dd>
              </div>
              <div>
                <dt className="text-muted">Status</dt>
                <dd className="mt-1 font-medium">{display(company.status)}</dd>
              </div>
              <div>
                <dt className="text-muted">Verificação</dt>
                <dd className="mt-1 font-medium">{display(company.verificationState)}</dd>
              </div>
            </dl>
            <p className="mt-4 text-sm text-subtle">
              <span className="font-medium text-ink">Fontes: </span>
              {sourceNames(company)}
            </p>
          </article>
        ))}
      </div>
    </>
  )
}

export function CompaniesPage() {
  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const companies = useCompanies({ page, pageSize, q: query })
  const register = useRegisterCompany()
  const [creating, setCreating] = useState(false)
  const totalPages = companies.data ? Math.ceil(companies.data.total / pageSize) : 0

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setQuery(input.trim())
    setPage(1)
  }

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

      <SearchBar
        id="company-search"
        label="Buscar empresas"
        onChange={setInput}
        onSubmit={submit}
        placeholder="Nome ou domínio"
        value={input}
      />

      <div className="mt-8">
        {companies.isPending && (
          <>
            {/* A mesma troca de forma da lista: tabela em tela larga, cartões na estreita. A
                variante escondida sai também da árvore de acessibilidade, então o anúncio
                continua sendo um só. */}
            <div className="hidden md:block">
              <TableSkeleton columns={5} label="Carregando empresas…" />
            </div>
            <div className="md:hidden">
              <CardListSkeleton label="Carregando empresas…" />
            </div>
          </>
        )}
        {companies.isError && (
          <ErrorState onRetry={() => void companies.refetch()}>Não foi possível carregar as empresas.</ErrorState>
        )}
        {companies.data?.items.length === 0 && (
          <EmptyState>Nenhuma empresa encontrada{query ? ` para “${query}”` : ''}.</EmptyState>
        )}
        {companies.data && companies.data.items.length > 0 && (
          <>
            <p className="mb-4 text-sm text-muted">
              {companies.data.total} empresa
              {companies.data.total === 1 ? '' : 's'} encontrada
              {companies.data.total === 1 ? '' : 's'}.
            </p>
            <CompanyList companies={companies.data.items} />
            {totalPages > 1 && (
              <nav
                aria-label="Paginação de empresas"
                className="mt-6 flex items-center justify-between gap-4"
              >
                <Button
                  disabled={page === 1}
                  onClick={() => setPage((current) => current - 1)}
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
                  onClick={() => setPage((current) => current + 1)}
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
