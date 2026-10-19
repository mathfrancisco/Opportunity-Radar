import { useAuth } from '@clerk/react'
import { useQuery } from '@tanstack/react-query'
import { apiUrl, failureFrom, privateFetch } from './api'
import { queryStaleTimes } from './queryClient'

export type SessionCapability = { is_owner: boolean }

async function getSession(signal?: AbortSignal): Promise<SessionCapability> {
  const response = await privateFetch(apiUrl('/session'), { signal })
  if (!response.ok) throw await failureFrom(response)
  return response.json() as Promise<SessionCapability>
}

export function useSession() {
  const { isSignedIn, userId } = useAuth()
  const identity = isSignedIn === true && userId ? userId : null

  return useQuery({
    queryKey: ['session', identity],
    queryFn: ({ signal }) => getSession(signal),
    enabled: identity !== null,
    staleTime: queryStaleTimes.profile,
  })
}
