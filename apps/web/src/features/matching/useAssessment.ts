import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { queryStaleTimes } from '../../lib/queryClient'
import { analyzeAssessment, evaluateOpportunity, getLatestAssessment } from './api'

export function useLatestAssessment(opportunityId: string) {
  return useQuery({
    queryKey: ['assessment', opportunityId],
    queryFn: ({ signal }) => getLatestAssessment(opportunityId, signal),
    staleTime: queryStaleTimes.standard,
  })
}

export function useAnalyzeAssessment(opportunityId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: { assessmentId: string; refresh?: boolean }) =>
      analyzeAssessment(input.assessmentId, { refresh: input.refresh }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['assessment', opportunityId] })
    },
  })
}

export function useEvaluateOpportunity(opportunityId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => evaluateOpportunity(opportunityId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['assessment', opportunityId] })
      void client.invalidateQueries({ queryKey: ['inbox'] })
      void client.invalidateQueries({ queryKey: ['overview'] })
      void client.invalidateQueries({ queryKey: ['saved-searches'] })
    },
  })
}
