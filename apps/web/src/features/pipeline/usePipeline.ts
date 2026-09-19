import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getApplicationForOpportunity,
  listApplications,
  setNextAction,
  startApplication,
  transitionApplication,
} from './api'

export function useApplications(params: { status?: string } = {}) {
  return useQuery({
    queryKey: ['applications', params],
    queryFn: () => listApplications(params),
  })
}

export function useOpportunityApplication(opportunityId: string) {
  return useQuery({
    queryKey: ['application', 'opportunity', opportunityId],
    queryFn: () => getApplicationForOpportunity(opportunityId),
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
