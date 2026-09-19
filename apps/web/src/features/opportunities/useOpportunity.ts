import { useQuery } from '@tanstack/react-query'
import { getOpportunity } from './api'

export function useOpportunity(opportunityId: string) {
  return useQuery({
    queryKey: ['opportunity', opportunityId],
    queryFn: () => getOpportunity(opportunityId),
  })
}
