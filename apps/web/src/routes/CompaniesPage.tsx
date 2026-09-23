import { type FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../components/Button'
import { PageShell } from '../components/PageShell'
import { SearchBar } from '../components/SearchBar'
import { type Company } from '../features/companies/api'
import { useCompanies } from '../features/companies/useCompanies'

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
          <thead className="bg-canvas text-xs uppercase tracking-[0.08em] text-muted">
            <tr>
              <th className="px-5 py-4 font-semibold">Empresa</th>
              <th className="px-5 py-4 font-semibold">Prioridade</th>
              <th className="px-5 py-4 font-semibold">Status</th>
              <th className="px-5 py-4 font-semibold">Verificação</th>
              <th className="px-5 py-4 font-semibold">Fontes</th>
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
                <td className="max-w-64 px-5 py-4 text-subtle">
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
      <SearchBar
        id="company-search"
        label="Buscar empresas"
        onChange={setInput}
        onSubmit={submit}
        placeholder="Nome ou domínio"
        value={input}
      />

      <div className="mt-8" aria-live="polite">
        {companies.isPending && (
          <p className="rounded-2xl bg-info-surface p-5 text-info-ink">
            Carregando empresas…
          </p>
        )}
        {companies.isError && (
          <div className="rounded-2xl bg-danger-surface-strong p-5 text-danger-ink">
            <p>Não foi possível carregar as empresas.</p>
            <button
              className="mt-3 font-semibold underline"
              onClick={() => void companies.refetch()}
              type="button"
            >
              Tentar novamente
            </button>
          </div>
        )}
        {companies.data?.items.length === 0 && (
          <p className="rounded-2xl border border-dashed border-line-strong p-8 text-subtle">
            Nenhuma empresa encontrada{query ? ` para “${query}”` : ''}.
          </p>
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
