import { type FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
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
      <div className="hidden overflow-hidden rounded-2xl border border-[#dce4dc] md:block">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="bg-[#f2f5ef] text-xs uppercase tracking-[0.08em] text-[#6d827b]">
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
              <tr className="border-t border-[#e4ebe4]" key={company.id}>
                <td className="px-5 py-4">
                  <p className="font-semibold">{company.name}</p>
                  <p className="mt-1 text-[#6d827b]">{display(company.domain)}</p>
                </td>
                <td className="px-5 py-4">{display(company.priority)}</td>
                <td className="px-5 py-4">{display(company.status)}</td>
                <td className="px-5 py-4">{display(company.verificationState)}</td>
                <td className="max-w-64 px-5 py-4 text-[#547068]">
                  {sourceNames(company)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-3 md:hidden">
        {companies.map((company) => (
          <article className="rounded-2xl border border-[#dce4dc] p-4" key={company.id}>
            <h2 className="font-semibold">{company.name}</h2>
            <p className="mt-1 text-sm text-[#6d827b]">{display(company.domain)}</p>
            <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
              <div>
                <dt className="text-[#6d827b]">Prioridade</dt>
                <dd className="mt-1 font-medium">{display(company.priority)}</dd>
              </div>
              <div>
                <dt className="text-[#6d827b]">Status</dt>
                <dd className="mt-1 font-medium">{display(company.status)}</dd>
              </div>
              <div>
                <dt className="text-[#6d827b]">Verificação</dt>
                <dd className="mt-1 font-medium">{display(company.verificationState)}</dd>
              </div>
            </dl>
            <p className="mt-4 text-sm text-[#547068]">
              <span className="font-medium text-[#17322d]">Fontes: </span>
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
    <main className="min-h-screen bg-[#f2f5ef] px-5 py-7 text-[#17322d] sm:px-10 sm:py-10">
      <div className="mx-auto min-h-[calc(100vh-3.5rem)] max-w-5xl rounded-[2rem] border border-[#ced8ce] bg-[#fbfcf8] p-7 shadow-[0_24px_70px_rgba(23,50,45,0.10)] sm:p-12">
        <header
          className="flex flex-wrap items-center justify-between gap-4"
          aria-label="Opportunity Radar"
        >
          <Link className="flex items-center gap-3" to="/">
            <span className="grid h-10 w-10 place-items-center rounded-full bg-[#d7f06f] text-lg font-black">
              ◉
            </span>
            <span className="text-lg font-semibold tracking-tight">Opportunity Radar</span>
          </Link>
          <nav aria-label="Navegação principal" className="flex gap-4 text-sm font-medium">
            <Link className="text-[#547068] hover:text-[#17322d]" to="/">
              Status
            </Link>
            <Link
              aria-current="page"
              className="text-[#17322d] underline decoration-[#d7f06f] decoration-2 underline-offset-4"
              to="/companies"
            >
              Empresas
            </Link>
          </nav>
        </header>

        <section className="py-10 sm:py-14">
          <p className="text-sm font-medium text-[#547068]">Catálogo local</p>
          <h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] sm:text-5xl">
            Empresas
          </h1>
          <p className="mt-3 max-w-2xl leading-7 text-[#547068]">
            Consulte as empresas monitoradas e as fontes associadas a cada uma.
          </p>

          <form className="mt-8 flex max-w-xl gap-3" onSubmit={submit} role="search">
            <label className="sr-only" htmlFor="company-search">
              Buscar empresas
            </label>
            <input
              className="min-w-0 flex-1 rounded-xl border border-[#c8d4c8] bg-white px-4 py-3 outline-none focus:border-[#17322d] focus:ring-2 focus:ring-[#d7f06f]"
              id="company-search"
              onChange={(event) => setInput(event.target.value)}
              placeholder="Nome ou domínio"
              value={input}
            />
            <button
              className="rounded-xl bg-[#17322d] px-5 py-3 font-semibold text-white hover:bg-[#25483f] focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-[#d7f06f]"
              type="submit"
            >
              Buscar
            </button>
          </form>

          <div className="mt-8" aria-live="polite">
            {companies.isPending && (
              <p className="rounded-2xl bg-[#eef3df] p-5 text-[#5c694e]">
                Carregando empresas…
              </p>
            )}
            {companies.isError && (
              <div className="rounded-2xl bg-[#f9e4df] p-5 text-[#9b3e2e]">
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
              <p className="rounded-2xl border border-dashed border-[#c8d4c8] p-8 text-[#547068]">
                Nenhuma empresa encontrada{query ? ` para “${query}”` : ''}.
              </p>
            )}
            {companies.data && companies.data.items.length > 0 && (
              <>
                <p className="mb-4 text-sm text-[#6d827b]">
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
                    <button
                      className="rounded-xl border border-[#c8d4c8] px-4 py-2 font-medium disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={page === 1}
                      onClick={() => setPage((current) => current - 1)}
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
                      onClick={() => setPage((current) => current + 1)}
                      type="button"
                    >
                      Próxima
                    </button>
                  </nav>
                )}
              </>
            )}
          </div>
        </section>
      </div>
    </main>
  )
}
