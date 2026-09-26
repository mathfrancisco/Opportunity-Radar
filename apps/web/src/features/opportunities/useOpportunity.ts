import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  confirmDuplicate,
  getDuplicateCandidates,
  getOpportunity,
  markRelevance,
  rejectDuplicate,
} from './api'

export function useOpportunity(opportunityId: string) {
  return useQuery({
    queryKey: ['opportunity', opportunityId],
    queryFn: () => getOpportunity(opportunityId),
  })
}

export function useMarkRelevance(opportunityId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: { relevant: boolean; reason?: string | null }) =>
      markRelevance(opportunityId, input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['opportunity', opportunityId] })
      void client.invalidateQueries({ queryKey: ['inbox'] })
    },
  })
}

/** F20-26: candidates naming this opportunity, every status included. */
export function useDuplicateCandidates(opportunityId: string) {
  return useQuery({
    queryKey: ['duplicate-candidates', opportunityId],
    queryFn: () => getDuplicateCandidates(opportunityId),
    enabled: opportunityId !== '',
  })
}

function invalidateAfterDuplicateDecision(
  client: ReturnType<typeof useQueryClient>,
  opportunityId: string,
  otherOpportunityId: string,
) {
  void client.invalidateQueries({ queryKey: ['duplicate-candidates', opportunityId] })
  void client.invalidateQueries({ queryKey: ['duplicate-candidates', otherOpportunityId] })
  void client.invalidateQueries({ queryKey: ['opportunity', opportunityId] })
  void client.invalidateQueries({ queryKey: ['opportunity', otherOpportunityId] })
  void client.invalidateQueries({ queryKey: ['inbox'] })
}

export function useConfirmDuplicate(opportunityId: string, otherOpportunityId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: {
      candidateId: string
      expectedVersionSurvivor: number
      expectedVersionAbsorbed: number
      decidedBy: string
    }) =>
      confirmDuplicate(input.candidateId, {
        expectedVersionSurvivor: input.expectedVersionSurvivor,
        expectedVersionAbsorbed: input.expectedVersionAbsorbed,
        decidedBy: input.decidedBy,
      }),
    onSuccess: () =>
      invalidateAfterDuplicateDecision(client, opportunityId, otherOpportunityId),
  })
}

export function useRejectDuplicate(opportunityId: string, otherOpportunityId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: { candidateId: string; decidedBy: string }) =>
      rejectDuplicate(input.candidateId, { decidedBy: input.decidedBy }),
    onSuccess: () =>
      invalidateAfterDuplicateDecision(client, opportunityId, otherOpportunityId),
  })
}
