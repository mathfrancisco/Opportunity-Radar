import { useQuery } from '@tanstack/react-query'
import { getCompanies, getCompany, type CompanyListParams } from './api'

export function useCompanies(params: CompanyListParams) {
  return useQuery({ queryKey: ['companies', params], queryFn: () => getCompanies(params) })
}

export function useCompany(companyId: string) {
  return useQuery({
    queryKey: ['company', companyId],
    queryFn: () => getCompany(companyId),
  })
}
