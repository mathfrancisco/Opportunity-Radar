import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState } from '../../components/states'
import {
  type AnalysisClaim,
  type AnalysisMetrics,
  type MatchAnalysis,
  type MatchAssessment,
} from './api'

function formatDate(value: string | null) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString('pt-BR')
}

/**
 * What the model call cost, in one line. Absent is said as absent: a cached answer or a row
 * from before the cost was recorded did not cost zero, it is simply not known.
 */
function analysisCost(metrics: AnalysisMetrics | null) {
  if (!metrics || metrics.totalMs === null) return 'Custo da chamada indisponível.'
  const seconds = (metrics.totalMs / 1000).toLocaleString('pt-BR', {
    maximumFractionDigits: 1,
  })
  const tokens =
    metrics.promptTokens !== null && metrics.outputTokens !== null
      ? ` · ${metrics.promptTokens} tokens de entrada, ${metrics.outputTokens} de saída`
      : ''
  return `Gerada em ${seconds} s${tokens}.`
}

const sourceLabels: Record<string, string> = {
  posting: 'anúncio',
  profile: 'perfil',
}

/**
 * Each claim with the passage behind it, quoted, and where it came from. A claim with no
 * passage is shown as an inference: the model did not find it written anywhere.
 */
function Claims({ items }: { items: AnalysisClaim[] }) {
  return (
    <ul className="mt-2 grid list-disc gap-2 pl-5 text-subtle">
      {items.map((item, index) => (
        <li key={`${index}-${item.claim}`}>
          {item.claim}
          {item.evidence && item.source ? (
            <span className="mt-1 block text-xs text-muted">
              “{item.evidence}” — {sourceLabels[item.source] ?? item.source}
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  )
}

export function AnalysisPanel({
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
          <p className="text-body">{analysis.summary}</p>
          {analysis.strengths.length > 0 && (
            <>
              <h3 className="mt-4 font-semibold">Pontos fortes</h3>
              <Claims items={analysis.strengths} />
            </>
          )}
          {analysis.risks.length > 0 && (
            <>
              <h3 className="mt-4 font-semibold">Riscos</h3>
              <Claims items={analysis.risks} />
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
          {analysis.contextRefs.length > 0 && (
            <p className="mt-4 text-xs text-muted">
              Comentada à luz de {analysis.contextRefs.length} vaga
              {analysis.contextRefs.length === 1 ? '' : 's'} parecida
              {analysis.contextRefs.length === 1 ? '' : 's'} já decidida
              {analysis.contextRefs.length === 1 ? '' : 's'}; o contexto não altera a decisão.
            </p>
          )}
          <p className="mt-4 text-xs text-muted">
            {analysis.modelId} · {analysis.promptVersion} · {analysis.schemaVersion} ·{' '}
            {formatDate(analysis.analyzedAt)}
          </p>
          <p className="mt-1 text-xs text-muted">
            {analysisCost(analysis.metrics)}
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
              : 'Analisar com IA'}
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
