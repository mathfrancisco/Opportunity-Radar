import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { CompanyForm } from '../components/CompanyForm'
import { CompanySourceForm } from '../components/CompanySourceForm'
import { PageShell } from '../components/PageShell'
import { EmptyState, ErrorState, LoadingState } from '../components/states'
import { type CompanyDetail, type CompanyDetailSource } from '../features/companies/api'
import {
  useCompany,
  useDetectCompanySource,
  useUpdateCompany,
} from '../features/companies/useCompanies'
import { useInbox } from '../features/dashboard/useInbox'

function formatDate(value: string | null) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString('pt-BR')
}

const fieldLabels: Record<string, string> = {
  source_type: 'ATS',
  endpoint: 'endereço',
  external_key: 'chave',
}

function describeChange(change: { from: unknown; to: unknown }) {
  const shown = (value: unknown) => (value === null || value === undefined ? '—' : String(value))
  return change.from === null ? shown(change.to) : `${shown(change.from)} → ${shown(change.to)}`
}

/** Every registration and correction of one ATS record, oldest first, with its reason. */
function Revisions({ source }: { source: CompanyDetailSource }) {
  if (source.revisions.length === 0) return null
  return (
    <details className="mt-3">
      <summary className="cursor-pointer text-xs font-medium text-subtle">
        Histórico ({source.revisions.length})
      </summary>
      <ol className="mt-2 grid gap-2">
        {source.revisions.map((revision) => (
          <li className="rounded-xl bg-panel p-3 text-xs" key={revision.version}>
            <p className="text-muted">
              Versão {revision.version} · {formatDate(revision.changedAt)}
            </p>
            <p className="mt-1">
              {Object.entries(revision.changes)
                .map(([field, change]) => `${fieldLabels[field] ?? field}: ${describeChange(change)}`)
                .join(' · ')}
            </p>
            <p className="mt-1 text-subtle">{revision.evidenceNote}</p>
          </li>
        ))}
      </ol>
    </details>
  )
}

function Sources({
  company,
  onCorrect,
}: {
  company: CompanyDetail
  onCorrect: (source: CompanyDetailSource) => void
}) {
  if (company.sources.length === 0) {
    return (
      <EmptyState>Nenhuma fonte associada. A pesquisa registrou a empresa, mas nenhum endpoint foi
        confirmado.</EmptyState>
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
          <Revisions source={source} />
          <Button className="mt-3" onClick={() => onCorrect(source)} size="sm" variant="secondary">
            Corrigir
          </Button>
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
      <ErrorState onRetry={() => void inbox.refetch()}>Não foi possível carregar as vagas desta empresa.</ErrorState>
    )
  }
  if (!inbox.data || inbox.data.items.length === 0) {
    return (
      <EmptyState>Nenhuma vaga coletada desta empresa até agora.</EmptyState>
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
  const update = useUpdateCompany(companyId)
  const [editing, setEditing] = useState(false)
  // 'new' registers an ATS record; a source corrects that one.
  const [sourceForm, setSourceForm] = useState<CompanyDetailSource | 'new' | null>(null)
  const [savedSource, setSavedSource] = useState(false)

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

      <div>
        {company.isPending && (
          <LoadingState className="mt-8">Carregando empresa…</LoadingState>
        )}
        {company.isError && (
          <ErrorState className="mt-8" onRetry={() => void company.refetch()}>{company.error.message}</ErrorState>
        )}
      </div>

      {company.data && editing && (
        <div className="mt-8">
          <CompanyForm
            company={company.data}
            error={update.error}
            onCancel={() => {
              update.reset()
              setEditing(false)
            }}
            onReload={() => {
              update.reset()
              void company.refetch()
            }}
            onSubmit={(input) =>
              update.mutate(
                { ...input, expectedVersion: company.data.version },
                { onSuccess: () => setEditing(false) },
              )
            }
            pending={update.isPending}
          />
        </div>
      )}

      {company.data && (
        <>
          {!editing && (
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Button onClick={() => setEditing(true)} size="sm" variant="secondary">
                Editar empresa
              </Button>
              {update.isSuccess && (
                <p className="text-sm text-success-ink" role="status">
                  Empresa salva, versão {update.data.version}.
                </p>
              )}
            </div>
          )}
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

          <section className="mt-section">
            <h2 className="text-section">Aliases</h2>
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

          <section className="mt-section">
            <h2 className="text-section">Fontes</h2>
            <p className="mt-1 max-w-2xl text-sm text-muted">
              Registre ou corrija o ATS da empresa e proponha a fonte a partir dele. A proposta
              nasce desabilitada e é homologada na tela de fontes.
            </p>
            <div className="mt-3 flex flex-wrap gap-3">
              <Button
                disabled={detectSource.isPending}
                onClick={() => {
                  setSavedSource(false)
                  detectSource.mutate()
                }}
                variant="secondary"
              >
                {detectSource.isPending ? 'Propondo…' : 'Propor fonte a partir do ATS'}
              </Button>
              {sourceForm === null && (
                <Button
                  onClick={() => {
                    setSavedSource(false)
                    setSourceForm('new')
                  }}
                  variant="secondary"
                >
                  Registrar ATS
                </Button>
              )}
            </div>
            {detectSource.data && (
              <p className="mt-3 text-sm text-subtle" role="status">
                {detectSource.data.result === 'not_detected'
                  ? 'Nenhum ATS com chave registrada: registre o ATS da empresa e tente de novo.'
                  : detectSource.data.result === 'already_proposed'
                    ? 'A proposta já existe e não foi duplicada; ela continua desabilitada.'
                    : 'Proposta criada e desabilitada; aguarda homologação.'}
                {detectSource.data.evidence ? ` Evidência: ${detectSource.data.evidence}` : ''}
                {detectSource.data.sourceId && (
                  <>
                    {' '}
                    <Link
                      className="font-medium text-ink underline decoration-accent decoration-2 underline-offset-4"
                      to="/sources"
                    >
                      Ir para a homologação
                    </Link>
                  </>
                )}
              </p>
            )}
            {detectSource.isError && (
              <ErrorState className="mt-3">{detectSource.error.message}</ErrorState>
            )}
            {savedSource && sourceForm === null && (
              <p className="mt-3 text-sm text-success-ink" role="status">
                Registro salvo. Proponha a fonte para levá-lo à homologação.
              </p>
            )}
            {sourceForm !== null && (
              <div className="mt-4">
                <CompanySourceForm
                  companyId={companyId}
                  key={sourceForm === 'new' ? 'new' : sourceForm.id}
                  onCancel={() => setSourceForm(null)}
                  onReload={() => {
                    void company.refetch().then((fresh) => {
                      if (sourceForm === 'new') return
                      const latest = fresh.data?.sources.find((item) => item.id === sourceForm.id)
                      if (latest) setSourceForm(latest)
                    })
                  }}
                  onSaved={() => {
                    setSourceForm(null)
                    setSavedSource(true)
                  }}
                  source={sourceForm === 'new' ? null : sourceForm}
                />
              </div>
            )}
            <div className="mt-4">
              <Sources
                company={company.data}
                onCorrect={(source) => {
                  setSavedSource(false)
                  setSourceForm(source)
                }}
              />
            </div>
          </section>

          <section className="mt-section">
            <h2 className="text-section">Últimas vagas</h2>
            <div className="mt-4">
              <LatestOpportunities companyId={company.data.id} />
            </div>
          </section>
        </>
      )}
    </PageShell>
  )
}
