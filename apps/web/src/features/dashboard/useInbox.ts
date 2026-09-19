import { useQuery } from '@tanstack/react-query'
import { getInbox, type InboxParams } from './api'

export function useInbox(params: InboxParams) {
  return useQuery({ queryKey: ['inbox', params], queryFn: () => getInbox(params) })
}
