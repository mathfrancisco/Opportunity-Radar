import { useQuery } from '@tanstack/react-query'
import { queryStaleTimes } from '../../lib/queryClient'
import { getReadiness } from './api'

export function useReadiness() {
  return useQuery({
    queryKey: ['health', 'ready'],
    queryFn: ({ signal }) => getReadiness(signal),
    staleTime: queryStaleTimes.standard,
  })
}
