import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Chip } from '../components/Chip'
import { CompanyForm } from '../components/CompanyForm'
import { CompanySourceForm } from '../components/CompanySourceForm'
import { DataTable } from '../components/DataTable'
import { PageShell } from '../components/PageShell'
import { VerdictBadge } from '../components/VerdictBadge'
import { PanelSkeleton, TableSkeleton } from '../components/skeletons'
import { EmptyState, ErrorState } from '../components/states'
import {
  type CompanyDetail,
  type CompanyDetailSource,
  type ProposalOutcome,
} from '../features/companies/api'
import {
  useCompany,
  useDetectCompanySource,
  useReopenHomologation,
  useUpdateCompany,
} from '../features/companies/useCompanies'
import { companyLabel, companyStatusLabels, priorityLabels, verificationLabels } from '../features/companies/labels'
import { opportunityLabel, workModeLabels } from '../features/opportunities/labels'
import { ConflictError } from '../lib/api'
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

const sensitiveConfigKey = /secret|token|password|credential|authorization|api.?key|email/i

function configSummary(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  if (Array.isArray(value)) {
    const simple = value.filter((item) => ['string', 'number', 'boolean'].includes(typeof item))
    return simple.length === value.length
      ? simple.slice(0, 3).map(String).join(', ') + (value.length > 3 ? ` e mais ${value.length - 3}` : '')
      : `Lista com ${value.length} itens`
  }
  if (typeof value === 'object') {
    const visible = Object.entries(value as Record<string, unknown>)
      .filter(([key]) => !sensitiveConfigKey.test(key))
      .slice(0, 3)
      .map(([key, item]) => `${key}: ${typeof item === 'object' ? 'valor estruturado' : String(item)}`)
    return visible.length ? visible.join('; ') : 'Detalhes indisponíveis'
  }
  return 'Detalhes indisponíveis'
}

function describeChange(change: { from: unknown; to: unknown }) {
  return change.from === null
    ? configSummary(change.to)
    : `${configSummary(change.from)} → ${configSummary(change.to)}`
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
          <li className="rounded-control bg-panel p-3 text-xs" key={revision.version}>
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

/**
 * The source proposed from this record, next to the record itself. When the record was
 * corrected after a proposal that had already been reviewed, tested or enabled, the two
 * disagree, and bringing the proposal along is an explicit reopening of its gate.
 */
function Proposal({ companyId, source }: { companyId: string; source: CompanyDetailSource }) {
  const reopen = useReopenHomologation(companyId)
  const proposal = source.proposal
  if (!proposal) return null
  const state = proposal.enabled ? 'habilitada' : 'desabilitada'
  return (
    <div
      className={`mt-3 rounded-control p-3 text-xs ${proposal.outdated ? 'border border-warning-line bg-warning-surface text-warning-ink' : 'bg-panel text-subtle'}`}
    >
      <p>Fonte proposta: {state}.</p>
      <details className="mt-2">
        <summary className="cursor-pointer font-medium">Detalhe técnico</summary>
        <p className="mt-1">
          Chave {proposal.externalKey ?? '—'} · evidência {proposal.evidenceStatus} · versão{' '}
          {proposal.version}
        </p>
      </details>
      {proposal.outdated && (
        <>
          <p className="mt-2">
            O registro foi corrigido para a chave {source.externalKey ?? '—'}, mas a fonte
            proposta já tinha homologação ou teste sobre a chave antiga e não mudou. Reabrir a
            homologação troca a chave e zera evidência, termos, teste e data de revisão
            {proposal.enabled ? ' — e desabilita a fonte, que para de coletar' : ''}.
          </p>
          <Button
            className="mt-2"
            disabled={reopen.isPending}
            onClick={() =>
              reopen.mutate({ sourceId: proposal.sourceId, expectedVersion: proposal.version })
            }
            size="sm"
            variant="secondary"
          >
            {reopen.isPending ? 'Reabrindo…' : 'Reabrir a homologação da fonte proposta'}
          </Button>
          {reopen.isError && (
            <p className="mt-2 text-danger-ink" role="alert">
              {reopen.error instanceof ConflictError
                ? 'A fonte proposta mudou depois que a página carregou. Ela foi recarregada; confira e tente de novo.'
                : reopen.error.message}
            </p>
          )}
        </>
      )}
    </div>
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
        confirmado. Registre o ATS acima para propor uma.</EmptyState>
    )
  }
  return (
    <ul className="grid gap-3">
      {company.sources.map((source) => (
        <Card as="li" className="text-sm" key={source.id}>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-semibold">{source.name}</span>
            <span className="text-muted">{companyLabel(source.status, verificationLabels)}</span>
          </div>
          {source.url && <p className="mt-1 break-all text-subtle">{source.url}</p>}
          <p className="mt-2 text-xs text-muted">
            Última verificação em {formatDate(source.lastVerifiedAt)}.
          </p>
          <details className="mt-2">
            <summary className="cursor-pointer text-xs font-medium text-subtle">Detalhe técnico</summary>
            <p className="mt-1 text-xs text-muted">
              Status: {source.status} · método: {source.verificationMethod ?? 'não informado'}
              {source.externalKey ? ` · chave ${source.externalKey}` : ''}
            </p>
          </details>
          {source.evidence && (
            <p className="mt-2 text-subtle">{source.evidence}</p>
          )}
          <Proposal companyId={company.id} source={source} />
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
    return <TableSkeleton columns={4} label="Carregando vagas…" rows={3} />
  }
  if (inbox.isError) {
    // Partial state: the company is on screen, only its vagas are missing.
    return (
      <div className="flex flex-wrap items-center gap-3 text-sm text-subtle" role="status">
        <p>Não foi possível carregar as vagas agora. O resto desta empresa continua valendo.</p>
        <Button onClick={() => void inbox.refetch()} size="sm" variant="secondary">
          Tentar novamente
        </Button>
      </div>
    )
  }
  if (!inbox.data || inbox.data.items.length === 0) {
    return (
      <EmptyState>Nenhuma vaga desta empresa até agora. Quando uma fonte habilitada coletar, ela aparece aqui.</EmptyState>
    )
  }
  return (
    <>
      <DataTable
        caption="Últimas vagas desta empresa"
        columns={['Vaga', 'Modalidade', 'Decisão', 'Score']}
      >
        {inbox.data.items.map((item) => (
          <tr key={item.opportunityId}>
            <td>
              <Link
                className="font-medium underline decoration-accent decoration-2 underline-offset-4"
                to={`/opportunities/${item.opportunityId}`}
              >
                {item.title}
              </Link>
            </td>
            <td className="text-subtle">{opportunityLabel(item.workMode, workModeLabels)}</td>
            <td>
              <VerdictBadge verdict={item.verdict} />
            </td>
            <td className="text-subtle">{item.score ? Number(item.score).toFixed(1) : '—'}</td>
          </tr>
        ))}
      </DataTable>
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
  const [savedSource, setSavedSource] = useState<ProposalOutcome | null>(null)

  return (
    <PageShell
      actions={
        company.data && !editing ? (
          <Button onClick={() => setEditing(true)} variant="secondary">
            Editar empresa
          </Button>
        ) : undefined
      }
      eyebrow="Catálogo local"
      title={company.data?.name ?? 'Empresa'}
      description={company.data?.domain ?? 'Prioridade, fontes e vagas desta empresa.'}
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
          <div className="mt-8">
            <PanelSkeleton columns={4} label="Carregando empresa…" />
          </div>
        )}
        {company.isError && (
          <ErrorState className="mt-8" onRetry={() => void company.refetch()}>
            Não foi possível carregar a empresa agora. Nada foi alterado e as outras empresas continuam disponíveis.
          </ErrorState>
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
              {update.isSuccess && (
                <p className="text-sm text-success-ink" role="status">
                  Empresa salva, versão {update.data.version}.
                </p>
              )}
            </div>
          )}
          {!editing && (
            <nav aria-label="Navegar nesta empresa" className="mt-6 flex flex-wrap gap-x-4 gap-y-2 text-sm">
              <a className="underline decoration-accent decoration-2 underline-offset-4" href="#resumo">Resumo</a>
              <a className="underline decoration-accent decoration-2 underline-offset-4" href="#fontes">Fontes</a>
              <a className="underline decoration-accent decoration-2 underline-offset-4" href="#vagas">Vagas</a>
            </nav>
          )}
          <div className="mt-6 scroll-mt-6" id="resumo">
          <Card>
          <dl className="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-muted">Prioridade</dt>
              <dd className="mt-1 break-words font-medium">{companyLabel(company.data.priority, priorityLabels)}</dd>
            </div>
            <div>
              <dt className="text-muted">Status no radar</dt>
              <dd className="mt-1 break-words font-medium">{companyLabel(company.data.status, companyStatusLabels)}</dd>
            </div>
            <div>
              <dt className="text-muted">Verificação</dt>
              <dd className="mt-1 break-words font-medium">{companyLabel(company.data.verificationState, verificationLabels)}</dd>
            </div>
            <div>
              <dt className="text-muted">Última verificação</dt>
              <dd className="mt-1 font-medium">{formatDate(company.data.lastVerifiedAt)}</dd>
            </div>
          </dl>
          </Card>
          </div>

          <section className="mt-10">
            <h2 className="text-section">Aliases</h2>
            <div className="mt-4">
              {company.data.aliases.length === 0 ? (
                <p className="text-sm text-subtle">Nenhum alias registrado.</p>
              ) : (
                <ul className="flex flex-wrap gap-2">
                  {company.data.aliases.map((alias) => (
                    <li key={alias}>
                      <Chip className="text-body-sm">{alias}</Chip>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section className="mt-10 scroll-mt-6" id="fontes">
            <h2 className="text-section">Fontes</h2>
            <p className="mt-1 max-w-2xl text-sm text-muted">
              Registre ou corrija o ATS da empresa e proponha a fonte a partir dele. A proposta
              nasce desabilitada e é homologada na tela de fontes.
            </p>
            <div className="mt-3 flex flex-wrap gap-3">
              <Button
                disabled={detectSource.isPending}
                onClick={() => {
                  setSavedSource(null)
                  detectSource.mutate()
                }}
                variant="secondary"
              >
                {detectSource.isPending ? 'Propondo…' : 'Propor fonte a partir do ATS'}
              </Button>
              {sourceForm === null && (
                <Button
                  onClick={() => {
                    setSavedSource(null)
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
            {savedSource !== null && sourceForm === null && (
              <p className="mt-3 text-sm text-success-ink" role="status">
                {savedSource === 'updated'
                  ? 'Registro corrigido, e a fonte proposta a partir dele passou a ler a chave nova.'
                  : savedSource === 'outdated'
                    ? 'Registro corrigido. A fonte proposta já tinha homologação ou teste e não mudou; veja abaixo como trazê-la junto.'
                    : 'Registro salvo. Proponha a fonte para levá-lo à homologação.'}
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
                  onSaved={(outcome) => {
                    setSourceForm(null)
                    setSavedSource(outcome)
                  }}
                  source={sourceForm === 'new' ? null : sourceForm}
                />
              </div>
            )}
            <div className="mt-4">
              <Sources
                company={company.data}
                onCorrect={(source) => {
                  setSavedSource(null)
                  setSourceForm(source)
                }}
              />
            </div>
          </section>

          <section className="mt-10 scroll-mt-6" id="vagas">
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
