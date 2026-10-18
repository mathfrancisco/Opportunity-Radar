import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { queryStaleTimes } from '../../lib/queryClient'
import {
  getApplicationForOpportunity,
  listApplications,
  setNextAction,
  startApplication,
  transitionApplication,
} from './api'

export function useApplications(
  params: { status?: string; stage?: string; opportunityId?: string; offset?: number; limit?: number } = {},
  enabled = true,
) {
  return useQuery({
    queryKey: ['applications', params],
    queryFn: ({ signal }) => listApplications(params, signal),
    enabled,
    staleTime: queryStaleTimes.standard,
  })
}

export function useOpportunityApplication(opportunityId: string) {
  return useQuery({
    queryKey: ['application', 'opportunity', opportunityId],
    queryFn: ({ signal }) => getApplicationForOpportunity(opportunityId, signal),
    staleTime: queryStaleTimes.standard,
  })
}

function useApplicationMutation<TInput>(
  opportunityId: string | null,
  mutationFn: (input: TInput) => Promise<unknown>,
) {
  const client = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['applications'] })
      void client.invalidateQueries({ queryKey: ['overview'] })
      void client.invalidateQueries({ queryKey: ['inbox'] })
      void client.invalidateQueries({ queryKey: ['saved-searches'] })
      if (opportunityId !== null) {
        void client.invalidateQueries({
          queryKey: ['application', 'opportunity', opportunityId],
        })
      }
    },
  })
}

export function useStartApplication(opportunityId: string) {
  return useApplicationMutation(opportunityId, startApplication)
}

export function useTransitionApplication(opportunityId: string | null) {
  return useApplicationMutation(opportunityId, transitionApplication)
}

export function useSetNextAction(opportunityId: string | null) {
  return useApplicationMutation(opportunityId, setNextAction)
}
