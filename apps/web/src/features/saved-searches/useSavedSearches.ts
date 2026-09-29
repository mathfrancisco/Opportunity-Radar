import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  type NewSavedSearch,
  createSavedSearch,
  deleteSavedSearch,
  getSavedSearchNewCount,
  getSavedSearches,
  openSavedSearch,
  renameSavedSearch,
} from './api'

export function useSavedSearches() {
  return useQuery({ queryKey: ['saved-searches'], queryFn: getSavedSearches })
}

export function useSavedSearchNewCount(savedSearchId: string | null) {
  return useQuery({
    queryKey: ['saved-search-new-count', savedSearchId],
    queryFn: () => getSavedSearchNewCount(savedSearchId ?? ''),
    enabled: savedSearchId !== null,
  })
}

function refreshSavedSearches(client: ReturnType<typeof useQueryClient>) {
  void client.invalidateQueries({ queryKey: ['saved-searches'] })
  void client.invalidateQueries({ queryKey: ['overview'] })
}

export function useCreateSavedSearch() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: NewSavedSearch) => createSavedSearch(input),
    onSuccess: () => refreshSavedSearches(client),
  })
}

export function useOpenSavedSearch() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (savedSearchId: string) => openSavedSearch(savedSearchId),
    onSuccess: () => refreshSavedSearches(client),
  })
}

export function useRenameSavedSearch(savedSearchId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => renameSavedSearch(savedSearchId, name),
    onSuccess: () => refreshSavedSearches(client),
  })
}

export function useDeleteSavedSearch() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (savedSearchId: string) => deleteSavedSearch(savedSearchId),
    onSuccess: () => refreshSavedSearches(client),
  })
}
