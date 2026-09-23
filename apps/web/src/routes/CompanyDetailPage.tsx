import { Link, useParams } from 'react-router-dom'
import { Card } from '../components/Card'
import { PageShell } from '../components/PageShell'
import { type CompanyDetail } from '../features/companies/api'
import { useCompany, useDetectCompanySource } from '../features/companies/useCompanies'
import { useInbox } from '../features/dashboard/useInbox'

function formatDate(value: string | null) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString('pt-BR')
}

function Sources({ company }: { company: CompanyDetail }) {
  if (company.sources.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-line-strong p-5 text-subtle">
        Nenhuma fonte associada. A pesquisa registrou a empresa, mas nenhum endpoint foi
        confirmado.
      </p>
    )
  }
  return (
    <ul className="grid gap-3">
      {company.sources.map((source) => (
        <Card as="li" className="text-sm" key={source.id}>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-semibold">{source.name}</span>
            <span className="text-muted">{source.status}</span>
          </div>
          {source.url && <p className="mt-1 break-all text-subtle">{source.url}</p>}
          <p className="mt-2 text-xs text-muted">
            Verificação: {source.verificationMethod ?? 'não informada'} · última em{' '}
            {formatDate(source.lastVerifiedAt)}
            {source.externalKey ? ` · chave ${source.externalKey}` : ''}
          </p>
          {source.evidence && (
            <p className="mt-2 text-subtle">{source.evidence}</p>
          )}
        </Card>
      ))}
    </ul>
  )
}

function LatestOpportunities({ companyId }: { companyId: string }) {
  const inbox = useInbox({ page: 1, pageSize: 5, companyId, order: 'recency' })

  if (inbox.isPending) {
    return <p className="text-sm text-subtle">Carregando vagas…</p>
  }
  if (inbox.isError) {
    return (
      <div className="rounded-2xl bg-danger-surface-strong p-5 text-sm text-danger-ink">
        <p>Não foi possível carregar as vagas desta empresa.</p>
        <button
          className="mt-3 font-semibold underline"
          onClick={() => void inbox.refetch()}
          type="button"
        >
          Tentar novamente
        </button>
      </div>
    )
  }
  if (!inbox.data || inbox.data.items.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-line-strong p-5 text-subtle">
        Nenhuma vaga coletada desta empresa até agora.
      </p>
    )
  }
  return (
    <>
      <ul className="grid gap-2">
        {inbox.data.items.map((item) => (
          <li
            className="flex flex-wrap items-baseline justify-between gap-3 rounded-2xl border border-line bg-surface p-4 text-sm"
            key={item.opportunityId}
          >
            <Link
              className="font-medium underline decoration-accent decoration-2 underline-offset-4"
              to={`/opportunities/${item.opportunityId}`}
            >
              {item.title}
            </Link>
            <span className="text-muted">
              {item.workMode} · {item.verdict ?? 'não avaliada'}
              {item.score ? ` · ${Number(item.score).toFixed(1)}` : ''}
            </span>
          </li>
        ))}
      </ul>
      {inbox.data.total > inbox.data.items.length && (
        <p className="mt-3 text-sm">
          <Link
            className="underline decoration-accent decoration-2 underline-offset-4"
            to={`/inbox?company_id=${companyId}`}
          >
            Ver todas as {inbox.data.total} vagas
          </Link>
        </p>
      )}
    </>
  )
}

export function CompanyDetailPage() {
  const { companyId = '' } = useParams()
  const company = useCompany(companyId)
  const detectSource = useDetectCompanySource(companyId)

  return (
    <PageShell
      eyebrow="Catálogo local"
      title={company.data?.name ?? 'Empresa'}
      description={company.data?.domain ?? undefined}
    >
      <p className="mt-2">
        <Link
          className="text-sm text-subtle underline decoration-accent decoration-2 underline-offset-4"
          to="/companies"
        >
          ← Voltar para as empresas
        </Link>
      </p>

      <div aria-live="polite">
        {company.isPending && (
          <p className="mt-8 rounded-2xl bg-info-surface p-5 text-info-ink">
            Carregando empresa…
          </p>
        )}
        {company.isError && (
          <div className="mt-8 rounded-2xl bg-danger-surface-strong p-5 text-danger-ink">
            <p>{company.error.message}</p>
            <button
              className="mt-3 font-semibold underline"
              onClick={() => void company.refetch()}
              type="button"
            >
              Tentar novamente
            </button>
          </div>
        )}
      </div>

      {company.data && (
        <>
          <dl className="mt-8 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-muted">Prioridade</dt>
              <dd className="mt-1 font-medium">{company.data.priority}</dd>
            </div>
            <div>
              <dt className="text-muted">Status no radar</dt>
              <dd className="mt-1 font-medium">{company.data.status}</dd>
            </div>
            <div>
              <dt className="text-muted">Verificação</dt>
              <dd className="mt-1 font-medium">{company.data.verificationState}</dd>
            </div>
            <div>
              <dt className="text-muted">Última verificação</dt>
              <dd className="mt-1 font-medium">{formatDate(company.data.lastVerifiedAt)}</dd>
            </div>
          </dl>

          <section className="mt-10">
            <h2 className="text-lg font-semibold">Aliases</h2>
            <div className="mt-4">
              {company.data.aliases.length === 0 ? (
                <p className="text-sm text-subtle">Nenhum alias registrado.</p>
              ) : (
                <ul className="flex flex-wrap gap-2">
                  {company.data.aliases.map((alias) => (
                    <li
                      className="rounded-full border border-line-strong bg-surface px-4 py-2 text-sm"
                      key={alias}
                    >
                      {alias}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section className="mt-10">
            <h2 className="text-lg font-semibold">Fontes</h2>
            <button
              className="mt-3 rounded-xl border border-ink px-4 py-2 text-sm font-medium hover:bg-info-surface disabled:opacity-50"
              disabled={detectSource.isPending}
              onClick={() => detectSource.mutate()}
              type="button"
            >
              {detectSource.isPending ? 'Detectando…' : 'Detectar fonte'}
            </button>
            {detectSource.data && (
              <p className="mt-3 text-sm text-subtle" role="status">
                {detectSource.data.result === 'not_detected'
                  ? 'Nenhum ATS detectável foi encontrado.'
                  : detectSource.data.result === 'already_proposed'
                    ? 'A proposta já existe e continua desabilitada.'
                    : 'Proposta criada e desabilitada; aguarda revisão e homologação.'}
                {detectSource.data.evidence ? ` Evidência: ${detectSource.data.evidence}` : ''}
              </p>
            )}
            {detectSource.isError && <p className="mt-3 text-sm text-danger-ink">Não foi possível detectar a fonte.</p>}
            <div className="mt-4">
              <Sources company={company.data} />
            </div>
          </section>

          <section className="mt-10">
            <h2 className="text-lg font-semibold">Últimas vagas</h2>
            <div className="mt-4">
              <LatestOpportunities companyId={company.data.id} />
            </div>
          </section>
        </>
      )}
    </PageShell>
  )
}
