import { useMemo, useState } from 'react'
import { type ControlsDraft, draftFrom, missingForEnable } from '../features/sources/gate'
import { type SourceHealth } from '../features/sources/api'
import {
  useProbeQueue,
  useProbeSource,
  useSource,
  useSourceHealth,
  useUpdateSourceControls,
} from '../features/sources/useSources'
import { ConflictError } from '../lib/api'
import { Button } from './Button'
import { Card } from './Card'
import { PrimaryText, SecondaryText } from './cells'
import { DataTable, RowSelect } from './DataTable'
import { controlClassName } from './Field'
import { CardListSkeleton } from './skeletons'
import { ConflictNotice, EmptyState, ErrorState, LoadingState } from './states'
import { StatusBadge } from './StatusBadge'

type QueueState = 'no_probe' | 'probe_failed' | 'confirmed' | 'ready'

const stateLabels: Record<QueueState, string> = {
  no_probe: 'Sem sonda',
  probe_failed: 'Sonda falhou',
  confirmed: 'Evidência confirmada',
  ready: 'Pronta para habilitar',
}

const stateTones: Record<QueueState, string> = {
  no_probe: 'border-line-strong bg-canvas text-neutral-ink',
  probe_failed: 'border-danger-line bg-danger-surface-strong text-danger-ink',
  confirmed: 'border-success-line bg-success-surface text-success-ink',
  ready: 'border-accent bg-accent-surface text-accent-ink',
}

/** The queue's own read of a proposal's state — never persisted, only ever displayed. */
function stateFor(source: SourceHealth, probeFailed: boolean): QueueState {
  if (source.termsReviewed && source.collectorLocalTested) return 'ready'
  if (probeFailed && !source.collectorLocalTested) return 'probe_failed'
  if (source.collectorLocalTested) return 'confirmed'
  return 'no_probe'
}

/**
 * The queue's card for one proposal at a time (F20-25 sequential mode).
 *
 * Reuses the F14-02/F14-06 routes exactly as `SourceControlsPanel` does — this is not a
 * new endpoint, only a narrower flow: test the collector, mark terms reviewed with a
 * date, then enable, in that order, with "Pular"/"Próxima" moving on without ever
 * returning to the list.
 */
function SequentialCard({
  sourceId,
  onAdvance,
}: {
  sourceId: string
  onAdvance: (enabled: boolean) => void
}) {
  const source = useSource(sourceId)
  const probe = useProbeSource(sourceId)
  const update = useUpdateSourceControls(sourceId)
  const [draft, setDraft] = useState<ControlsDraft | null>(null)

  if (source.isPending) return <LoadingState className="mt-4">Carregando proposta…</LoadingState>
  if (source.isError || !source.data) {
    return (
      <ErrorState className="mt-4" onRetry={() => void source.refetch()}>
        Não foi possível carregar esta proposta.
      </ErrorState>
    )
  }

  const record = source.data
  const current = draft ?? draftFrom(record)
  const missing = missingForEnable(record, current)
  const edit = (patch: Partial<ControlsDraft>) => setDraft({ ...current, ...patch })

  function enable() {
    update.mutate(
      {
        enabled: true,
        termsReviewed: current.termsReviewed,
        collectorLocalTested: current.collectorLocalTested,
        reviewedAt: current.reviewedOn ? `${current.reviewedOn}T12:00:00Z` : null,
        expectedVersion: record.version,
      },
      { onSuccess: () => onAdvance(true) },
    )
  }

  return (
    <Card as="article">
      <h3 className="font-semibold">
        {record.name} <span className="font-normal text-muted">({record.sourceType})</span>
      </h3>
      <p className="mt-1 text-sm text-subtle">
        evidência {record.evidenceStatus} · versão {record.version}
      </p>
      {Object.keys(record.configuration).length > 0 && (
        <dl className="mt-3 grid gap-1 text-sm">
          {Object.entries(record.configuration).map(([key, value]) => (
            <div className="flex gap-2" key={key}>
              <dt className="text-muted">{key}</dt>
              <dd className="font-medium">{String(value)}</dd>
            </div>
          ))}
        </dl>
      )}

      <ol className="mt-4 flex flex-col gap-3">
        <li>
          <p className="text-sm font-medium">1. Testar o collector</p>
          <Button
            className="mt-2"
            disabled={probe.isPending}
            onClick={() => probe.mutate(record.version)}
            size="sm"
            variant="secondary"
          >
            {probe.isPending ? 'Testando…' : 'Testar o collector'}
          </Button>
          {probe.data && (
            <p
              className={`mt-2 text-sm ${probe.data.probe.status === 'PASSED' ? 'text-success-ink' : 'text-danger-ink'}`}
              role="status"
            >
              {probe.data.probe.status === 'PASSED'
                ? `Confirmado (${probe.data.probe.itemsSeen} item).`
                : `Falhou: ${probe.data.probe.errorCode ?? 'erro'} — ${probe.data.probe.detail ?? 'sem detalhe'}.`}
            </p>
          )}
        </li>
        <li>
          <p className="text-sm font-medium">2. Termos revisados</p>
          <label className="mt-2 flex items-center gap-2 text-sm">
            <input
              checked={current.termsReviewed}
              className="h-4 w-4"
              onChange={(event) => edit({ termsReviewed: event.target.checked })}
              type="checkbox"
            />
            Revisei os termos de uso desta fonte
          </label>
          <input
            aria-label="Data da revisão"
            className={`mt-2 ${controlClassName}`}
            onChange={(event) => edit({ reviewedOn: event.target.value })}
            type="date"
            value={current.reviewedOn}
          />
        </li>
        <li>
          <p className="text-sm font-medium">3. Habilitar</p>
          <Button className="mt-2" disabled={update.isPending || missing.length > 0} onClick={enable}>
            Habilitar
          </Button>
          {missing.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-sm text-warning-ink">
              {missing.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </li>
      </ol>

      {update.isError &&
        (update.error instanceof ConflictError ? (
          <ConflictNotice className="mt-4" onReload={() => void source.refetch()}>
            A fonte mudou enquanto você a homologava. Recarregue e confira antes de habilitar.
          </ConflictNotice>
        ) : (
          <ErrorState className="mt-4">{update.error.message}</ErrorState>
        ))}

      <div className="mt-5 flex flex-wrap gap-3 max-md:[&_button]:flex-1">
        <Button onClick={() => onAdvance(false)} variant="secondary">
          Pular fonte
        </Button>
        <Button onClick={() => onAdvance(false)}>Próxima</Button>
      </div>
    </Card>
  )
}

export function HomologationQueue() {
  const health = useSourceHealth({ status: 'proposed' })
  const batch = useProbeQueue()
  const [mode, setMode] = useState<'list' | 'sequential'>('list')
  const [cursor, setCursor] = useState(0)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [failedProbes, setFailedProbes] = useState<Set<string>>(new Set())
  const [enabledCount, setEnabledCount] = useState(0)

  const items = useMemo(() => health.data?.items ?? [], [health.data])

  const counters = useMemo(() => {
    let withoutProbe = 0
    let probeFailed = 0
    let confirmed = 0
    for (const item of items) {
      const state = stateFor(item, failedProbes.has(item.sourceDefinitionId))
      if (state === 'no_probe') withoutProbe += 1
      else if (state === 'probe_failed') probeFailed += 1
      else confirmed += 1
    }
    return { withoutProbe, probeFailed, confirmed, enabled: enabledCount }
  }, [items, failedProbes, enabledCount])

  function toggleSelected(sourceId: string) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(sourceId)) next.delete(sourceId)
      else next.add(sourceId)
      return next
    })
  }

  function toggleAll(selected: boolean) {
    setSelected(selected ? new Set(items.map((item) => item.sourceDefinitionId)) : new Set())
  }

  function runBatch() {
    const targets = items
      .filter((item) => selected.has(item.sourceDefinitionId))
      .map((item) => ({ sourceId: item.sourceDefinitionId, expectedVersion: item.version }))
    batch.mutate(targets, {
      onSuccess: (results) => {
        setFailedProbes((current) => {
          const next = new Set(current)
          for (const result of results) {
            if (result.ok) next.delete(result.sourceId)
            else next.add(result.sourceId)
          }
          return next
        })
      },
    })
  }

  function advance(enabled: boolean) {
    if (enabled) setEnabledCount((count) => count + 1)
    setCursor((current) => current + 1)
  }

  if (health.isPending) return <CardListSkeleton label="Carregando a fila de homologação…" />
  if (health.isError) {
    return (
      <ErrorState onRetry={() => void health.refetch()}>
        Não foi possível carregar a fila de homologação.
      </ErrorState>
    )
  }
  if (items.length === 0) {
    return <EmptyState>Nenhuma proposta aguardando homologação.</EmptyState>
  }

  if (mode === 'sequential') {
    const current = items[cursor]
    const completed = Math.min(cursor, items.length)
    return (
      <div aria-live="polite">
        <div className="rounded-control border border-line bg-panel p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <div>
              <p className="text-sm font-semibold">Revisão uma a uma</p>
              <p className="mt-1 text-sm text-subtle">
                Teste o collector, registre a revisão dos termos e habilite somente quando os
                requisitos estiverem concluídos.
              </p>
            </div>
            <p className="text-sm font-medium text-ink">
              {current ? `${cursor + 1} de ${items.length}` : `${items.length} de ${items.length}`}
            </p>
          </div>
          <progress
            aria-label={`${completed} de ${items.length} propostas percorridas`}
            className="mt-3 h-2 w-full accent-ink"
            max={items.length}
            value={completed}
          />
        </div>
        {current ? (
          <div className="mt-3">
            <SequentialCard onAdvance={advance} sourceId={current.sourceDefinitionId} />
          </div>
        ) : (
          <EmptyState className="mt-3">
            Fila percorrida. {enabledCount} habilitada{enabledCount === 1 ? '' : 's'} nesta sessão.
          </EmptyState>
        )}
        <Button className="mt-4" onClick={() => setMode('list')} variant="secondary">
          Voltar para a lista
        </Button>
      </div>
    )
  }

  return (
    <div>
      <div className="rounded-control border border-line bg-panel p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <div>
            <h2 className="text-sm font-semibold">Propostas aguardando homologação</h2>
            <p className="mt-1 text-sm text-subtle">
              Selecione fontes para testar em lote ou revise uma fonte por vez antes de habilitar.
            </p>
          </div>
          <p aria-live="polite" className="text-sm font-medium text-ink">
            {selected.size} selecionada{selected.size === 1 ? '' : 's'}
          </p>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div className="rounded-control border border-line bg-surface p-3">
          <dt className="text-muted">Sem sonda</dt>
          <dd className="mt-1 text-lg font-semibold">{counters.withoutProbe}</dd>
        </div>
        <div className="rounded-control border border-line bg-surface p-3">
          <dt className="text-muted">Sonda falhou</dt>
          <dd className="mt-1 text-lg font-semibold">{counters.probeFailed}</dd>
        </div>
        <div className="rounded-control border border-line bg-surface p-3">
          <dt className="text-muted">Confirmadas</dt>
          <dd className="mt-1 text-lg font-semibold">{counters.confirmed}</dd>
        </div>
        <div className="rounded-control border border-line bg-surface p-3">
          <dt className="text-muted">Habilitadas</dt>
          <dd className="mt-1 text-lg font-semibold">{counters.enabled}</dd>
        </div>
      </dl>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <section aria-labelledby="batch-mode-title" className="rounded-control border border-line bg-surface p-4">
          <h3 className="text-sm font-semibold" id="batch-mode-title">Teste em lote</h3>
          <p className="mt-1 text-sm text-subtle">Confirma se os collectors respondem; termos e habilitação continuam individuais.</p>
          <Button
            className="mt-3 w-full sm:w-auto"
            disabled={selected.size === 0 || batch.isPending}
            onClick={runBatch}
            variant="secondary"
          >
            {batch.isPending ? 'Testando…' : `Testar selecionadas (${selected.size})`}
          </Button>
        </section>
        <section aria-labelledby="sequential-mode-title" className="rounded-control border border-line bg-surface p-4">
          <h3 className="text-sm font-semibold" id="sequential-mode-title">Revisão uma a uma</h3>
          <p className="mt-1 text-sm text-subtle">Conduz cada fonte pela sonda, revisão de termos e habilitação.</p>
          <Button
            className="mt-3 w-full sm:w-auto"
            onClick={() => {
              setCursor(0)
              setMode('sequential')
            }}
          >
            Modo sequencial
          </Button>
        </section>
      </div>

      <DataTable
        caption="Propostas aguardando homologação"
        className="mt-4"
        columns={['Fonte', 'Estado', 'Ações']}
        selectable
        allSelected={selected.size === items.length}
        someSelected={selected.size > 0}
        onToggleAll={toggleAll}
        selectAllLabel="Selecionar todas as propostas"
      >
        {items.map((item, index) => {
          const state = stateFor(item, failedProbes.has(item.sourceDefinitionId))
          const result = batch.data?.find((row) => row.sourceId === item.sourceDefinitionId)
          return (
            <tr
              aria-selected={selected.has(item.sourceDefinitionId)}
              className={selected.has(item.sourceDefinitionId) ? 'bg-accent-surface' : undefined}
              key={item.sourceDefinitionId}
            >
              <td className="w-10">
                <RowSelect
                  checked={selected.has(item.sourceDefinitionId)}
                  label={`Selecionar ${item.name}`}
                  onChange={() => toggleSelected(item.sourceDefinitionId)}
                />
              </td>
              <td className="min-w-28">
                <PrimaryText>{item.name}</PrimaryText>
                <SecondaryText>{item.sourceType}</SecondaryText>
                {result && (
                  <p
                    className={`mt-1 text-caption ${result.ok ? 'text-success-ink' : 'text-danger-ink'}`}
                    role="status"
                  >
                    {result.ok
                      ? 'Sonda confirmada.'
                      : `Falhou: ${result.errorCode ?? 'erro'}${
                          result.retryAfterSeconds !== null
                            ? ` — aguardar ${result.retryAfterSeconds}s`
                            : ''
                        }`}
                  </p>
                )}
              </td>
              <td>
                <StatusBadge labels={stateLabels} tones={stateTones} value={state} />
              </td>
              <td className="min-w-28">
                <Button
                  aria-label={`Homologar ${item.name}`}
                  className="max-md:w-full"
                  onClick={() => {
                    setCursor(index)
                    setMode('sequential')
                  }}
                  size="sm"
                  variant="secondary"
                >
                  Homologar
                </Button>
              </td>
            </tr>
          )
        })}
      </DataTable>
    </div>
  )
}
