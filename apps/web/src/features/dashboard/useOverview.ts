import { useQuery } from '@tanstack/react-query'
import { getAnalysisMetrics, getOverview, getSourceMetrics } from './api'

export function useOverview() {
  return useQuery({ queryKey: ['overview'], queryFn: getOverview })
}

export function useSourceMetrics() {
  return useQuery({ queryKey: ['source-metrics'], queryFn: getSourceMetrics })
}

export function useAnalysisMetrics() {
  return useQuery({ queryKey: ['analysis-metrics'], queryFn: getAnalysisMetrics })
}
