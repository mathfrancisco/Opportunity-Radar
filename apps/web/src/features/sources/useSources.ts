import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getSourceHealth, getSourceRuns, runSource } from './api'

export function useSourceHealth() {
  return useQuery({ queryKey: ['source-health'], queryFn: getSourceHealth })
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
      void client.invalidateQueries({ queryKey: ['source-runs', sourceId] })
      void client.invalidateQueries({ queryKey: ['overview'] })
    },
  })
}
