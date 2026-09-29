import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getActiveProfile,
  listProfileVersions,
  saveProfileVersion,
  type ProfileDraft,
} from './api'

export function useActiveProfile() {
  return useQuery({ queryKey: ['profile', 'active'], queryFn: getActiveProfile })
}

export function useProfileVersions() {
  return useQuery({ queryKey: ['profile', 'versions'], queryFn: listProfileVersions })
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
    },
  })
}
