import { describe, expect, it } from 'vitest'

import { sourceTypeLabel } from './labels'

describe('sourceTypeLabel', () => {
  it('traduz tipos conhecidos', () => {
    expect(sourceTypeLabel('greenhouse')).toBe('Greenhouse')
  })

  it('não confunde propriedades herdadas com tipos', () => {
    expect(sourceTypeLabel('constructor')).toBe('Tipo não reconhecido')
    expect(sourceTypeLabel('toString')).toBe('Tipo não reconhecido')
  })
})
