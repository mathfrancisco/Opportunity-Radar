import type { SavedSearchFilters } from '../features/saved-searches/api'

export const salaryCurrencies = ['BRL', 'USD', 'EUR', 'GBP', 'CAD'] as const
export const salaryPeriods = [
  { value: 'MONTH', label: 'Mês' },
  { value: 'YEAR', label: 'Ano' },
  { value: 'HOUR', label: 'Hora' },
  { value: 'WEEK', label: 'Semana' },
  { value: 'DAY', label: 'Dia' },
] as const
export const defaultSalaryCurrency = 'BRL'
export const defaultSalaryPeriod = 'MONTH'

export function salaryUnit(params: URLSearchParams): { currency: string; period: string } {
  const currency = params.get('salary_currency') ?? ''
  const period = params.get('salary_period') ?? ''
  return {
    currency: (salaryCurrencies as readonly string[]).includes(currency)
      ? currency
      : defaultSalaryCurrency,
    period: salaryPeriods.some((option) => option.value === period) ? period : defaultSalaryPeriod,
  }
}

export function filtersFromParams(params: URLSearchParams): SavedSearchFilters {
  const filters: SavedSearchFilters = {}
  const hasSalary = Boolean(params.get('salary_min') || params.get('salary_max'))
  for (const key of new Set(params.keys())) {
    if (key === 'page' || key === 'size') continue
    // The unit only means something next to a salary bound; the API rejects the pair otherwise.
    if ((key === 'salary_currency' || key === 'salary_period') && !hasSalary) continue
    const values = params.getAll(key)
    filters[key] = values.length > 1 ? values : values[0]
  }
  if (hasSalary) {
    const unit = salaryUnit(params)
    filters.salary_currency = unit.currency
    filters.salary_period = unit.period
  }
  return filters
}
