import { useQuery } from '@tanstack/react-query'
import { queryStaleTimes } from '../../lib/queryClient'
import { getAnalysisMetrics, getOverview, getSourceMetrics } from './api'

export function useOverview() {
  return useQuery({ queryKey: ['overview'], queryFn: ({ signal }) => getOverview(signal), staleTime: queryStaleTimes.standard })
}

export function useSourceMetrics() {
  return useQuery({ queryKey: ['source-metrics'], queryFn: ({ signal }) => getSourceMetrics(signal), staleTime: queryStaleTimes.standard })
}

export function useAnalysisMetrics() {
  return useQuery({ queryKey: ['analysis-metrics'], queryFn: ({ signal }) => getAnalysisMetrics(signal), staleTime: queryStaleTimes.standard })
}
