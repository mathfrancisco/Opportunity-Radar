import { describe, expect, it } from 'vitest'
import { type SourceDefinition } from './api'
import { draftFrom, missingForEnable } from './gate'

const external: SourceDefinition = {
  id: 'source-1',
  sourceType: 'greenhouse',
  name: 'Acme',
  enabled: false,
  schedule: null,
  priority: 100,
  configuration: {},
  evidenceStatus: 'confirmed',
  reviewedAt: '2026-09-20T12:00:00Z',
  termsReviewed: false,
  collectorLocalTested: false,
  version: 3,
}

describe('missingForEnable', () => {
  it('lista cada requisito que falta, pelo nome', () => {
    const missing = missingForEnable(external, draftFrom(external))

    expect(missing).toEqual(['termos revisados', 'collector testado localmente'])
  })

  it('libera quando o gate inteiro está satisfeito', () => {
    const draft = { ...draftFrom(external), termsReviewed: true, collectorLocalTested: true }

    expect(missingForEnable(external, draft)).toEqual([])
  })

  it('explica que evidência não confirmada não se resolve pela tela', () => {
    const unverified = { ...external, evidenceStatus: 'ats_identified' }
    const draft = { ...draftFrom(unverified), termsReviewed: true, collectorLocalTested: true }

    const missing = missingForEnable(unverified, draft)
    expect(missing).toHaveLength(1)
    expect(missing[0]).toContain('ats_identified')
  })

  it('pede data de revisão quando nenhuma foi registrada', () => {
    const neverReviewed = { ...external, reviewedAt: null }
    const draft = { ...draftFrom(neverReviewed), termsReviewed: true, collectorLocalTested: true }

    expect(missingForEnable(neverReviewed, draft)).toEqual(['data de revisão'])
  })

  it('não impõe gate à fonte manual', () => {
    const manual = { ...external, sourceType: 'manual', evidenceStatus: 'unverified' }

    expect(missingForEnable(manual, draftFrom(manual))).toEqual([])
  })
})
