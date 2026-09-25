import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getOpportunity, markRelevance } from './api'

export function useOpportunity(opportunityId: string) {
  return useQuery({
    queryKey: ['opportunity', opportunityId],
    queryFn: () => getOpportunity(opportunityId),
  })
}

export function useMarkRelevance(opportunityId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: { relevant: boolean; reason?: string | null }) =>
      markRelevance(opportunityId, input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['opportunity', opportunityId] })
      void client.invalidateQueries({ queryKey: ['inbox'] })
    },
  })
}
