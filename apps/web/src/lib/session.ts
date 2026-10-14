import { useAuth } from '@clerk/react'
import { useQuery } from '@tanstack/react-query'
import { apiUrl, failureFrom, privateFetch } from './api'

export type SessionCapability = { is_owner: boolean }

async function getSession(): Promise<SessionCapability> {
  const response = await privateFetch(apiUrl('/session'))
  if (!response.ok) throw await failureFrom(response)
  return response.json() as Promise<SessionCapability>
}

export function useSession() {
  const { isSignedIn, userId } = useAuth()
  const identity = isSignedIn === true && userId ? userId : null

  return useQuery({
    queryKey: ['session', identity],
    queryFn: getSession,
    enabled: identity !== null,
  })
}
