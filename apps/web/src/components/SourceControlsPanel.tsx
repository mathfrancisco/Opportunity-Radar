import { useState } from 'react'
import { type ControlsDraft as Draft, draftFrom, missingForEnable } from '../features/sources/gate'
import { useProbeSource, useSource, useUpdateSourceControls } from '../features/sources/useSources'
import { ConflictError } from '../lib/api'
import { Button } from './Button'
import { Field, controlClassName } from './Field'
import { ConflictNotice, ErrorState, LoadingState } from './states'

export function SourceControlsPanel({ sourceId }: { sourceId: string }) {
  const source = useSource(sourceId)
  // Null while the form mirrors the server. Once the operator touches it, the draft is
  // theirs, and it survives a conflict reload: the intent stays, the version refreshes.
  const [draft, setDraft] = useState<Draft | null>(null)
  const update = useUpdateSourceControls(sourceId)
  const probe = useProbeSource(sourceId)

  if (source.isPending) return <LoadingState className="mt-4">Carregando homologação…</LoadingState>
  if (source.isError || !source.data) {
    return (
      <ErrorState className="mt-4" onRetry={() => void source.refetch()}>
        Não foi possível carregar a homologação desta fonte.
      </ErrorState>
    )
  }

  const record = source.data
  const current = draft ?? draftFrom(record)
  const missing = missingForEnable(record, current)
  const edit = (patch: Partial<Draft>) => setDraft({ ...current, ...patch })

  function send(enabled: boolean) {
    update.mutate(
      {
        enabled,
        termsReviewed: current.termsReviewed,
        collectorLocalTested: current.collectorLocalTested,
        reviewedAt: current.reviewedOn ? `${current.reviewedOn}T12:00:00Z` : null,
        expectedVersion: record.version,
      },
      { onSuccess: () => setDraft(null) },
    )
  }

  const reviewId = `review-${sourceId}`
  const gateId = `gate-${sourceId}`

  return (
    <section aria-labelledby={reviewId} className="mt-4 rounded-2xl border border-line bg-panel p-4">
      <h3 className="font-semibold" id={reviewId}>
        Homologação
      </h3>
      <p className="mt-1 text-sm text-subtle">
        {record.enabled ? 'Habilitada' : 'Desabilitada'} · evidência {record.evidenceStatus} ·
        versão {record.version}
      </p>

      {record.sourceType !== 'manual' && (
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <label className="flex min-h-10 items-center gap-2 text-sm">
            <input
              checked={current.termsReviewed}
              className="h-4 w-4"
              onChange={(event) => edit({ termsReviewed: event.target.checked })}
              type="checkbox"
            />
            Termos de uso revisados
          </label>
          <label className="flex min-h-10 items-center gap-2 text-sm">
            <input
              checked={current.collectorLocalTested}
              className="h-4 w-4"
              onChange={(event) => edit({ collectorLocalTested: event.target.checked })}
              type="checkbox"
            />
            Collector testado localmente
          </label>
          <Field hint="Vazio mantém a data já registrada." label="Data da revisão">
            <input
              className={controlClassName}
              onChange={(event) => edit({ reviewedOn: event.target.value })}
              type="date"
              value={current.reviewedOn}
            />
          </Field>
        </div>
      )}

      {record.sourceType !== 'manual' && !record.enabled && (
        <div className="mt-4 rounded-xl border border-line bg-surface p-3 text-sm">
          <p className="font-medium">Teste do collector</p>
          <p className="mt-1 text-subtle">
            Pede um item ao endpoint público e descarta o que leu. Se o collector entender a
            resposta, a evidência fica confirmada e o collector, testado. Termos revisados e a
            habilitação continuam com você.
          </p>
          <Button
            className="mt-3"
            disabled={probe.isPending}
            onClick={() => {
              update.reset()
              probe.mutate(record.version)
            }}
            size="sm"
            variant="secondary"
          >
            {probe.isPending ? 'Testando…' : 'Testar o collector agora'}
          </Button>
          {probe.data && (
            <p
              className={`mt-3 ${probe.data.probe.status === 'PASSED' ? 'text-success-ink' : 'text-danger-ink'}`}
              role="status"
            >
              {probe.data.probe.status === 'PASSED'
                ? `O collector leu o endpoint (${probe.data.probe.itemsSeen} item, ${probe.data.probe.httpRequests} requisição). Evidência confirmada.`
                : `O teste falhou: ${probe.data.probe.errorCode ?? 'erro'} — ${probe.data.probe.detail ?? 'sem detalhe'}. A fonte não mudou.`}
            </p>
          )}
          {probe.isError &&
            (probe.error instanceof ConflictError ? (
              <ConflictNotice
                className="mt-3"
                onReload={() => {
                  probe.reset()
                  void source.refetch()
                }}
              >
                A fonte mudou enquanto o teste rodava, e nada foi registrado. Recarregue e teste
                de novo.
              </ConflictNotice>
            ) : (
              <ErrorState className="mt-3">{probe.error.message}</ErrorState>
            ))}
        </div>
      )}

      {!record.enabled && missing.length > 0 && (
        <div className="mt-4 text-sm text-warning-ink" id={gateId}>
          <p className="font-medium">Para habilitar, falta:</p>
          <ul className="mt-1 list-disc pl-5">
            {missing.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {update.isError &&
        (update.error instanceof ConflictError ? (
          <ConflictNotice className="mt-4" onReload={() => {
              update.reset()
              void source.refetch()
            }}
          >
            A fonte mudou depois que você a abriu. Recarregue para ver a versão atual — o que
            você marcou aqui continua marcado; confira e envie de novo.
          </ConflictNotice>
        ) : (
          <ErrorState className="mt-4">{update.error.message}</ErrorState>
        ))}
      {update.isSuccess && (
        <p className="mt-4 text-sm text-success-ink" role="status">
          Homologação registrada. A fonte está {update.data.enabled ? 'habilitada' : 'desabilitada'}.
        </p>
      )}

      <div className="mt-4 flex flex-wrap gap-3">
        {record.enabled ? (
          <Button disabled={update.isPending} onClick={() => send(false)}>
            Desabilitar e parar a coleta
          </Button>
        ) : (
          <Button
            aria-describedby={missing.length > 0 ? gateId : undefined}
            disabled={update.isPending || missing.length > 0}
            onClick={() => send(true)}
          >
            Habilitar
          </Button>
        )}
        {record.sourceType !== 'manual' && (
          <Button
            disabled={update.isPending || draft === null}
            onClick={() => send(record.enabled)}
            variant="secondary"
          >
            Salvar sem mudar a habilitação
          </Button>
        )}
      </div>
    </section>
  )
}
