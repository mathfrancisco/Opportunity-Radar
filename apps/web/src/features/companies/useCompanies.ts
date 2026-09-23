import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  type CompanyInput,
  type CompanyListParams,
  type CompanySourceInput,
  addCompanySource,
  detectCompanySource,
  getCompanies,
  getCompany,
  registerCompany,
  updateCompany,
  updateCompanySource,
} from './api'

export function useCompanies(params: CompanyListParams) {
  return useQuery({ queryKey: ['companies', params], queryFn: () => getCompanies(params) })
}

export function useCompany(companyId: string) {
  return useQuery({
    queryKey: ['company', companyId],
    queryFn: () => getCompany(companyId),
  })
}

export function useDetectCompanySource(companyId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => detectCompanySource(companyId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['company', companyId] })
      void client.invalidateQueries({ queryKey: ['source-health'] })
      void client.invalidateQueries({ queryKey: ['source-coverage'] })
    },
  })
}

export function useRegisterCompany() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: CompanyInput) => registerCompany(input),
    onSuccess: (result) => {
      client.setQueryData(['company', result.company.id], result.company)
      void client.invalidateQueries({ queryKey: ['companies'] })
      void client.invalidateQueries({ queryKey: ['source-coverage'] })
    },
  })
}

export function useUpdateCompany(companyId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: CompanyInput & { expectedVersion: number }) =>
      updateCompany(companyId, input),
    onSuccess: (company) => {
      client.setQueryData(['company', companyId], company)
      void client.invalidateQueries({ queryKey: ['companies'] })
    },
  })
}

interface SaveCompanySource extends CompanySourceInput {
  /** Null registers a new record; an id corrects that one at the given version. */
  sourceId: string | null
  expectedVersion: number | null
}

export function useSaveCompanySource(companyId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ sourceId, expectedVersion, ...input }: SaveCompanySource) =>
      sourceId === null || expectedVersion === null
        ? addCompanySource(companyId, input)
        : updateCompanySource(companyId, sourceId, { ...input, expectedVersion }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['company', companyId] })
      void client.invalidateQueries({ queryKey: ['companies'] })
      void client.invalidateQueries({ queryKey: ['source-coverage'] })
    },
  })
}
