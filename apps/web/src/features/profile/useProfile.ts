import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { queryStaleTimes } from '../../lib/queryClient'
import {
  getActiveProfile,
  listProfileVersions,
  saveProfileVersion,
  type ProfileDraft,
} from './api'

export function useActiveProfile() {
  return useQuery({ queryKey: ['profile', 'active'], queryFn: ({ signal }) => getActiveProfile(signal), staleTime: queryStaleTimes.profile })
}

export function useProfileVersions() {
  return useQuery({ queryKey: ['profile', 'versions'], queryFn: ({ signal }) => listProfileVersions(signal), staleTime: queryStaleTimes.profile })
}

export function useSaveProfile() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: {
      draft: ProfileDraft
      expectedProfileVersion: number
      baseVersionId: string | null
    }) => saveProfileVersion(input.draft, input.expectedProfileVersion, input.baseVersionId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['profile'] })
      // A new active version changes every assessment the inbox shows.
      void client.invalidateQueries({ queryKey: ['inbox'] })
      void client.invalidateQueries({ queryKey: ['overview'] })
      void client.invalidateQueries({ queryKey: ['assessment'] })
      void client.invalidateQueries({ queryKey: ['saved-searches'] })
    },
  })
}
