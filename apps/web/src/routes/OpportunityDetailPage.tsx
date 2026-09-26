import { type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApplicationPanel } from '../components/ApplicationPanel'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { DataTable } from '../components/DataTable'
import { PageShell } from '../components/PageShell'
import { EmptyState, ErrorState, LoadingState } from '../components/states'
import { AnalysisPanel } from '../features/matching/AnalysisPanel'
import {
  type EligibilityDetail,
  type MatchAssessment,
  type MatchFactor,
} from '../features/matching/api'
import {
  useAnalyzeAssessment,
  useEvaluateOpportunity,
  useLatestAssessment,
} from '../features/matching/useAssessment'
import { type DuplicateCandidate, type OpportunityDetail } from '../features/opportunities/api'
import { verdictLabels } from '../features/matching/verdicts'
import {
  useConfirmDuplicate,
  useDuplicateCandidates,
  useMarkRelevance,
  useOpportunity,
  useRejectDuplicate,
} from '../features/opportunities/useOpportunity'

/** Single-operator MVP (SPEC 43): no login, so duplicate decisions are attributed to a
 * fixed operator identity rather than a per-user one. */
const DUPLICATE_DECIDED_BY = 'web-operator'

const resultLabels: Record<string, string> = {
  TRUE: 'Atende',
  FALSE: 'Não atende',
  UNKNOWN: 'Desconhecido',
}

function display(value: string | null) {
  return value === null || value === '' ? '—' : value
}

function formatDate(value: string | null) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString('pt-BR')
}

function formatNumber(value: string | null, digits = 1) {
  if (value === null) return '—'
  const parsed = Number(value)
  return Number.isNaN(parsed) ? value : parsed.toFixed(digits)
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-section">
      <h2 className="text-section">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  )
}

function Facts({ opportunity }: { opportunity: OpportunityDetail }) {
  return (
    <dl className="mt-8 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
      <div>
        <dt className="text-muted">Empresa</dt>
        <dd className="mt-1 font-medium">{display(opportunity.companyName)}</dd>
      </div>
      <div>
        <dt className="text-muted">Localização</dt>
        <dd className="mt-1 font-medium">{display(opportunity.location)}</dd>
      </div>
      <div>
        <dt className="text-muted">Modalidade</dt>
        <dd className="mt-1 font-medium">{opportunity.workMode}</dd>
      </div>
      <div>
        <dt className="text-muted">Senioridade</dt>
        <dd className="mt-1 font-medium">{opportunity.seniority}</dd>
      </div>
      <div>
        <dt className="text-muted">Contrato</dt>
        <dd className="mt-1 font-medium">{opportunity.contractType}</dd>
      </div>
      <div>
        <dt className="text-muted">Status</dt>
        <dd className="mt-1 font-medium">{opportunity.lifecycleStatus}</dd>
      </div>
      <div>
        <dt className="text-muted">Publicada</dt>
        <dd className="mt-1 font-medium">{formatDate(opportunity.publishedAt)}</dd>
      </div>
      <div>
        <dt className="text-muted">Versão do conteúdo</dt>
        <dd className="mt-1 font-medium">{opportunity.version}</dd>
      </div>
    </dl>
  )
}

function Compensation({ opportunity }: { opportunity: OpportunityDetail }) {
  if (opportunity.compensations.length === 0) {
    return (
      <EmptyState>Nenhuma remuneração declarada nas fontes. Ausência de dado não vira zero nem
        penalidade.</EmptyState>
    )
  }
  return (
    <ul className="grid gap-3">
      {opportunity.compensations.map((item, index) => (
        <Card as="li" className="text-sm" key={`${item.rawItemId}-${index}`}>
          <p className="font-semibold">
            {display(item.minimum)} – {display(item.maximum)} {display(item.currency)}{' '}
            <span className="font-normal text-muted">
              ({item.period}, {item.grossNet})
            </span>
          </p>
          {item.evidenceText && (
            <p className="mt-2 text-subtle">“{item.evidenceText}”</p>
          )}
          <p className="mt-2 text-xs text-muted">
            Evidência: {display(item.evidenceSource)} · raw item {item.rawItemId}
          </p>
        </Card>
      ))}
    </ul>
  )
}

function Skills({ opportunity }: { opportunity: OpportunityDetail }) {
  if (opportunity.skills.length === 0) {
    return <p className="text-subtle">Nenhuma skill extraída.</p>
  }
  return (
    <ul className="flex flex-wrap gap-2">
      {opportunity.skills.map((skill) => (
        <li
          className="rounded-full border border-line-strong bg-surface px-4 py-2 text-sm"
          key={skill.canonicalName}
        >
          <span className="font-medium">{skill.displayName}</span>{' '}
          <span className="text-muted">
            {skill.requirement.toLowerCase()} · {skill.taxonomyVersion}
          </span>
        </li>
      ))}
    </ul>
  )
}

function Provenance({ opportunity }: { opportunity: OpportunityDetail }) {
  return (
    <>
      <ul className="grid gap-3">
        {opportunity.occurrences.map((occurrence) => (
          <Card as="li" className="text-sm" key={occurrence.id}>
            <p className="font-medium">
              {occurrence.sourceUrl ? (
                <a
                  className="break-anywhere underline decoration-accent decoration-2 underline-offset-4"
                  href={occurrence.sourceUrl}
                  rel="noreferrer"
                  target="_blank"
                >
                  {occurrence.sourceUrl}
                </a>
              ) : (
                `Ocorrência ${occurrence.externalId ?? occurrence.id}`
              )}
            </p>
            <p className="mt-2 text-muted">
              Primeira vez {formatDate(occurrence.firstSeenAt)} · última{' '}
              {formatDate(occurrence.lastSeenAt)}
            </p>
            <p className="break-anywhere mt-1 text-xs text-muted">
              raw item {occurrence.rawItemId}
            </p>
            {!occurrence.payloadRetained && (
              <p className="mt-2 rounded-xl border border-warning-line bg-warning-surface px-3 py-2 text-xs text-warning-ink">
                Conteúdo bruto expirado pela retenção
                {occurrence.payloadExpiredAt
                  ? ` em ${formatDate(occurrence.payloadExpiredAt)}`
                  : ''}
                . A procedência permanece; o reprocessamento não está mais disponível.
              </p>
            )}
          </Card>
        ))}
      </ul>
      <p className="break-anywhere mt-4 text-sm text-muted">
        Fingerprint {opportunity.fingerprint} ({opportunity.fingerprintVersion}) ·{' '}
        {opportunity.normalizationResults.length} resultado
        {opportunity.normalizationResults.length === 1 ? '' : 's'} de normalização.
      </p>
    </>
  )
}

const RELEVANCE_REASONS = [
  { value: 'AREA', label: 'Área' },
  { value: 'SENIORITY', label: 'Senioridade' },
  { value: 'LOCATION', label: 'Localização' },
  { value: 'COMPANY', label: 'Empresa' },
  { value: 'COMPENSATION', label: 'Remuneração' },
  { value: 'OTHER', label: 'Outro' },
]

/** The relevance mark is operator evaluation data (F17-01): it never feeds the score. */
function RelevanceMark({ opportunity }: { opportunity: OpportunityDetail }) {
  const mark = useMarkRelevance(opportunity.id)
  const current = opportunity.relevanceMark

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          disabled={mark.isPending}
          onClick={() => mark.mutate({ relevant: true })}
        >
          Relevante
        </Button>
        <select
          aria-label="Motivo de não ser para mim"
          className="rounded-xl border border-line-strong bg-surface px-3 py-2 text-sm"
          disabled={mark.isPending}
          onChange={(event) => {
            const reason = event.target.value
            mark.mutate({ relevant: false, reason: reason === '' ? null : reason })
            event.target.value = ''
          }}
          value=""
        >
          <option value="">Não é para mim…</option>
          {RELEVANCE_REASONS.map((reason) => (
            <option key={reason.value} value={reason.value}>
              {reason.label}
            </option>
          ))}
        </select>
        {current && (
          <span className="text-sm text-muted">
            Marcada como {current.relevant ? 'relevante' : 'não relevante'}
            {current.reason ? ` (${current.reason.toLowerCase()})` : ''} em{' '}
            {formatDate(current.markedAt)}.
          </span>
        )}
      </div>
      {mark.isError && (
        <p className="mt-2 text-sm text-danger-ink">Não foi possível registrar a marca.</p>
      )}
    </div>
  )
}

const DUPLICATE_COMPARISON_FIELDS: {
  label: string
  read: (opportunity: OpportunityDetail) => string
}[] = [
  { label: 'Título', read: (o) => o.title },
  { label: 'Empresa', read: (o) => display(o.companyName) },
  { label: 'Localização', read: (o) => display(o.location) },
  { label: 'Modalidade', read: (o) => o.workMode },
  { label: 'Senioridade', read: (o) => o.seniority },
  { label: 'Contrato', read: (o) => o.contractType },
  { label: 'Publicada', read: (o) => formatDate(o.publishedAt) },
]

/** One `PENDING` candidate, the two opportunities side by side with differences
 * highlighted, and the confirm/reject actions (F20-26 "Escopo"). Fetches the other side
 * of the pair itself so `OpportunityDetailPage` only has to know the candidate row. */
function DuplicateCandidateCard({
  candidate,
  opportunity,
}: {
  candidate: DuplicateCandidate
  opportunity: OpportunityDetail
}) {
  const otherId =
    candidate.opportunityId === opportunity.id
      ? candidate.duplicateOpportunityId
      : candidate.opportunityId
  const other = useOpportunity(otherId)
  const confirm = useConfirmDuplicate(opportunity.id, otherId)
  const reject = useRejectDuplicate(opportunity.id, otherId)
  const busy = confirm.isPending || reject.isPending

  if (other.isPending) return <LoadingState>Carregando a outra vaga do par…</LoadingState>
  if (other.isError || !other.data) {
    return <ErrorState onRetry={() => void other.refetch()}>Não foi possível carregar a outra vaga.</ErrorState>
  }

  const otherOpportunity = other.data
  // `confirm_duplicate` always keeps the older `created_at` as the survivor — shown here
  // so the operator sees which side "É a mesma vaga" would keep before confirming.
  const survivorIsCurrent = opportunity.createdAt <= otherOpportunity.createdAt
  const survivor = survivorIsCurrent ? opportunity : otherOpportunity
  const absorbed = survivorIsCurrent ? otherOpportunity : opportunity

  return (
    <Card as="article" className="text-sm">
      <p className="text-xs text-muted">
        Regra: {candidate.rule}
        {candidate.score !== null ? ` · score ${candidate.score}` : ''}
      </p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {[opportunity, otherOpportunity].map((side) => (
          <div className="rounded-2xl border border-line bg-surface p-4" key={side.id}>
            <p className="font-semibold">
              {side.id === survivor.id ? (
                <Link
                  className="underline decoration-accent decoration-2 underline-offset-4"
                  to={`/opportunities/${side.id}`}
                >
                  {side.title}
                </Link>
              ) : (
                <Link to={`/opportunities/${side.id}`}>{side.title}</Link>
              )}
            </p>
            <p className="mt-1 text-xs font-medium text-muted">
              {side.id === survivor.id ? 'Ficaria como sobrevivente' : 'Seria absorvida'}
            </p>
            <dl className="mt-3 grid gap-2">
              {DUPLICATE_COMPARISON_FIELDS.map((field) => {
                const value = field.read(side)
                const differs = field.read(opportunity) !== field.read(otherOpportunity)
                return (
                  <div key={field.label}>
                    <dt className="text-muted">{field.label}</dt>
                    <dd
                      className={
                        differs
                          ? 'mt-0.5 rounded bg-warning-surface px-1 font-medium text-warning-ink'
                          : 'mt-0.5 font-medium'
                      }
                    >
                      {value}
                    </dd>
                  </div>
                )
              })}
            </dl>
          </div>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          disabled={busy}
          onClick={() =>
            confirm.mutate({
              candidateId: candidate.id,
              expectedVersionSurvivor: survivor.version,
              expectedVersionAbsorbed: absorbed.version,
              decidedBy: DUPLICATE_DECIDED_BY,
            })
          }
        >
          É a mesma vaga
        </Button>
        <Button
          disabled={busy}
          onClick={() =>
            reject.mutate({ candidateId: candidate.id, decidedBy: DUPLICATE_DECIDED_BY })
          }
          variant="secondary"
        >
          São vagas diferentes
        </Button>
      </div>
      {(confirm.isError || reject.isError) && (
        <p className="mt-2 text-sm text-danger-ink">
          {(confirm.error ?? reject.error)?.message ?? 'Não foi possível registrar a decisão.'}
        </p>
      )}
    </Card>
  )
}

/** Section "Possível duplicata": every `PENDING` candidate naming this opportunity, each
 * with its own side-by-side comparison and confirm/reject actions. */
export function DuplicateCandidates({ opportunity }: { opportunity: OpportunityDetail }) {
  const candidates = useDuplicateCandidates(opportunity.id)

  if (candidates.isPending) return <LoadingState>Carregando candidatos a duplicata…</LoadingState>
  if (candidates.isError) {
    return (
      <ErrorState onRetry={() => void candidates.refetch()}>
        Não foi possível carregar os candidatos a duplicata.
      </ErrorState>
    )
  }
  const pending = candidates.data.filter((candidate) => candidate.status === 'PENDING')
  if (pending.length === 0) {
    return <EmptyState>Nenhum candidato a duplicata pendente para esta oportunidade.</EmptyState>
  }
  return (
    <div className="grid gap-4">
      {pending.map((candidate) => (
        <DuplicateCandidateCard
          candidate={candidate}
          key={candidate.id}
          opportunity={opportunity}
        />
      ))}
    </div>
  )
}

function Eligibility({ details }: { details: EligibilityDetail[] }) {
  if (details.length === 0) return <p className="text-subtle">Nenhum filtro avaliado.</p>
  return (
    <ul className="grid gap-2">
      {details.map((detail) => (
        <li
          className="rounded-2xl border border-line bg-surface p-4 text-sm"
          key={detail.code}
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-medium">{detail.code}</span>
            <span
              className={
                detail.result === 'FALSE'
                  ? 'text-danger-ink'
                  : detail.result === 'UNKNOWN'
                    ? 'text-warning-ink'
                    : 'text-success-ink'
              }
            >
              {resultLabels[detail.result] ?? detail.result}
            </span>
          </div>
          <p className="mt-1 text-subtle">{detail.reason}</p>
        </li>
      ))}
    </ul>
  )
}

function Factors({ factors }: { factors: MatchFactor[] }) {
  if (factors.length === 0) return <p className="text-subtle">Nenhum fator calculado.</p>
  return (
    <DataTable
      caption="Fatores que compõem o score desta avaliação"
      columns={['Fator', 'Peso', 'Contribuição', 'Estado', 'Explicação']}
      stickyFirstColumn
    >
      {factors.map((factor) => (
            <tr className="border-t border-divider" key={factor.factorCode}>
              <td className="px-4 py-3 font-medium">{factor.factorCode}</td>
              <td className="px-4 py-3">{formatNumber(factor.weight, 2)}</td>
              <td className="px-4 py-3">{formatNumber(factor.contribution, 2)}</td>
              <td className="px-4 py-3">
                {factor.status}
                {factor.status === 'UNKNOWN' && (
                  <span className="block text-xs text-muted">
                    {factor.missingPolicy}
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-subtle">{factor.explanation}</td>
            </tr>
      ))}
    </DataTable>
  )
}

function Decision({
  assessment,
  opportunityId,
}: {
  assessment: MatchAssessment
  opportunityId: string
}) {
  const analyze = useAnalyzeAssessment(opportunityId)
  return (
    <>
      <div className="flex flex-wrap items-baseline gap-4">
        <span className="text-metric-lg">
          {formatNumber(assessment.score)}
        </span>
        <span className="rounded-full border border-line-strong bg-surface px-4 py-2 text-sm font-medium">
          {verdictLabels[assessment.verdict] ?? assessment.verdict}
        </span>
        <span className="text-sm text-muted">
          Elegibilidade {assessment.eligibility} · confiança{' '}
          {formatNumber(assessment.confidence, 2)}
        </span>
      </div>
      {assessment.isStale && (
        <p className="mt-3 rounded-xl border border-warning-line bg-warning-surface p-3 text-sm text-warning-ink" role="status">
          Esta decisão foi calculada com dados anteriores. Uma reavaliação está pendente;
          os detalhes abaixo permanecem disponíveis como histórico.
        </p>
      )}
      <p className="mt-2 text-xs text-muted">
        Regras {assessment.rulesVersion} · taxonomia {assessment.taxonomyVersion} · perfil{' '}
        {assessment.profileVersionId.slice(0, 8)} · avaliada em{' '}
        {formatDate(assessment.assessedAt)} · hash {assessment.inputHash.slice(0, 12)}…
      </p>

      <Section title="Filtros eliminatórios">
        <Eligibility details={assessment.eligibilityDetails} />
      </Section>

      <Section title="Fatores do score">
        <Factors factors={assessment.factors} />
      </Section>

      <Section title="Análise semântica">
        <AnalysisPanel
          analysis={assessment.analysis}
          assessment={assessment}
          failed={analyze.isError}
          onRun={(refresh) =>
            analyze.mutate({ assessmentId: assessment.id, refresh })
          }
          running={analyze.isPending}
        />
      </Section>
    </>
  )
}

export function OpportunityDetailPage() {
  const { opportunityId = '' } = useParams()
  const opportunity = useOpportunity(opportunityId)
  const assessment = useLatestAssessment(opportunityId)
  const evaluate = useEvaluateOpportunity(opportunityId)

  return (
    <PageShell
      eyebrow="Oportunidade"
      title={opportunity.data?.title ?? 'Detalhe da oportunidade'}
      description={
        opportunity.data
          ? undefined
          : 'Carregando os dados preservados desta oportunidade.'
      }
    >
      <p className="mt-2">
        <Link
          className="text-sm text-subtle underline decoration-accent decoration-2 underline-offset-4"
          to="/inbox"
        >
          ← Voltar para as oportunidades
        </Link>
      </p>

      <div>
        {opportunity.isPending && (
          <LoadingState className="mt-8">Carregando oportunidade…</LoadingState>
        )}
        {opportunity.isError && (
          <ErrorState className="mt-8" onRetry={() => void opportunity.refetch()}>{opportunity.error.message}</ErrorState>
        )}

        {opportunity.data && (
          <>
            <Facts opportunity={opportunity.data} />

            <Section title="Relevância">
              <RelevanceMark opportunity={opportunity.data} />
            </Section>

            <Section title="Possível duplicata">
              <DuplicateCandidates opportunity={opportunity.data} />
            </Section>

            {opportunity.data.description && (
              <Section title="Descrição">
                <p className="whitespace-pre-line text-body text-subtle">
                  {opportunity.data.description}
                </p>
              </Section>
            )}

            <Section title="Remuneração">
              <Compensation opportunity={opportunity.data} />
            </Section>

            <Section title="Skills">
              <Skills opportunity={opportunity.data} />
            </Section>

            <Section title="Procedência">
              <Provenance opportunity={opportunity.data} />
            </Section>

            <Section title="Decisão">
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <Button
                  disabled={evaluate.isPending}
                  onClick={() => evaluate.mutate()}
                >
                  {evaluate.isPending ? 'Avaliando…' : 'Avaliar agora'}
                </Button>
                {evaluate.isSuccess && <span className="text-sm text-subtle">Avaliação atualizada.</span>}
                {evaluate.isError && <span className="text-sm text-danger-ink">Não foi possível avaliar agora.</span>}
              </div>
              {assessment.isPending && (
                <LoadingState>Carregando a avaliação…</LoadingState>
              )}
              {assessment.isError && (
                <ErrorState onRetry={() => void assessment.refetch()}>Não foi possível carregar a avaliação.</ErrorState>
              )}
              {assessment.data === null && (
                <EmptyState>Esta oportunidade ainda não foi avaliada contra o perfil ativo.</EmptyState>
              )}
              {assessment.data && (
                <Decision
                  assessment={assessment.data}
                  opportunityId={opportunity.data.id}
                />
              )}
            </Section>

            <Section title="Candidatura">
              <ApplicationPanel opportunityId={opportunity.data.id} />
            </Section>
          </>
        )}
      </div>
    </PageShell>
  )
}
