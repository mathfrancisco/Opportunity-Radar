import { useQuery } from '@tanstack/react-query'
import { getCompanies, type CompanyListParams } from './api'

export function useCompanies(params: CompanyListParams) {
  return useQuery({ queryKey: ['companies', params], queryFn: () => getCompanies(params) })
}
