import { useQuery } from '@tanstack/react-query'
import { queryStaleTimes } from '../../lib/queryClient'
import { getInbox, getInboxSummary, type InboxParams } from './api'

export function useInbox(params: InboxParams) {
  return useQuery({
    queryKey: ['inbox', params],
    queryFn: ({ signal }) => getInbox(params, signal),
    staleTime: queryStaleTimes.standard,
  })
}

/** Separate from the list: a slow or failing summary never blocks the rows. */
export function useInboxSummary() {
  return useQuery({
    queryKey: ['inbox-summary'],
    queryFn: ({ signal }) => getInboxSummary(signal),
    staleTime: queryStaleTimes.standard,
  })
}
