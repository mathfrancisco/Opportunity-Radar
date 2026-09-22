import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { detectCompanySource, getCompanies, getCompany, type CompanyListParams } from './api'

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
    onSuccess: () => void client.invalidateQueries({ queryKey: ['company', companyId] }),
  })
}
