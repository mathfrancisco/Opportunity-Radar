import { afterEach, describe, expect, it, vi } from 'vitest'
import { analyzeAssessment, getLatestAssessment } from './api'

afterEach(() => vi.unstubAllGlobals())

function respond(body: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })),
  )
}

const assessment = {
  id: 'assessment-1',
  opportunity_id: 'opportunity-1',
  opportunity_version: 2,
  profile_version_id: 'profile-1',
  input_hash: 'a'.repeat(64),
  rules_version: 'matching-v1',
  taxonomy_version: 'skills-v1',
  eligibility: 'UNKNOWN',
  eligibility_details: [
    {
      code: 'COUNTRY_ALLOWED',
      result: 'UNKNOWN',
      reason: 'A vaga não declara países permitidos.',
      severity: 'SOFT',
      confidence: '0.500',
      evidence_refs: [],
    },
  ],
  status: 'COMPLETED',
  verdict: 'REVIEW_REQUIRED',
  score: '61.2500',
  confidence: '0.700',
  assessed_at: '2026-09-17T12:00:00Z',
  created_at: '2026-09-17T12:00:00Z',
  factors: [
    {
      factor_code: 'TECHNOLOGY_FIT',
      weight: '0.2500',
      raw_score: '0.8000',
      contribution: '20.0000',
      status: 'KNOWN',
      confidence: '0.900',
      missing_policy: 'NEUTRAL',
      explanation: 'O perfil cobre as tecnologias exigidas.',
      evidence_refs: ['opportunity.skills:python'],
    },
  ],
  analysis: null,
}

describe('getLatestAssessment', () => {
  it('pede apenas a avaliação mais recente da oportunidade', async () => {
    respond({ items: [assessment], total: 1, offset: 0, limit: 1 })

    const result = await getLatestAssessment('opportunity-1')

    expect(fetch).toHaveBeenCalledWith(
      '/api/matches?opportunity_id=opportunity-1&limit=1',
      expect.any(Object),
    )
    expect(result?.verdict).toBe('REVIEW_REQUIRED')
    expect(result?.factors[0].factorCode).toBe('TECHNOLOGY_FIT')
    expect(result?.eligibilityDetails[0].result).toBe('UNKNOWN')
    expect(result?.analysis).toBeNull()
  })

  it('devolve null quando a oportunidade nunca foi avaliada', async () => {
    respond({ items: [], total: 0, offset: 0, limit: 1 })
    await expect(getLatestAssessment('opportunity-1')).resolves.toBeNull()
  })

  it('rejeita respostas sem coleção de itens', async () => {
    respond({ total: 1 })
    await expect(getLatestAssessment('opportunity-1')).rejects.toThrow(
      'avaliações inválida',
    )
  })
})

describe('analyzeAssessment', () => {
  it('envia refresh e devolve a análise degradada como resultado, não como erro', async () => {
    respond({
      id: 'analysis-1',
      assessment_id: 'assessment-1',
      status: 'AI_FAILED',
      failure_code: 'TRANSPORT_ERROR',
      detail: 'could not connect to provider',
      summary: null,
      strengths: [],
      risks: [],
      inferences: [],
      unknowns: [],
      recommended_review: null,
      model_id: null,
      prompt_version: null,
      schema_version: 'analysis-v1',
      cache_key: 'b'.repeat(64),
      analyzed_at: '2026-09-17T12:05:00Z',
      created_at: '2026-09-17T12:05:00Z',
    })

    const analysis = await analyzeAssessment('assessment-1', { refresh: true })

    expect(fetch).toHaveBeenCalledWith(
      '/api/matches/assessment-1/analysis',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ refresh: true }) }),
    )
    expect(analysis.status).toBe('AI_FAILED')
    expect(analysis.failureCode).toBe('TRANSPORT_ERROR')
    expect(analysis.summary).toBeNull()
    // No call reached the model, so there is no cost to show — absent, not zero.
    expect(analysis.metrics).toBeNull()
  })

  it('lê o custo da chamada e mantém ausente o que o servidor não informou', async () => {
    respond({
      id: 'analysis-2',
      assessment_id: 'assessment-1',
      status: 'AI_COMPLETED',
      failure_code: null,
      detail: null,
      summary: 'Boa aderência.',
      strengths: [],
      risks: [],
      inferences: [],
      unknowns: [],
      recommended_review: false,
      model_id: 'qwen3:8b-q4_K_M',
      prompt_version: 'opportunity_analysis/v1',
      schema_version: 'analysis-v1',
      cache_key: 'c'.repeat(64),
      analyzed_at: '2026-09-24T12:05:00Z',
      created_at: '2026-09-24T12:05:00Z',
      metrics: {
        total_ms: 4200,
        load_ms: null,
        prompt_tokens: 1830,
        prompt_eval_ms: 900,
        output_tokens: 212,
        eval_ms: 3100,
      },
    })

    const analysis = await analyzeAssessment('assessment-1', { refresh: false })

    expect(analysis.metrics).toEqual({
      totalMs: 4200,
      loadMs: null,
      promptTokens: 1830,
      outputTokens: 212,
    })
  })

  it('lê afirmações com evidência do analysis-v2 e strings do analysis-v1 na mesma forma', async () => {
    respond({
      id: 'analysis-3',
      assessment_id: 'assessment-1',
      status: 'AI_COMPLETED',
      failure_code: null,
      detail: null,
      summary: 'Vaga backend remota.',
      strengths: [
        { claim: 'Python exigido está no perfil', evidence: 'Required: Python', source: 'posting' },
        'Texto de uma análise antiga',
      ],
      risks: [
        { claim: 'Provavelmente exige plantão', evidence: null, source: null },
        // An inconsistent pair must not be shown as evidence.
        { claim: 'Trecho sem origem', evidence: 'algo', source: 'elsewhere' },
      ],
      inferences: [],
      unknowns: [],
      recommended_review: false,
      model_id: 'qwen3:8b-q4_K_M',
      prompt_version: 'opportunity_analysis/v2',
      schema_version: 'analysis-v2',
      cache_key: 'd'.repeat(64),
      context_refs: [
        { opportunity_id: 'opp-9', decision: 'NOT_RELEVANT', decided_at: null, similarity: 0.82 },
      ],
      analyzed_at: '2026-09-25T12:05:00Z',
      created_at: '2026-09-25T12:05:00Z',
    })

    const analysis = await analyzeAssessment('assessment-1')

    expect(analysis.strengths).toEqual([
      { claim: 'Python exigido está no perfil', evidence: 'Required: Python', source: 'posting' },
      { claim: 'Texto de uma análise antiga', evidence: null, source: null },
    ])
    expect(analysis.risks).toEqual([
      { claim: 'Provavelmente exige plantão', evidence: null, source: null },
      { claim: 'Trecho sem origem', evidence: null, source: null },
    ])
    expect(analysis.contextRefs).toEqual([
      { opportunityId: 'opp-9', decision: 'NOT_RELEVANT', decidedAt: null, similarity: 0.82 },
    ])
  })

  it('explica a análise já em andamento em vez de mostrar o código do conflito', async () => {
    respond(
      { detail: { code: 'analysis_in_progress', message: 'Already being analyzed.' } },
      409,
    )

    await expect(analyzeAssessment('assessment-1')).rejects.toThrow('já está em andamento')
  })
})
