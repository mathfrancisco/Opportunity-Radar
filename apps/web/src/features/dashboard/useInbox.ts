import { useQuery } from '@tanstack/react-query'
import { queryStaleTimes } from '../../lib/queryClient'
import { getInbox, type InboxParams } from './api'

export function useInbox(params: InboxParams) {
  return useQuery({
    queryKey: ['inbox', params],
    queryFn: ({ signal }) => getInbox(params, signal),
    staleTime: queryStaleTimes.standard,
  })
}
