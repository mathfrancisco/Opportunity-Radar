import { type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApplicationPanel } from '../components/ApplicationPanel'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { DataTable } from '../components/DataTable'
import { PageShell } from '../components/PageShell'
import { EmptyState, ErrorState, LoadingState } from '../components/states'
import {
  type EligibilityDetail,
  type MatchAnalysis,
  type MatchAssessment,
  type MatchFactor,
} from '../features/matching/api'
import {
  useAnalyzeAssessment,
  useEvaluateOpportunity,
  useLatestAssessment,
} from '../features/matching/useAssessment'
import { type OpportunityDetail } from '../features/opportunities/api'
import { verdictLabels } from '../features/matching/verdicts'
import { useOpportunity } from '../features/opportunities/useOpportunity'

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
    <section className="mt-10">
      <h2 className="text-lg font-semibold">{title}</h2>
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

function Analysis({
  assessment,
  analysis,
  onRun,
  running,
  failed,
}: {
  assessment: MatchAssessment
  analysis: MatchAnalysis | null
  onRun: (refresh: boolean) => void
  running: boolean
  failed: boolean
}) {
  return (
    <>
      {analysis === null && (
        <EmptyState>Nenhuma análise semântica registrada para esta avaliação.</EmptyState>
      )}
      {analysis && analysis.status !== 'AI_COMPLETED' && (
        <div className="rounded-2xl border border-warning-line bg-warning-surface p-5 text-sm">
          <p className="font-medium text-warning-ink">
            Camada semântica degradada ({analysis.status}
            {analysis.failureCode ? `, ${analysis.failureCode}` : ''}).
          </p>
          <p className="mt-2 text-subtle">
            {analysis.detail ?? 'A decisão determinística acima permanece completa.'}
          </p>
        </div>
      )}
      {analysis?.status === 'AI_COMPLETED' && (
        <Card className="text-sm">
          <p className="leading-6">{analysis.summary}</p>
          {analysis.strengths.length > 0 && (
            <>
              <h3 className="mt-4 font-semibold">Pontos fortes</h3>
              <ul className="mt-2 list-disc pl-5 text-subtle">
                {analysis.strengths.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
          {analysis.risks.length > 0 && (
            <>
              <h3 className="mt-4 font-semibold">Riscos</h3>
              <ul className="mt-2 list-disc pl-5 text-subtle">
                {analysis.risks.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
          {analysis.unknowns.length > 0 && (
            <>
              <h3 className="mt-4 font-semibold">O anúncio não responde</h3>
              <ul className="mt-2 list-disc pl-5 text-subtle">
                {analysis.unknowns.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
          {analysis.recommendedReview && (
            <p className="mt-4 font-medium text-warning-ink">
              A análise sugere revisão humana antes de aplicar.
            </p>
          )}
          <p className="mt-4 text-xs text-muted">
            {analysis.modelId} · {analysis.promptVersion} · {analysis.schemaVersion} ·{' '}
            {formatDate(analysis.analyzedAt)}
          </p>
        </Card>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button
          disabled={running}
          onClick={() => onRun(analysis?.status === 'AI_COMPLETED')}
        >
          {running
            ? 'Analisando…'
            : analysis?.status === 'AI_COMPLETED'
              ? 'Analisar novamente'
              : 'Analisar com Ollama'}
        </Button>
        <span className="text-xs text-muted">
          A análise é consultiva: não altera score, verdict nem elegibilidade da avaliação{' '}
          {assessment.id.slice(0, 8)}.
        </span>
      </div>
      {failed && (
        <p className="mt-3 text-sm text-danger-ink">
          Não foi possível falar com a API. Tente novamente.
        </p>
      )}
    </>
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
        <span className="text-4xl font-semibold tracking-[-0.03em]">
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
        <Analysis
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

            {opportunity.data.description && (
              <Section title="Descrição">
                <p className="whitespace-pre-line leading-7 text-subtle">
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
