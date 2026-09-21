import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { analyzeAssessment, evaluateOpportunity, getLatestAssessment } from './api'

export function useLatestAssessment(opportunityId: string) {
  return useQuery({
    queryKey: ['assessment', opportunityId],
    queryFn: () => getLatestAssessment(opportunityId),
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
    },
  })
}
