import { type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApplicationPanel } from '../components/ApplicationPanel'
import { PageShell } from '../components/PageShell'
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
import { useOpportunity } from '../features/opportunities/useOpportunity'

const verdictLabels: Record<string, string> = {
  HIGH_PRIORITY: 'Alta prioridade',
  RECOMMENDED: 'Recomendada',
  WATCHLIST: 'Observação',
  REVIEW_REQUIRED: 'Revisão necessária',
  LOW_MATCH: 'Baixa aderência',
  INELIGIBLE: 'Inelegível',
}

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
        <dt className="text-[#6d827b]">Empresa</dt>
        <dd className="mt-1 font-medium">{display(opportunity.companyName)}</dd>
      </div>
      <div>
        <dt className="text-[#6d827b]">Localização</dt>
        <dd className="mt-1 font-medium">{display(opportunity.location)}</dd>
      </div>
      <div>
        <dt className="text-[#6d827b]">Modalidade</dt>
        <dd className="mt-1 font-medium">{opportunity.workMode}</dd>
      </div>
      <div>
        <dt className="text-[#6d827b]">Senioridade</dt>
        <dd className="mt-1 font-medium">{opportunity.seniority}</dd>
      </div>
      <div>
        <dt className="text-[#6d827b]">Contrato</dt>
        <dd className="mt-1 font-medium">{opportunity.contractType}</dd>
      </div>
      <div>
        <dt className="text-[#6d827b]">Status</dt>
        <dd className="mt-1 font-medium">{opportunity.lifecycleStatus}</dd>
      </div>
      <div>
        <dt className="text-[#6d827b]">Publicada</dt>
        <dd className="mt-1 font-medium">{formatDate(opportunity.publishedAt)}</dd>
      </div>
      <div>
        <dt className="text-[#6d827b]">Versão do conteúdo</dt>
        <dd className="mt-1 font-medium">{opportunity.version}</dd>
      </div>
    </dl>
  )
}

function Compensation({ opportunity }: { opportunity: OpportunityDetail }) {
  if (opportunity.compensations.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-[#c8d4c8] p-5 text-[#547068]">
        Nenhuma remuneração declarada nas fontes. Ausência de dado não vira zero nem
        penalidade.
      </p>
    )
  }
  return (
    <ul className="grid gap-3">
      {opportunity.compensations.map((item, index) => (
        <li
          className="rounded-2xl border border-[#dce4dc] bg-white p-5 text-sm"
          key={`${item.rawItemId}-${index}`}
        >
          <p className="font-semibold">
            {display(item.minimum)} – {display(item.maximum)} {display(item.currency)}{' '}
            <span className="font-normal text-[#6d827b]">
              ({item.period}, {item.grossNet})
            </span>
          </p>
          {item.evidenceText && (
            <p className="mt-2 text-[#547068]">“{item.evidenceText}”</p>
          )}
          <p className="mt-2 text-xs text-[#6d827b]">
            Evidência: {display(item.evidenceSource)} · raw item {item.rawItemId}
          </p>
        </li>
      ))}
    </ul>
  )
}

function Skills({ opportunity }: { opportunity: OpportunityDetail }) {
  if (opportunity.skills.length === 0) {
    return <p className="text-[#547068]">Nenhuma skill extraída.</p>
  }
  return (
    <ul className="flex flex-wrap gap-2">
      {opportunity.skills.map((skill) => (
        <li
          className="rounded-full border border-[#c8d4c8] bg-white px-4 py-2 text-sm"
          key={skill.canonicalName}
        >
          <span className="font-medium">{skill.displayName}</span>{' '}
          <span className="text-[#6d827b]">
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
          <li
            className="rounded-2xl border border-[#dce4dc] bg-white p-5 text-sm"
            key={occurrence.id}
          >
            <p className="font-medium">
              {occurrence.sourceUrl ? (
                <a
                  className="underline decoration-[#d7f06f] decoration-2 underline-offset-4"
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
            <p className="mt-2 text-[#6d827b]">
              Primeira vez {formatDate(occurrence.firstSeenAt)} · última{' '}
              {formatDate(occurrence.lastSeenAt)}
            </p>
            <p className="mt-1 text-xs text-[#6d827b]">raw item {occurrence.rawItemId}</p>
            {!occurrence.payloadRetained && (
              <p className="mt-2 rounded-xl border border-[#e3cf9a] bg-[#fbf3e2] px-3 py-2 text-xs text-[#7a5a16]">
                Conteúdo bruto expirado pela retenção
                {occurrence.payloadExpiredAt
                  ? ` em ${formatDate(occurrence.payloadExpiredAt)}`
                  : ''}
                . A procedência permanece; o reprocessamento não está mais disponível.
              </p>
            )}
          </li>
        ))}
      </ul>
      <p className="mt-4 text-sm text-[#6d827b]">
        Fingerprint {opportunity.fingerprint} ({opportunity.fingerprintVersion}) ·{' '}
        {opportunity.normalizationResults.length} resultado
        {opportunity.normalizationResults.length === 1 ? '' : 's'} de normalização.
      </p>
    </>
  )
}

function Eligibility({ details }: { details: EligibilityDetail[] }) {
  if (details.length === 0) return <p className="text-[#547068]">Nenhum filtro avaliado.</p>
  return (
    <ul className="grid gap-2">
      {details.map((detail) => (
        <li
          className="rounded-2xl border border-[#dce4dc] bg-white p-4 text-sm"
          key={detail.code}
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-medium">{detail.code}</span>
            <span
              className={
                detail.result === 'FALSE'
                  ? 'text-[#9b3e2e]'
                  : detail.result === 'UNKNOWN'
                    ? 'text-[#7a5a16]'
                    : 'text-[#42571c]'
              }
            >
              {resultLabels[detail.result] ?? detail.result}
            </span>
          </div>
          <p className="mt-1 text-[#547068]">{detail.reason}</p>
        </li>
      ))}
    </ul>
  )
}

function Factors({ factors }: { factors: MatchFactor[] }) {
  if (factors.length === 0) return <p className="text-[#547068]">Nenhum fator calculado.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-[#f2f5ef] text-xs uppercase tracking-[0.08em] text-[#6d827b]">
          <tr>
            <th className="px-4 py-3 font-semibold">Fator</th>
            <th className="px-4 py-3 font-semibold">Peso</th>
            <th className="px-4 py-3 font-semibold">Contribuição</th>
            <th className="px-4 py-3 font-semibold">Estado</th>
            <th className="px-4 py-3 font-semibold">Explicação</th>
          </tr>
        </thead>
        <tbody>
          {factors.map((factor) => (
            <tr className="border-t border-[#e4ebe4]" key={factor.factorCode}>
              <td className="px-4 py-3 font-medium">{factor.factorCode}</td>
              <td className="px-4 py-3">{formatNumber(factor.weight, 2)}</td>
              <td className="px-4 py-3">{formatNumber(factor.contribution, 2)}</td>
              <td className="px-4 py-3">
                {factor.status}
                {factor.status === 'UNKNOWN' && (
                  <span className="block text-xs text-[#6d827b]">
                    {factor.missingPolicy}
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-[#547068]">{factor.explanation}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
        <p className="rounded-2xl border border-dashed border-[#c8d4c8] p-5 text-[#547068]">
          Nenhuma análise semântica registrada para esta avaliação.
        </p>
      )}
      {analysis && analysis.status !== 'AI_COMPLETED' && (
        <div className="rounded-2xl border border-[#e3cf9a] bg-[#fbf3e2] p-5 text-sm">
          <p className="font-medium text-[#7a5a16]">
            Camada semântica degradada ({analysis.status}
            {analysis.failureCode ? `, ${analysis.failureCode}` : ''}).
          </p>
          <p className="mt-2 text-[#547068]">
            {analysis.detail ?? 'A decisão determinística acima permanece completa.'}
          </p>
        </div>
      )}
      {analysis?.status === 'AI_COMPLETED' && (
        <div className="rounded-2xl border border-[#dce4dc] bg-white p-5 text-sm">
          <p className="leading-6">{analysis.summary}</p>
          {analysis.strengths.length > 0 && (
            <>
              <h3 className="mt-4 font-semibold">Pontos fortes</h3>
              <ul className="mt-2 list-disc pl-5 text-[#547068]">
                {analysis.strengths.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
          {analysis.risks.length > 0 && (
            <>
              <h3 className="mt-4 font-semibold">Riscos</h3>
              <ul className="mt-2 list-disc pl-5 text-[#547068]">
                {analysis.risks.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
          {analysis.unknowns.length > 0 && (
            <>
              <h3 className="mt-4 font-semibold">O anúncio não responde</h3>
              <ul className="mt-2 list-disc pl-5 text-[#547068]">
                {analysis.unknowns.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
          {analysis.recommendedReview && (
            <p className="mt-4 font-medium text-[#7a5a16]">
              A análise sugere revisão humana antes de aplicar.
            </p>
          )}
          <p className="mt-4 text-xs text-[#6d827b]">
            {analysis.modelId} · {analysis.promptVersion} · {analysis.schemaVersion} ·{' '}
            {formatDate(analysis.analyzedAt)}
          </p>
        </div>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          className="rounded-xl bg-[#17322d] px-5 py-3 text-sm font-semibold text-white hover:bg-[#25483f] disabled:cursor-not-allowed disabled:opacity-40"
          disabled={running}
          onClick={() => onRun(analysis?.status === 'AI_COMPLETED')}
          type="button"
        >
          {running
            ? 'Analisando…'
            : analysis?.status === 'AI_COMPLETED'
              ? 'Analisar novamente'
              : 'Analisar com Ollama'}
        </button>
        <span className="text-xs text-[#6d827b]">
          A análise é consultiva: não altera score, verdict nem elegibilidade da avaliação{' '}
          {assessment.id.slice(0, 8)}.
        </span>
      </div>
      {failed && (
        <p className="mt-3 text-sm text-[#9b3e2e]">
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
        <span className="rounded-full border border-[#c8d4c8] bg-white px-4 py-2 text-sm font-medium">
          {verdictLabels[assessment.verdict] ?? assessment.verdict}
        </span>
        <span className="text-sm text-[#6d827b]">
          Elegibilidade {assessment.eligibility} · confiança{' '}
          {formatNumber(assessment.confidence, 2)}
        </span>
      </div>
      {assessment.isStale && (
        <p className="mt-3 rounded-xl border border-[#e3cf9a] bg-[#fbf3e2] p-3 text-sm text-[#7a5a16]" role="status">
          Esta decisão foi calculada com dados anteriores. Uma reavaliação está pendente;
          os detalhes abaixo permanecem disponíveis como histórico.
        </p>
      )}
      <p className="mt-2 text-xs text-[#6d827b]">
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
          className="text-sm text-[#547068] underline decoration-[#d7f06f] decoration-2 underline-offset-4"
          to="/inbox"
        >
          ← Voltar para as oportunidades
        </Link>
      </p>

      <div aria-live="polite">
        {opportunity.isPending && (
          <p className="mt-8 rounded-2xl bg-[#eef3df] p-5 text-[#5c694e]">
            Carregando oportunidade…
          </p>
        )}
        {opportunity.isError && (
          <div className="mt-8 rounded-2xl bg-[#f9e4df] p-5 text-[#9b3e2e]">
            <p>{opportunity.error.message}</p>
            <button
              className="mt-3 font-semibold underline"
              onClick={() => void opportunity.refetch()}
              type="button"
            >
              Tentar novamente
            </button>
          </div>
        )}

        {opportunity.data && (
          <>
            <Facts opportunity={opportunity.data} />

            {opportunity.data.description && (
              <Section title="Descrição">
                <p className="whitespace-pre-line leading-7 text-[#547068]">
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
                <button
                  className="rounded-xl bg-[#17322d] px-5 py-3 text-sm font-semibold text-white hover:bg-[#25483f] disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={evaluate.isPending}
                  onClick={() => evaluate.mutate()}
                  type="button"
                >
                  {evaluate.isPending ? 'Avaliando…' : 'Avaliar agora'}
                </button>
                {evaluate.isSuccess && <span className="text-sm text-[#547068]">Avaliação atualizada.</span>}
                {evaluate.isError && <span className="text-sm text-[#9b3e2e]">Não foi possível avaliar agora.</span>}
              </div>
              {assessment.isPending && (
                <p className="rounded-2xl bg-[#eef3df] p-5 text-[#5c694e]">
                  Carregando a avaliação…
                </p>
              )}
              {assessment.isError && (
                <div className="rounded-2xl bg-[#f9e4df] p-5 text-[#9b3e2e]">
                  <p>Não foi possível carregar a avaliação.</p>
                  <button
                    className="mt-3 font-semibold underline"
                    onClick={() => void assessment.refetch()}
                    type="button"
                  >
                    Tentar novamente
                  </button>
                </div>
              )}
              {assessment.data === null && (
                <p className="rounded-2xl border border-dashed border-[#c8d4c8] p-5 text-[#547068]">
                  Esta oportunidade ainda não foi avaliada contra o perfil ativo.
                </p>
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
