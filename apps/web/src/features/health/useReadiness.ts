import { useQuery } from '@tanstack/react-query'
import { getReadiness } from './api'

export function useReadiness() {
  return useQuery({
    queryKey: ['health', 'ready'],
    queryFn: getReadiness,
    staleTime: 30_000,
  })
}
