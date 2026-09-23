import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  type ManualInput,
  type NewSource,
  type SourceControls,
  createSource,
  getSource,
  getSourceCoverage,
  getSourceHealth,
  getSourceRuns,
  normalizeRun,
  runSource,
  submitManualRun,
  updateSourceControls,
} from './api'

export function useSourceHealth() {
  return useQuery({ queryKey: ['source-health'], queryFn: getSourceHealth })
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
