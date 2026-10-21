import { useAIBudget, useAnalysisMetrics } from '../features/dashboard/useOverview'
import { type ModelBudget, type TaskAIMetrics } from '../features/dashboard/api'
import { modelName } from '../features/dashboard/modelName'
import { Card } from './Card'
import { Bone } from './skeletons'

const taskLabels: Record<string, string> = {
  job_match: 'Análise de encaixe',
  job_classification: 'Classificação',
  job_extraction: 'Extração',
}

const numberFormat = new Intl.NumberFormat('pt-BR')

function formatCount(value: number): string {
  return numberFormat.format(value)
}

function percent(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toFixed(0)}%`
}

/** "00:00 UTC" style time of the day reset, from the API's ISO timestamp. */
function resetTime(iso: string): string | null {
  const moment = new Date(iso)
  if (Number.isNaN(moment.getTime())) return null
  return `${moment.toISOString().slice(11, 16)} UTC`
}

function ModelRow({ budget }: { budget: ModelBudget }) {
  // The provider's own daily limit is the headline (1 000/dia on Groq free); a model with
  // none known falls back to the operational ceiling the router enforces.
  const limit = budget.providerRequestsLimit ?? budget.requestsSoftLimit
  const remaining = budget.requestsRemaining ?? budget.requestsRemainingOperational
  const name = modelName(budget.model, budget.provider)
  const used = limit > 0 ? Math.min(1, budget.requestsUsed / limit) : 0
  return (
    <li>
      <div className="flex items-baseline justify-between gap-2">
        <span className="flex min-w-0 items-baseline gap-2">
          <span className="truncate text-sm font-medium">{name}</span>
          {budget.provider && (
            <span className="shrink-0 text-xs font-normal text-subtle">{budget.provider}</span>
          )}
        </span>
        <span className="text-xs text-subtle">
          restam {formatCount(remaining)} req
        </span>
      </div>
      <div
        aria-label={`${name}${budget.provider ? ` (${budget.provider})` : ''}: ${budget.requestsUsed} de ${limit} requisições hoje`}
        className="mt-1 h-2 w-full overflow-hidden rounded-full bg-line"
        role="img"
      >
        <div
          className="h-full rounded-full bg-ink"
          style={{ width: `${(used * 100).toFixed(0)}%` }}
        />
      </div>
      <p className="mt-1 text-xs text-subtle">
        {formatCount(budget.requestsUsed)} / {formatCount(limit)} req hoje · tokens{' '}
        {formatCount(budget.tokensUsed)} / {formatCount(budget.tokensLimit)} (restam{' '}
        {formatCount(budget.tokensRemaining)})
      </p>
    </li>
  )
}

function TaskRow({ task }: { task: TaskAIMetrics }) {
  return (
    <li className="flex items-baseline justify-between gap-2 text-xs text-subtle">
      <span className="text-sm text-ink">{taskLabels[task.task] ?? task.task}</span>
      <span>
        {task.avgTokensPerJob === null ? '—' : formatCount(Math.round(task.avgTokensPerJob))}{' '}
        tokens/vaga · fallback {percent(task.fallbackRate)} · {formatCount(task.jobs)} vagas
      </span>
    </li>
  )
}

/**
 * Cards R55-C4 and R55-C6: today's request and token balance per model, with the provider's
 * daily limit, and the average cost per job and fallback rate per task.
 *
 * While the budget loads it shows a placeholder, never "desligada": the state only
 * speaks once the API has answered.
 */
export function AIBudgetCard() {
  const budget = useAIBudget()
  const metrics = useAnalysisMetrics()

  if (budget.isError) {
    return (
      <Card>
        <p className="text-sm text-muted">Orçamento diário de IA</p>
        <p className="mt-2 text-sm text-subtle">Não foi possível carregar o orçamento de IA.</p>
      </Card>
    )
  }
  if (!budget.data) {
    return (
      <Card>
        <p className="text-sm text-muted">Orçamento diário de IA</p>
        <div aria-busy="true" className="mt-3 space-y-2">
          <Bone className="h-4 w-2/3" />
          <Bone className="h-2 w-full" />
        </div>
      </Card>
    )
  }

  const { data } = budget
  if (data.state !== 'enabled') {
    return (
      <Card>
        <p className="text-sm text-muted">Orçamento diário de IA</p>
        <p className="mt-2 text-sm text-subtle">
          {data.state === 'blocked_by_configuration'
            ? 'Bloqueada por configuração: nenhum provedor de IA tem chave.'
            : 'IA desligada: nenhuma requisição é gasta.'}
        </p>
      </Card>
    )
  }

  const reset = resetTime(data.resetsAt)
  const hasGroq = data.models.some((model) => model.provider === 'groq')
  const tasks = metrics.data?.ai.byTask ?? []
  return (
    <Card>
      <p className="text-sm text-muted">Orçamento diário de IA (requisições e tokens)</p>
      <ul className="mt-3 space-y-3">
        {data.models.map((model) => (
          <ModelRow budget={model} key={model.model} />
        ))}
      </ul>
      <p className="mt-3 text-xs text-subtle">
        {/* The interactive reserve protects the Groq budget only; other providers' budgets are all the worker's. */}
        {hasGroq
          ? `Reserva interativa: ${formatCount(data.interactiveReserveRequests)} req`
          : null}
        {hasGroq && reset ? ' · ' : ''}
        {reset ? `zera às ${reset}` : ''}
      </p>
      {tasks.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <p className="text-sm text-muted">Custo médio por vaga (últimas 24 h)</p>
          <ul className="mt-2 space-y-1">
            {tasks.map((task) => (
              <TaskRow key={task.task} task={task} />
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}
