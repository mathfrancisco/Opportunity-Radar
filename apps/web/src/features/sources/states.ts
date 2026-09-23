/**
 * The states a source can be in, named once.
 *
 * These maps existed twice, in `SourcesPage` and in `OverviewPage`, with different labels
 * for the same value. Two translations of one state teach the operator two vocabularies
 * for the same screenful of information.
 */

/** Outcome of one `SourceRun`, as the API reports it. */
export const runStatusLabels: Record<string, string> = {
  SUCCEEDED: 'Sucesso',
  PARTIAL: 'Parcial',
  FAILED: 'Falhou',
  RUNNING: 'Executando',
  PENDING: 'Na fila',
  CANCELLED: 'Cancelada',
}

export const runStatusTones: Record<string, string> = {
  SUCCEEDED: 'border-success-line bg-success-surface text-success-ink',
  PARTIAL: 'border-warning-line bg-warning-surface text-warning-ink',
  FAILED: 'border-danger-line bg-danger-surface text-danger-ink',
  RUNNING: 'border-line-strong bg-canvas text-neutral-ink',
  PENDING: 'border-line-strong bg-canvas text-neutral-ink',
  CANCELLED: 'border-line-strong bg-canvas text-muted',
}

/**
 * Why a source produced what it produced in a metrics window. Keeping `SUCCEEDED_ZERO`
 * apart from `NOT_RUN` is the whole point of the coverage state: one is a source that
 * answered nothing, the other a source that was never asked.
 */
export const coverageLabels: Record<string, string> = {
  NOT_ENABLED: 'Não habilitada',
  CONFIGURATION_BLOCKED: 'Bloqueada por homologação',
  NOT_SCHEDULED: 'Sem agendamento',
  NOT_RUN: 'Não executou na janela',
  SUCCEEDED_ZERO: 'Sucesso sem vagas',
  SUCCEEDED: 'Saudável',
  PARTIAL: 'Degradada',
  FAILED: 'Falhou',
  CANCELLED: 'Cancelada',
}

export const coverageTones: Record<string, string> = {
  NOT_ENABLED: 'border-line-strong bg-canvas text-neutral-ink',
  CONFIGURATION_BLOCKED: 'border-line-strong bg-canvas text-neutral-ink',
  NOT_SCHEDULED: 'border-line-strong bg-canvas text-neutral-ink',
  NOT_RUN: 'border-line-strong bg-canvas text-neutral-ink',
  SUCCEEDED: 'border-success-line bg-success-surface text-success-ink',
  SUCCEEDED_ZERO: 'border-line-strong bg-canvas text-neutral-ink',
  PARTIAL: 'border-warning-line bg-warning-surface text-warning-ink',
  FAILED: 'border-danger-line bg-danger-surface text-danger-ink',
  CANCELLED: 'border-line-strong bg-canvas text-muted',
}
