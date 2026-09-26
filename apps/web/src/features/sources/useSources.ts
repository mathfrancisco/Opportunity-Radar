import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  type BatchProbeResult,
  type ManualInput,
  type NewSource,
  type SourceControls,
  createSource,
  getSource,
  getSourceCoverage,
  getSourceHealth,
  getSourceRuns,
  normalizeRun,
  probeSource,
  runSource,
  submitManualRun,
  updateSourceControls,
} from './api'

/** The default wait between probes in a batch when the source did not reply 429. */
const DEFAULT_BATCH_PROBE_DELAY_MS = 500

export function useSourceHealth(params?: { status?: 'proposed' }) {
  return useQuery({
    queryKey: ['source-health', params?.status ?? null],
    queryFn: () => getSourceHealth(params),
  })
}

export function useSourceCoverage() {
  return useQuery({ queryKey: ['source-coverage'], queryFn: getSourceCoverage })
}

export function useSourceRuns(sourceId: string | null) {
  return useQuery({
    queryKey: ['source-runs', sourceId],
    queryFn: () => getSourceRuns(sourceId ?? ''),
    enabled: sourceId !== null,
  })
}

export function useRunSource() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (sourceId: string) => runSource(sourceId),
    onSettled: (_data, _error, sourceId) => {
      void client.invalidateQueries({ queryKey: ['source-health'] })
      void client.invalidateQueries({ queryKey: ['source-coverage'] })
      void client.invalidateQueries({ queryKey: ['source-runs', sourceId] })
      void client.invalidateQueries({ queryKey: ['overview'] })
    },
  })
}

/** Everything a change to the source list can move: the list, the coverage and the overview. */
function refreshCatalogue(client: ReturnType<typeof useQueryClient>) {
  void client.invalidateQueries({ queryKey: ['source-health'] })
  void client.invalidateQueries({ queryKey: ['source-coverage'] })
  void client.invalidateQueries({ queryKey: ['source-metrics'] })
  void client.invalidateQueries({ queryKey: ['overview'] })
}

export function useSource(sourceId: string | null) {
  return useQuery({
    queryKey: ['source', sourceId],
    queryFn: () => getSource(sourceId ?? ''),
    enabled: sourceId !== null,
  })
}

export function useCreateSource() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: NewSource) => createSource(input),
    onSuccess: () => refreshCatalogue(client),
  })
}

export function useUpdateSourceControls(sourceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (controls: SourceControls) => updateSourceControls(sourceId, controls),
    onSuccess: (source) => {
      client.setQueryData(['source', sourceId], source)
      refreshCatalogue(client)
    },
  })
}

/**
 * Submits manual inputs and normalizes what the run preserved, as one step for the
 * operator: they registered a job, and the answer they want is what became of it.
 */
export function useManualIntake(sourceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (inputs: ManualInput[]) => {
      const run = await submitManualRun(sourceId, inputs)
      const items = await normalizeRun(run.id)
      return { run, items }
    },
    onSettled: () => {
      refreshCatalogue(client)
      void client.invalidateQueries({ queryKey: ['source-runs', sourceId] })
      void client.invalidateQueries({ queryKey: ['inbox'] })
    },
  })
}

export function useProbeSource(sourceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (expectedVersion: number) => probeSource(sourceId, expectedVersion),
    onSuccess: ({ source }) => {
      client.setQueryData(['source', sourceId], source)
      refreshCatalogue(client)
    },
  })
}

/**
 * Probes several sources one at a time (`for … await`), never in parallel — the queue's
 * "test several" button (F20-25). A `SOURCE_RATE_LIMITED` result waits its own
 * `retryAfterSeconds` (or a fixed default) before probing the next one; anything else
 * moves on immediately. Only the probe runs in a batch: terms review and enabling a
 * source always happen one at a time, from the sequential card.
 */
export function useProbeQueue() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (
      sources: { sourceId: string; expectedVersion: number }[],
    ): Promise<BatchProbeResult[]> => {
      const results: BatchProbeResult[] = []
      for (const [index, { sourceId, expectedVersion }] of sources.entries()) {
        let errorCode: string | null = null
        let retryAfterSeconds: number | null = null
        try {
          const { probe } = await probeSource(sourceId, expectedVersion)
          errorCode = probe.errorCode
          retryAfterSeconds = probe.retryAfterSeconds
          results.push({
            sourceId,
            ok: probe.status === 'PASSED',
            detail: probe.detail,
            errorCode,
            retryAfterSeconds,
          })
        } catch (error) {
          results.push({
            sourceId,
            ok: false,
            detail: error instanceof Error ? error.message : 'Falha inesperada.',
            errorCode: null,
            retryAfterSeconds: null,
          })
        }
        const isLast = index === sources.length - 1
        if (!isLast) {
          const wait =
            errorCode === 'SOURCE_RATE_LIMITED'
              ? (retryAfterSeconds ?? DEFAULT_BATCH_PROBE_DELAY_MS / 1000) * 1000
              : DEFAULT_BATCH_PROBE_DELAY_MS
          await new Promise((resolve) => setTimeout(resolve, wait))
        }
      }
      return results
    },
    onSettled: () => refreshCatalogue(client),
  })
}
