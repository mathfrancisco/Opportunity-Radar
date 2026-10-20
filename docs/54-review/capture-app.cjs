'use strict'
/*
 * Visual capture of the real web app (apps/web), brand Bateia.
 *
 *   node docs/54-review/capture-app.cjs mock    # stubbed Clerk + mocked API, full matrix
 *   node docs/54-review/capture-app.cjs clerk   # real @clerk/react on /sign-in and /sign-up only
 *
 * mock : builds apps/web with Vite, replacing @clerk/react and @clerk/localizations with stubs
 *        (signed in or not by a window flag), serves dist on 127.0.0.1 and answers every /api/*
 *        call with synthetic data through page.route. Hosts other than 127.0.0.1 are blocked.
 * clerk: starts `vite` (dev) in apps/web, which loads the publishable key from apps/web/.env.local
 *        by itself. This script never opens, prints or copies that file. It types nothing and
 *        signs nobody in.
 *
 * Output: docs/54-review/screenshots/bateia-final/*.png (git-ignored) and capture-report.json.
 * Playwright comes from tests/e2e/browser (found in this checkout or in the main checkout).
 */
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const http = require('node:http')
const cp = require('node:child_process')

const repo = path.resolve(__dirname, '..', '..')
const webDir = path.join(repo, 'apps', 'web')
const shotsDir = path.join(__dirname, 'screenshots', 'bateia-final')
const reportPath = path.join(__dirname, 'capture-report.json')
const mode = process.argv[2] || 'mock'
const WIDTHS = [320, 375, 768, 1024, 1280, 1440]
const THEMES = ['light', 'dark']

function loadPlaywright() {
  const candidates = [path.join(repo, 'tests', 'e2e', 'browser')]
  try {
    const common = cp
      .execFileSync('git', ['rev-parse', '--git-common-dir'], { cwd: repo, encoding: 'utf8' })
      .trim()
    candidates.push(path.join(path.resolve(repo, common, '..'), 'tests', 'e2e', 'browser'))
  } catch {
    /* not a git checkout */
  }
  for (const dir of candidates) {
    try {
      return require(require.resolve('playwright', { paths: [dir] }))
    } catch {
      /* try next */
    }
  }
  throw new Error('playwright not found under tests/e2e/browser')
}

// ---------- synthetic data ----------
const NOW = Date.now()
const iso = (hoursAgo) => new Date(NOW - hoursAgo * 3_600_000).toISOString()
const ahead = (hours) => new Date(NOW + hours * 3_600_000).toISOString()
const uid = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`

const LONG_TITLE =
  'Engenheira ou Engenheiro de Software Sênior de Plataforma de Dados e Integrações para o Mercado Financeiro Brasileiro com Foco em Confiabilidade e Observabilidade'
const LONG_COMPANY = 'Aurora Soluções Digitais e Infraestrutura de Dados do Brasil Sociedade Anônima'

const PROFILE_VERSION = uid(9001)
const inboxRows = [
  { n: 1, title: LONG_TITLE, company: 0, verdict: 'HIGH_PRIORITY', score: '92.00', factor: 'TECHNOLOGY_FIT', mode: 'REMOTE', seniority: 'SENIOR', dup: true, sibling: 3, strong: 'S24' },
  { n: 2, title: 'Desenvolvedora Backend Python', company: 1, verdict: 'RECOMMENDED', score: '81.50', factor: 'GEOGRAPHY_CONTRACT_FIT', mode: 'HYBRID', seniority: 'MID' },
  { n: 3, title: 'Analista de Dados Pleno', company: 2, verdict: 'REVIEW_REQUIRED', score: '63.00', factor: 'FUTURE_FACTOR_X', mode: 'ONSITE', seniority: 'MID', estimated: true },
  { n: 4, title: 'Engenheiro de Confiabilidade (SRE)', company: 3, verdict: 'WATCHLIST', score: '55.25', factor: null, mode: 'REMOTE', seniority: 'SENIOR' },
  { n: 5, title: 'Estágio em Engenharia de Software', company: 1, verdict: 'LOW_MATCH', score: '31.00', factor: 'RECENCY', mode: 'ONSITE', seniority: 'INTERN' },
  { n: 6, title: 'Gerente de Engenharia', company: 4, verdict: 'INELIGIBLE', score: '12.00', factor: null, mode: 'ONSITE', seniority: 'MANAGER', elig: 'INELIGIBLE' },
  { n: 7, title: 'Pessoa Desenvolvedora Full Stack', company: 5, verdict: null, score: null, factor: null, mode: 'UNKNOWN', seniority: 'UNKNOWN' },
  { n: 8, title: 'Engenheiro de Software Sênior (Go)', company: 0, verdict: 'HIGH_PRIORITY', score: '88.75', factor: 'DOMAIN_EXPERIENCE', mode: 'REMOTE', seniority: 'SENIOR', applied: true },
]

const companies = [
  { id: uid(201), name: LONG_COMPANY, domain: 'aurora-solucoes-digitais-infraestrutura-de-dados.com.br', priority: 'high', status: 'active', verification_state: 'api_json_confirmed' },
  { id: uid(202), name: 'Pinça', domain: 'pinca.example', priority: 'normal', status: 'active', verification_state: 'ats_identified' },
  { id: uid(203), name: 'Quilate Tecnologia', domain: 'quilate.example', priority: 'normal', status: 'paused', verification_state: 'unverified' },
  { id: uid(204), name: 'Bateia Labs', domain: 'bateia-labs.example', priority: 'low', status: 'backlog', verification_state: 'backlog' },
  { id: uid(205), name: 'Cascalho Dados', domain: null, priority: 'high', status: 'active', verification_state: 'ESTADO_INEXISTENTE' },
  { id: uid(206), name: 'Ouro Fino Sistemas', domain: 'ourofino.example', priority: 'normal', status: 'active', verification_state: 'careers_confirmed' },
]
const companyName = (i) => (i === 0 ? LONG_COMPANY : companies[i].name)

const inboxItems = inboxRows.map((r) => ({
  opportunity_id: uid(100 + r.n),
  title: r.title,
  company_id: companies[r.company].id,
  company_name: companyName(r.company),
  company_priority: companies[r.company].priority,
  location: r.mode === 'REMOTE' ? 'Brasil (remoto)' : 'São Paulo, SP',
  work_mode: r.mode,
  seniority: r.seniority,
  contract_type: 'FULL_TIME',
  lifecycle_status: 'ACTIVE',
  role_family: 'SOFTWARE_ENGINEERING',
  published_at: r.estimated ? null : iso(6 + r.n * 20),
  recency_effective_date: iso(6 + r.n * 20),
  date_is_estimated: !!r.estimated,
  recency_basis: r.estimated ? 'first_seen' : 'published',
  opportunity_version: 2,
  assessment_id: r.verdict ? uid(300 + r.n) : null,
  assessment_opportunity_version: r.verdict ? 2 : null,
  assessment_profile_version_id: r.verdict ? PROFILE_VERSION : null,
  current_profile_version_id: PROFILE_VERSION,
  verdict: r.verdict,
  eligibility: r.verdict ? r.elig || 'ELIGIBLE' : null,
  score: r.score,
  confidence: r.verdict ? '0.80' : null,
  rules_version: r.verdict ? 'rules-v3' : null,
  is_stale: r.verdict ? false : null,
  assessed_at: r.verdict ? iso(3) : null,
  analysis_status: r.n === 1 ? 'COMPLETED' : r.n === 3 ? 'FAILED' : null,
  analysis_recommended_review: r.n === 3 ? true : null,
  analysis_summary: r.n === 1 ? 'Boa aderência em plataforma de dados e confiabilidade.' : null,
  top_factor_code: r.factor,
  applied: !!r.applied,
  application_id: r.applied ? uid(500) : null,
  application_stage: r.applied ? 'APPLIED' : null,
  application_next_action_at: r.applied ? ahead(30) : null,
  has_pending_duplicate: !!r.dup,
  startup_strength: r.strong ? 'strong' : null,
  startup_batch: r.strong || null,
  sibling_count: r.sibling || 0,
  salary_match: null,
}))

function opportunityDetail(id) {
  const row = inboxRows.find((r) => uid(100 + r.n) === id)
  if (!row) return null
  return {
    id,
    fingerprint: 'fp-' + row.n,
    fingerprint_version: 'v2',
    title: row.title,
    company_id: companies[row.company].id,
    company_name: companyName(row.company),
    location: inboxItems[row.n - 1].location,
    work_mode: row.mode,
    seniority: row.seniority,
    contract_type: 'FULL_TIME',
    description:
      'Você vai desenhar e operar a plataforma de dados que sustenta os produtos financeiros da empresa. ' +
      'Trabalhamos com Python, Go, PostgreSQL, Kafka e Kubernetes. Esperamos experiência com observabilidade, ' +
      'contratos de dados e boas práticas de confiabilidade.\n\nResponsabilidades\n- Evoluir pipelines de ingestão.\n- Definir SLOs com os times de produto.\n- Participar do plantão em rodízio.\n\n' +
      'EndereçoMuitoLongoSemEspacosParaTestarQuebraDeLinhaEmTelasEstreitas_https://exemplo.example/vagas/engenharia/plataforma-de-dados/12345678901234567890',
    lifecycle_status: 'ACTIVE',
    published_at: inboxItems[row.n - 1].published_at,
    recency_effective_date: inboxItems[row.n - 1].recency_effective_date,
    recency_basis: inboxItems[row.n - 1].recency_basis,
    created_at: iso(200),
    version: 2,
    compensations: [
      { minimum: '12000', maximum: '18000', currency: 'BRL', period: 'MONTH', gross_net: 'GROSS', evidence_text: 'R$ 12.000 a R$ 18.000 por mês', evidence_source: 'description', raw_item_id: uid(700) },
    ],
    skills: [
      { canonical_name: 'python', display_name: 'Python', requirement: 'REQUIRED', taxonomy_version: 'tax-v2', evidence: [] },
      { canonical_name: 'kafka', display_name: 'Kafka', requirement: 'PREFERRED', taxonomy_version: 'tax-v2', evidence: [] },
      { canonical_name: 'kubernetes', display_name: 'Kubernetes', requirement: 'PREFERRED', taxonomy_version: 'tax-v2', evidence: [] },
    ],
    occurrences: [
      { id: uid(710), raw_item_id: uid(700), source_definition_id: uid(401), external_id: 'job-4512', source_url: 'https://boards.example/aurora/jobs/4512', first_seen_at: iso(200), last_seen_at: iso(2), source_published_at: iso(210), payload_retained: true, payload_expired_at: null },
    ],
    normalization_results: [
      { id: uid(720), raw_item_id: uid(700), status: 'NORMALIZED', normalizer_version: 'norm-v4', identity_decision: 'NEW', reasons: [], error_summary: null, processed_at: iso(199) },
    ],
    sibling_locations: row.sibling
      ? [
          { opportunity_id: uid(180), location: 'Rio de Janeiro, RJ', source_url: 'https://boards.example/aurora/jobs/4513' },
          { opportunity_id: uid(181), location: 'Belo Horizonte, MG', source_url: 'https://boards.example/aurora/jobs/4514' },
        ]
      : [],
    relevance_mark: null,
    absence_after_hours: 72,
  }
}

const FACTOR_CODES = ['GEOGRAPHY_CONTRACT_FIT', 'TECHNOLOGY_FIT', 'COMPANY_PRIORITY', 'DOMAIN_EXPERIENCE', 'SENIORITY_SCOPE', 'CONTRACT_COMPENSATION', 'TIMEZONE', 'RECENCY', 'FUTURE_FACTOR_X']
function assessmentFor(oppId) {
  const row = inboxRows.find((r) => uid(100 + r.n) === oppId)
  if (!row || !row.verdict) return null
  return {
    id: uid(300 + row.n),
    opportunity_id: oppId,
    opportunity_version: 2,
    profile_version_id: PROFILE_VERSION,
    rules_version: 'rules-v3',
    taxonomy_version: 'tax-v2',
    input_hash: 'abc123',
    eligibility: row.elig || 'ELIGIBLE',
    eligibility_details: [
      { code: 'COUNTRY_ALLOWED', result: row.elig ? 'FAIL' : 'PASS', reason: row.elig ? 'A vaga exige presença fora dos países aceitos.' : 'País aceito pelo perfil.', severity: row.elig ? 'BLOCKING' : null, confidence: '0.90', evidence_refs: [] },
    ],
    verdict: row.verdict,
    score: row.score,
    confidence: '0.80',
    is_stale: false,
    assessed_at: iso(3),
    factors: FACTOR_CODES.map((code, i) => ({
      factor_code: code,
      weight: '0.125',
      raw_score: String(90 - i * 9),
      contribution: String(11.25 - i),
      status: i === 6 ? 'UNKNOWN' : i === 7 ? 'NOT_MET' : 'MET',
      confidence: '0.80',
      missing_policy: 'NEUTRAL',
      explanation: 'Explicação sintética do fator para conferência visual do layout em telas estreitas.',
      evidence_refs: [],
    })),
    analysis: {
      id: uid(800 + row.n),
      status: row.n === 3 ? 'FAILED' : 'COMPLETED',
      failure_code: row.n === 3 ? 'AI_FAILED' : null,
      detail: row.n === 3 ? 'A IA não respondeu a tempo.' : null,
      summary: 'Boa aderência em dados e confiabilidade; escopo de gestão é incerto.',
      strengths: [
        { claim: 'Experiência com Python e PostgreSQL em produção.', evidence: 'Python, Go, PostgreSQL', source: 'posting' },
        'Atuação anterior em plataforma de dados.',
      ],
      risks: [{ claim: 'Plantão em rodízio pode conflitar com a janela de horário.', evidence: 'Participar do plantão em rodízio.', source: 'posting' }],
      inferences: ['A equipe parece estar em fase de expansão.'],
      unknowns: ['Faixa salarial não confirmada.'],
      recommended_review: false,
      model_id: 'llama-synthetic-70b',
      prompt_version: 'analysis-v2',
      schema_version: 'analysis-v2',
      analyzed_at: iso(3),
      context_refs: [],
      metrics: { total_ms: 2400, load_ms: 10, prompt_tokens: 1800, output_tokens: 420 },
    },
  }
}

const applications = [
  { n: 8, stage: 'APPLIED', next: 'Enviar portfólio', hours: 30 },
  { n: 1, stage: 'INTERESTED', next: null, hours: null },
  { n: 2, stage: 'INTERVIEW', next: 'Preparar entrevista técnica', hours: 5 },
].map((a, i) => ({
  id: uid(500 + i),
  opportunity_id: uid(100 + a.n),
  opportunity_title: inboxRows[a.n - 1].title,
  company_name: companyName(inboxRows[a.n - 1].company),
  profile_version_id: PROFILE_VERSION,
  current_stage: a.stage,
  status: 'ACTIVE',
  outcome: null,
  next_action: a.next,
  next_action_at: a.hours ? ahead(a.hours) : null,
  notes: 'Nota sintética sobre esta candidatura.',
  applied_at: a.stage === 'INTERESTED' ? null : iso(72),
  started_at: iso(100),
  closed_at: null,
  version: 1,
  allowed_transitions: ['SCREENING', 'REJECTED', 'WITHDRAWN'],
  history: [{ id: uid(900 + i), from_stage: null, to_stage: a.stage, reason: null, source: 'MANUAL', notes: null, occurred_at: iso(100) }],
}))

const sources = [
  { n: 1, name: 'Aurora Soluções (Greenhouse)', type: 'greenhouse', enabled: true, evidence: 'confirmed', run: { status: 'SUCCEEDED', seen: 120, persisted: 14, skipped: 100, invalid: 6 } },
  { n: 2, name: 'Pinça (Lever)', type: 'lever', enabled: true, evidence: 'confirmed', run: { status: 'FAILED', seen: 0, persisted: 0, skipped: 0, invalid: 0, code: 'SOURCE_TIMEOUT_X', error: 'A fonte não respondeu em 30 s.' } },
  { n: 3, name: 'Quilate (Ashby)', type: 'ashby', enabled: true, evidence: 'confirmed', run: { status: 'PARTIAL', seen: 80, persisted: 12, skipped: 60, invalid: 8, code: 'PARTIAL_PAGES', error: 'Duas páginas falharam.' } },
  { n: 4, name: 'Bateia Labs (Workday)', type: 'workday', enabled: false, evidence: 'ats_identified', run: null, proposed: true },
  { n: 5, name: 'Cascalho Dados (Ashby)', type: 'ashby', enabled: false, evidence: 'unverified', run: null, proposed: true },
  { n: 6, name: 'Entrada manual', type: 'manual', enabled: true, evidence: 'confirmed', run: { status: 'SUCCEEDED', seen: 3, persisted: 3, skipped: 0, invalid: 0 } },
  { n: 7, name: 'Fonte de tipo novo', type: 'tipo_novo_x', enabled: false, evidence: 'estado_novo', run: { status: 'STATUS_NOVO', seen: 1, persisted: 0, skipped: 1, invalid: 0 } },
]
const sourceId = (n) => uid(400 + n)
const runFor = (s, i) => ({
  id: uid(600 + s.n * 10 + i),
  source_definition_id: sourceId(s.n),
  source_name: s.name,
  execution_trigger: i % 2 ? 'ON_DEMAND' : 'SCHEDULED',
  status: s.run ? s.run.status : 'SUCCEEDED',
  started_at: iso(2 + i * 24),
  finished_at: iso(2 + i * 24 - 0.05),
  items_seen: s.run ? s.run.seen : 0,
  items_persisted: s.run ? s.run.persisted : 0,
  items_skipped: s.run ? s.run.skipped : 0,
  items_invalid: s.run ? s.run.invalid : 0,
  error_code: s.run && s.run.code ? s.run.code : null,
  error_summary: s.run && s.run.error ? s.run.error : null,
  correlation_id: 'corr-' + s.n + '-' + i,
})
const sourceHealth = (s) => ({
  source_definition_id: sourceId(s.n),
  name: s.name,
  source_type: s.type,
  enabled: s.enabled,
  evidence_status: s.evidence,
  terms_reviewed: s.evidence === 'confirmed',
  collector_local_tested: s.evidence === 'confirmed',
  schedule: s.type === 'manual' ? null : '0 */6 * * *',
  version: 3,
  last_run_id: s.run ? uid(600 + s.n * 10) : null,
  last_run_status: s.run ? s.run.status : null,
  last_run_started_at: s.run ? iso(2) : null,
  last_run_finished_at: s.run ? iso(1.95) : null,
  last_run_duration_seconds: s.run ? 42 : null,
  last_run_error_code: s.run && s.run.code ? s.run.code : null,
  last_run_error: s.run && s.run.error ? s.run.error : null,
  last_run_items_seen: s.run ? s.run.seen : null,
  last_run_items_persisted: s.run ? s.run.persisted : null,
  last_run_items_skipped: s.run ? s.run.skipped : null,
  last_run_items_invalid: s.run ? s.run.invalid : null,
  seniority_counts: s.run ? { SENIOR: 6, MID: 5, UNKNOWN: 3 } : {},
})
const sourceDefinition = (s) => ({
  id: sourceId(s.n),
  source_type: s.type,
  name: s.name,
  enabled: s.enabled,
  schedule: s.type === 'manual' ? null : '0 */6 * * *',
  priority: 50,
  configuration: s.type === 'manual' ? {} : { board_token: 'aurora-sintetico' },
  evidence_status: s.evidence,
  reviewed_at: s.evidence === 'confirmed' ? iso(240) : null,
  terms_reviewed: s.evidence === 'confirmed',
  collector_local_tested: s.evidence === 'confirmed',
  version: 3,
})

function companyDetail(id) {
  const c = companies.find((x) => x.id === id)
  if (!c) return null
  return {
    id: c.id,
    name: c.name,
    domain: c.domain,
    priority: c.priority,
    status: c.status,
    verification_state: c.verification_state,
    aliases: [{ alias: 'Aurora Dados' }, { alias: 'Aurora S.A.' }],
    version: 4,
    sources: [
      {
        id: sourceId(1),
        name: 'Aurora Soluções (Greenhouse)',
        url: 'https://boards.greenhouse.io/aurora-sintetico',
        status: 'confirmed',
        external_key: 'aurora-sintetico',
        verification_method: 'api_json',
        evidence: 'Quadro público respondeu JSON com 120 vagas.',
        last_verified_at: iso(240),
        version: 2,
        revisions: [{ version: 2, changed_at: iso(300), changes: { external_key: { from: 'aurora', to: 'aurora-sintetico' } }, evidence_note: 'Chave corrigida após conferência.' }],
        proposal: { source_id: sourceId(1), source_type: 'greenhouse', external_key: 'aurora-sintetico', enabled: true, evidence_status: 'confirmed', terms_reviewed: true, collector_local_tested: true, version: 3, outdated: false },
      },
    ],
  }
}

const profile = {
  id: PROFILE_VERSION,
  number: 4,
  status: 'ACTIVE',
  profile_lock_version: 7,
  skills: [
    { canonical_name: 'Python', level: 'ADVANCED', last_used_at: '2026-09-30', experience_months: 96 },
    { canonical_name: 'PostgreSQL', level: 'ADVANCED', last_used_at: '2026-09-30', experience_months: 84 },
    { canonical_name: 'Kubernetes', level: 'INTERMEDIATE', last_used_at: '2026-06-01', experience_months: 30 },
  ],
  experiences: [
    { company_name: LONG_COMPANY, title: 'Engenheira de Software Sênior', started_on: '2022-03-01', ended_on: null, summary: 'Plataforma de dados e confiabilidade para produtos financeiros.' },
    { company_name: 'Quilate Tecnologia', title: 'Desenvolvedora Backend', started_on: '2018-01-01', ended_on: '2022-02-28', summary: null },
  ],
  projects: [{ name: 'Radar de vagas', started_on: '2025-01-01', ended_on: null, description: 'Projeto pessoal de acompanhamento de vagas.', url: 'https://exemplo.example/radar' }],
  preferences: {
    work_modes: ['REMOTE', 'HYBRID'],
    contracts: ['FULL_TIME'],
    countries: ['BR', 'PT'],
    timezone_start_hour: 9,
    timezone_end_hour: 18,
    compensation_min: '12000',
    compensation_max: null,
    compensation_currency: 'BRL',
    compensation_period: 'MONTH',
    relocation_allowed: false,
    sponsorship_required: false,
    target_role_families: ['SOFTWARE_ENGINEERING', 'DATA'],
    target_titles: ['Engenheira de Software', 'Engenheira de Dados'],
    accepted_seniorities: ['MID', 'SENIOR', 'STAFF'],
  },
}

const overview = {
  opportunities_total: 1240,
  opportunities_active: 860,
  new_opportunities: 37,
  new_opportunity_window_days: 7,
  assessed_opportunities: 640,
  verdict_counts: { HIGH_PRIORITY: 12, RECOMMENDED: 48, REVIEW_REQUIRED: 20, WATCHLIST: 90, LOW_MATCH: 400, INELIGIBLE: 70 },
  analyses_degraded: 3,
  sources_total: 7,
  sources_enabled: 4,
  sources_failing: 2,
  failing_sources: [
    { source_definition_id: sourceId(2), name: 'Pinça (Lever)', source_type: 'lever', enabled: true, last_run_status: 'FAILED', last_run_finished_at: iso(2), last_run_error: 'A fonte não respondeu em 30 s.' },
    { source_definition_id: sourceId(3), name: 'Quilate (Ashby)', source_type: 'ashby', enabled: true, last_run_status: 'PARTIAL', last_run_finished_at: iso(3), last_run_error: 'Duas páginas falharam.' },
  ],
  pending_normalizations: 5,
  applications_active: 3,
  applications_by_stage: { INTERESTED: 1, APPLIED: 1, INTERVIEW: 1 },
  follow_ups_due: 1,
  follow_up_window_days: 3,
  precision_percent: '72.5',
  precision_marked_count: 40,
  companies_covered: 6,
  companies_with_ats: 4,
}

const sourceMetricsWindow = (w, hours) => ({
  window: w,
  since: iso(hours),
  until: iso(0),
  sources: sources
    .filter((s) => s.enabled)
    .map((s) => ({
      source_definition_id: sourceId(s.n),
      name: s.name,
      source_type: s.type,
      enabled: true,
      schedule: '0 */6 * * *',
      coverage_state: s.run ? (s.run.status === 'SUCCEEDED' ? 'SUCCEEDED' : s.run.status === 'FAILED' ? 'FAILED' : 'PARTIAL') : 'NOT_RUN',
      runs: 4,
      runs_succeeded: s.run && s.run.status === 'SUCCEEDED' ? 4 : 2,
      runs_partial: s.run && s.run.status === 'PARTIAL' ? 2 : 0,
      runs_failed: s.run && s.run.status === 'FAILED' ? 2 : 0,
      items_seen: 120,
      items_persisted: 14,
      items_skipped: 100,
      items_invalid: 6,
      latency_p95_seconds: 41.2,
      error_rate: s.run && s.run.status === 'FAILED' ? 0.5 : 0,
      dedupe_rate: 0.83,
      has_runs: true,
      errors_by_code: s.run && s.run.code ? { [s.run.code]: 2 } : {},
      seniority: { counts: { SENIOR: 6, MID: 5, UNKNOWN: 3 }, percentages: { SENIOR: 42.9, MID: 35.7, UNKNOWN: 21.4 }, known: 11, unknown: 3, total: 14, mapping_versions: { 'seniority-v2': 14 }, evidence: { title: 11 } },
      incident_open: !!(s.run && s.run.status === 'FAILED'),
    })),
})

const analysisMetrics = {
  generated_at: iso(0),
  current_model: 'llama-synthetic-70b',
  pending: 4,
  windows: ['24h', '7d'].map((w, i) => ({
    window: w,
    since: iso(i ? 168 : 24),
    until: iso(0),
    models: [
      { model_id: 'llama-synthetic-70b', analyses: 60, completed: 55, failed: 5, total_ms_p50: 2100, total_ms_p95: 5200, total_ms_p99: 8100, prompt_tokens_avg: 1800, output_tokens_avg: 420, load_ms_avg: 12, failure_rate: 0.083, failure_rates: { AI_FAILED: 0.05, SCHEMA_INVALID: 0.033 }, reuse_rate: 0.2 },
    ],
  })),
  ai: {
    state: 'enabled',
    window_hours: 24,
    by_model: [
      { model: 'llama-synthetic-70b', requests: 110, success_rate: 0.93, rate_limited_rate: 0.02, fallback_rate: 0.1, latency_ms_avg: 2300, latency_ms_p95: 5200, prompt_tokens: 198000, completion_tokens: 46000, json_valid_rate: 0.97, breaker: 'closed', day_requests_used: 110, day_requests_limit: 1000, day_tokens_used: 244000, day_tokens_limit: 500000 },
      { model: 'fallback-synthetic-8b', requests: 12, success_rate: 0.75, rate_limited_rate: 0.1, fallback_rate: 0, latency_ms_avg: 900, latency_ms_p95: 1800, prompt_tokens: 20000, completion_tokens: 4000, json_valid_rate: 0.9, breaker: 'open', day_requests_used: 12, day_requests_limit: null, day_tokens_used: 24000, day_tokens_limit: null },
    ],
    cache_hit_rate: 0.31,
    by_task: [{ task: 'analysis', jobs: 60, cache_hits: 18, requests: 90, tokens: 244000, avg_tokens_per_job: 4066, avg_requests_per_job: 1.5, fallback_jobs: 6, fallback_rate: 0.1 }],
  },
}

const aiBudget = {
  state: 'enabled',
  day: new Date(NOW).toISOString().slice(0, 10),
  resets_at: ahead(9),
  interactive_reserve_requests: 50,
  models: [
    { model: 'llama-synthetic-70b', provider_requests_limit: 1000, requests_soft_limit: 900, requests_used: 110, requests_remaining: 890, requests_remaining_operational: 790, tokens_limit: 500000, tokens_used: 244000, tokens_remaining: 256000 },
    { model: 'fallback-synthetic-8b', provider_requests_limit: null, requests_soft_limit: 500, requests_used: 12, requests_remaining: null, requests_remaining_operational: 488, tokens_limit: 200000, tokens_used: 24000, tokens_remaining: 176000 },
  ],
}

const savedSearches = [
  { id: uid(1001), name: 'Backend remoto sênior', term: 'backend', filters: { work_mode: 'REMOTE', seniority: ['SENIOR'] }, last_opened_at: iso(48), created_at: iso(500), new_count: 5 },
  { id: uid(1002), name: 'Dados em empresa com um nome de busca salva muito longo para testar quebra', term: null, filters: { role_family: ['DATA'] }, last_opened_at: null, created_at: iso(400), new_count: 0 },
]

const profileSuggestions = {
  min_marks: 2,
  suggestions: [
    { kind: 'REMOVE_SENIORITY', value: 'STAFF', marks: 3 },
    { kind: 'LOWER_COMPANY_PRIORITY', value: 'Pinça', marks: 2 },
  ],
}

// ---------- API mock ----------
function apiResponse(method, url) {
  const p = url.pathname.replace(/^\/api/, '')
  const q = url.searchParams
  if (p === '/session') return { is_owner: true }
  if (p === '/health/ready') return { status: 'ready' }
  if (p === '/health') return { ai: { status: 'healthy' }, status: 'ok' }
  if (p === '/overview') return overview
  if (p === '/inbox/summary')
    return { worth_count: 4, collected_count: 37, since: iso(18), next_collection_at: ahead(2.2), generated_at: iso(0) }
  if (p === '/inbox') {
    const company = q.get('company_id')
    const items = company ? inboxItems.filter((i) => i.company_id === company).slice(0, 5) : inboxItems
    return { items, total: items.length, offset: 0, limit: Number(q.get('limit') || 25), off_filter_count: 12 }
  }
  if (p === '/source-metrics') return { generated_at: iso(0), windows: [sourceMetricsWindow('24h', 24), sourceMetricsWindow('7d', 168)] }
  if (p === '/analysis-metrics') return analysisMetrics
  if (p === '/ai-budget') return aiBudget
  if (p === '/saved-searches/summary') return savedSearches
  if (p === '/saved-searches') return savedSearches
  let m
  if ((m = p.match(/^\/saved-searches\/([^/]+)\/new-count$/))) return { new_count: 3 }
  if ((m = p.match(/^\/opportunities\/([^/]+)\/duplicate-candidates$/))) {
    return {
      items: [
        { id: uid(1100), opportunity_id: m[1], duplicate_opportunity_id: uid(104), survivor_opportunity_id: m[1], absorbed_opportunity_id: uid(104), rule: 'title_location_window', score: '0.93', status: 'PENDING', decided_by: null, decided_at: null, created_at: iso(10) },
      ].filter(() => m[1] === uid(101)),
    }
  }
  if ((m = p.match(/^\/opportunities\/([^/]+)$/))) return opportunityDetail(m[1])
  if (p === '/matches') {
    const a = assessmentFor(q.get('opportunity_id'))
    return { items: a ? [a] : [], total: a ? 1 : 0 }
  }
  if (p === '/applications') {
    const opp = q.get('opportunity_id')
    const items = opp ? applications.filter((a) => a.opportunity_id === opp) : applications
    return { items, total: items.length, offset: 0, limit: Number(q.get('limit') || 100) }
  }
  if (p === '/companies') return { items: companies.map((c, i) => (i < 3 ? { ...c, sources: [{ id: sourceId(i + 1), name: sources[i].name, url: 'https://boards.example/' + i, status: i === 0 ? 'confirmed' : 'proposed' }] } : c)), page: 1, page_size: Number(q.get('page_size') || 20), total: companies.length }
  if ((m = p.match(/^\/companies\/([^/]+)$/))) return companyDetail(m[1])
  if (p === '/source-health') {
    const list = sources.filter((s) => (q.get('status') === 'proposed' ? s.proposed : true))
    return { items: list.map(sourceHealth), total: list.length, failing: 2 }
  }
  if (p === '/source-coverage')
    return { catalog_companies: 6, catalog_source_records: 7, proposed_sources: 2, homologated_sources: 4, enabled_sources: 4, eligible_sources: 5 }
  if (p === '/source-runs') {
    const s = sources.find((x) => sourceId(x.n) === q.get('source_id')) || sources[0]
    return { items: [0, 1, 2].map((i) => runFor(s, i)), total: 3, page: 1, page_size: 10 }
  }
  if ((m = p.match(/^\/sources\/([^/]+)$/))) {
    const s = sources.find((x) => sourceId(x.n) === m[1])
    return s ? sourceDefinition(s) : null
  }
  if (p === '/profile') return profile
  if (p === '/profile/versions') return [profile, { ...profile, id: uid(9000), number: 3, status: 'ARCHIVED', profile_lock_version: 6 }]
  if (p === '/profile/suggestions') return profileSuggestions
  return undefined
}

// ---------- build + serve (mock) ----------
const STUB_AUTH = `import React from 'react'
const getToken = async () => (window.__CAPTURE_SIGNED_IN__ ? 'capture-token' : null)
export function ClerkProvider({ children }) { return children }
export function useAuth() {
  const s = !!window.__CAPTURE_SIGNED_IN__
  return { isLoaded: true, isSignedIn: s, userId: s ? 'user_capture' : null, getToken }
}
export function SignIn() { return React.createElement('div', { 'data-stub': 'sign-in', style: { padding: 24, border: '1px dashed currentColor' } }, 'Clerk (stub) entrar') }
export function SignUp() { return React.createElement('div', { 'data-stub': 'sign-up', style: { padding: 24, border: '1px dashed currentColor' } }, 'Clerk (stub) criar conta') }
export function Show({ when, children }) { const s = !!window.__CAPTURE_SIGNED_IN__; return (when === 'signed-in') === s ? children : null }
export function UserButton() { return React.createElement('button', { type: 'button', 'aria-label': 'Conta' }, 'U') }
`
const STUB_LOC = 'export const ptBR = {}\n'

function build() {
  const stubDir = path.join(webDir, '.capture-stubs')
  const dist = path.join(os.tmpdir(), 'bateia-capture-dist')
  const envDir = path.join(os.tmpdir(), 'bateia-capture-env')
  fs.mkdirSync(stubDir, { recursive: true })
  fs.mkdirSync(envDir, { recursive: true })
  fs.writeFileSync(path.join(stubDir, 'clerk-react.js'), STUB_AUTH)
  fs.writeFileSync(path.join(stubDir, 'clerk-localizations.js'), STUB_LOC)
  const cfg = path.join(webDir, 'vite.capture.config.mjs')
  const j = (s) => JSON.stringify(s.replace(/\\/g, '/'))
  fs.writeFileSync(
    cfg,
    `import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
export default defineConfig({
  root: ${j(webDir)},
  envDir: ${j(envDir)},
  plugins: [react(), tailwindcss()],
  resolve: { alias: [
    { find: /^@clerk\\/react$/, replacement: ${j(path.join(stubDir, 'clerk-react.js'))} },
    { find: /^@clerk\\/localizations$/, replacement: ${j(path.join(stubDir, 'clerk-localizations.js'))} },
  ] },
  build: { outDir: ${j(dist)}, emptyOutDir: true },
})
`,
  )
  try {
    cp.execFileSync(process.execPath, [path.join(webDir, 'node_modules', 'vite', 'bin', 'vite.js'), 'build', '--config', cfg], {
      cwd: webDir,
      stdio: 'inherit',
      env: { ...process.env, VITE_CLERK_PUBLISHABLE_KEY: 'pk_test_stub', VITE_API_BASE_URL: '/api' },
    })
  } finally {
    fs.rmSync(cfg, { force: true })
    fs.rmSync(stubDir, { recursive: true, force: true })
  }
  return dist
}

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.png': 'image/png', '.json': 'application/json', '.webmanifest': 'application/manifest+json', '.ico': 'image/x-icon' }
function serve(dist) {
  const server = http.createServer((req, res) => {
    const pathname = decodeURIComponent(new URL(req.url, 'http://x').pathname)
    let file = path.join(dist, pathname)
    if (!file.startsWith(dist) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(dist, 'index.html')
    res.writeHead(200, { 'content-type': MIME[path.extname(file)] || 'application/octet-stream' })
    fs.createReadStream(file).pipe(res)
  })
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)))
}

// ---------- matrix ----------
const ROUTES = [
  { key: 'landing', path: '/', signedIn: false },
  { key: 'sign-in', path: '/sign-in', signedIn: false },
  { key: 'sign-up', path: '/sign-up', signedIn: false },
  { key: 'visao-geral', path: '/', signedIn: true },
  { key: 'inbox', path: '/inbox', signedIn: true },
  { key: 'detalhe-vaga', path: `/opportunities/${uid(101)}`, signedIn: true },
  { key: 'pipeline', path: '/applications', signedIn: true },
  { key: 'perfil', path: '/profile', signedIn: true },
  { key: 'empresas', path: '/companies', signedIn: true },
  { key: 'detalhe-empresa', path: `/companies/${uid(201)}`, signedIn: true },
  { key: 'fontes', path: '/sources', signedIn: true },
  { key: 'homologacao', path: '/sources/homologation-queue', signedIn: true },
  { key: 'status', path: '/status', signedIn: true },
]

async function runMock(chromium) {
  const dist = build()
  const server = await serve(dist)
  const origin = `http://127.0.0.1:${server.address().port}`
  fs.mkdirSync(shotsDir, { recursive: true })
  const browser = await chromium.launch()
  const rows = []
  const unmocked = new Set()
  const blocked = new Set()
  for (const theme of THEMES) {
    for (const width of WIDTHS) {
      for (const signedIn of [false, true]) {
        const routes = ROUTES.filter((r) => r.signedIn === signedIn)
        const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: theme })
        await context.addInitScript(
          ([t, s]) => {
            try { localStorage.setItem('bateia-theme', t) } catch { /* ignore */ }
            window.__CAPTURE_SIGNED_IN__ = s
          },
          [theme, signedIn],
        )
        await context.route('**/*', async (route) => {
          const url = new URL(route.request().url())
          if (url.hostname !== '127.0.0.1') {
            blocked.add(url.host)
            return route.abort()
          }
          if (url.pathname.startsWith('/api/')) {
            const body = apiResponse(route.request().method(), url)
            if (body === undefined || body === null) {
              if (body === undefined) unmocked.add(`${route.request().method()} ${url.pathname}`)
              return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not mocked"}' })
            }
            return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
          }
          return route.continue()
        })
        for (const r of routes) {
          const page = await context.newPage()
          const consoleErrors = []
          const pageErrors = []
          page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 300)) })
          page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 300)))
          await page.goto(origin + r.path, { waitUntil: 'load' })
          await page.waitForLoadState('networkidle')
          await page.waitForTimeout(500)
          const m = await page.evaluate(() => ({
            theme: document.documentElement.getAttribute('data-theme'),
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
            path: location.pathname,
            h1: document.querySelector('h1')?.textContent?.slice(0, 80) ?? null,
            errorText: /Não foi possível|não encontrada|Configuração de autenticação/i.test(document.body.innerText),
            pending: /Verificando sessão|Carregando/i.test(document.body.innerText),
          }))
          const file = `${r.key}-${theme}-${width}.png`
          await page.screenshot({ path: path.join(shotsDir, file), fullPage: true })
          rows.push({
            route: r.key, theme, width, file,
            dataTheme: m.theme, themeOk: m.theme === theme,
            overflow: m.scrollWidth > m.clientWidth, scrollWidth: m.scrollWidth, clientWidth: m.clientWidth,
            landedOn: m.path, h1: m.h1, errorText: m.errorText, pending: m.pending,
            consoleErrors, pageErrors,
          })
          await page.close()
        }
        await context.close()
      }
    }
  }
  await browser.close()
  server.close()
  return { rows, unmocked: [...unmocked], blockedHosts: [...blocked] }
}

// ---------- Clerk real ----------
async function runClerk(chromium) {
  const port = 5199
  // A linked worktree has no apps/web/.env.local (it is git-ignored). Point Vite's envDir at the
  // main checkout's apps/web so Vite loads the key itself; this script never reads that file.
  let envDir = webDir
  if (!fs.existsSync(path.join(webDir, '.env.local'))) {
    const common = cp.execFileSync('git', ['rev-parse', '--git-common-dir'], { cwd: repo, encoding: 'utf8' }).trim()
    envDir = path.join(path.resolve(repo, common, '..'), 'apps', 'web')
  }
  const cfg = path.join(webDir, 'vite.capture-clerk.config.mjs')
  fs.writeFileSync(
    cfg,
    `import { defineConfig, mergeConfig } from 'vite'
import base from './vite.config.ts'
export default defineConfig((env) => mergeConfig(typeof base === 'function' ? base(env) : base, { envDir: ${JSON.stringify(envDir.split(path.sep).join('/'))} }))
`,
  )
  const vite = cp.spawn(process.execPath, [path.join(webDir, 'node_modules', 'vite', 'bin', 'vite.js'), '--config', cfg, '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
    cwd: webDir, stdio: ['ignore', 'pipe', 'pipe'],
  })
  let log = ''
  vite.stdout.on('data', (d) => { log += d })
  vite.stderr.on('data', (d) => { log += d })
  const origin = `http://127.0.0.1:${port}`
  for (let i = 0; i < 60; i++) {
    try { await new Promise((ok, no) => http.get(origin, (r) => { r.resume(); ok() }).on('error', no)); break } catch { await new Promise((r) => setTimeout(r, 500)) }
  }
  fs.mkdirSync(shotsDir, { recursive: true })
  const browser = await chromium.launch()
  const rows = []
  const hosts = new Set()
  try {
    for (const theme of THEMES) {
      for (const width of [320, 1440]) {
        const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: theme })
        await context.addInitScript((t) => { try { localStorage.setItem('bateia-theme', t) } catch { /* ignore */ } }, theme)
        for (const kind of ['sign-in', 'sign-up']) {
          const page = await context.newPage()
          const consoleErrors = []
          const pageErrors = []
          const failed = []
          page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 300)) })
          page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 300)))
          page.on('requestfailed', (rq) => failed.push(new URL(rq.url()).host.replace(/^[^.]+(\.clerk\.accounts\.dev)$/, '<instance>$1')))
          page.on('request', (rq) => { try { hosts.add(new URL(rq.url()).host.replace(/^[^.]+(\.clerk\.accounts\.dev)$/, '<instance>$1')) } catch { /* ignore */ } })
          await page.goto(`${origin}/${kind}`, { waitUntil: 'load' })
          let rendered = true
          try { await page.waitForSelector('.cl-rootBox, .cl-card, [class*="cl-"]', { timeout: 15000 }) } catch { rendered = false }
          await page.waitForLoadState('networkidle').catch(() => {})
          await page.waitForTimeout(800)
          const m = await page.evaluate(() => {
            const rgb = (v) => { const p = document.createElement('i'); p.style.color = v; document.body.appendChild(p); const c = getComputedStyle(p).color; p.remove(); return c }
            const bg = (v) => { const p = document.createElement('i'); p.style.backgroundColor = v; document.body.appendChild(p); const c = getComputedStyle(p).backgroundColor; p.remove(); return c }
            const first = (sel) => document.querySelector(sel)
            const colorOf = (el, prop) => (el ? getComputedStyle(el)[prop] : null)
            const card = first('.cl-card')
            const primary = first('.cl-formButtonPrimary')
            const title = first('.cl-headerTitle')
            const input = first('.cl-formFieldInput')
            const danger = [...document.querySelectorAll('.cl-formFieldErrorText, .cl-alert, [class*="danger"], [class*="Error"]')].filter((e) => e.offsetParent !== null)
            return {
              theme: document.documentElement.getAttribute('data-theme'),
              clerkNodes: document.querySelectorAll('[class*="cl-"]').length,
              scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth,
              probe: {
                card: card ? { bg: colorOf(card, 'backgroundColor'), token: bg('var(--color-surface)') } : null,
                primary: primary ? { bg: colorOf(primary, 'backgroundColor'), token: bg('var(--color-accent)'), fg: colorOf(primary, 'color'), fgToken: rgb('var(--color-surface)') } : null,
                title: title ? { color: colorOf(title, 'color'), token: rgb('var(--color-ink)') } : null,
                input: input ? { bg: colorOf(input, 'backgroundColor'), token: bg('var(--color-surface)'), color: colorOf(input, 'color'), colorToken: rgb('var(--color-ink)'), border: colorOf(input, 'borderTopColor'), shadow: colorOf(input, 'boxShadow'), bw: colorOf(input, 'borderTopWidth'), borderToken: bg('var(--color-control-line)') } : null,
                cardBox: first('.cl-cardBox') ? { width: first('.cl-cardBox').getBoundingClientRect().width, left: first('.cl-cardBox').getBoundingClientRect().left, right: window.innerWidth - first('.cl-cardBox').getBoundingClientRect().right } : null,
              },
              dangerVisible: danger.length,
              bodyText: document.body.innerText.slice(0, 200),
            }
          })
          const file = `clerk-real-${kind}-${theme}-${width}.png`
          await page.screenshot({ path: path.join(shotsDir, file), fullPage: true })
          rows.push({ route: kind, theme, width, file, rendered, ...m, overflow: m.scrollWidth > m.clientWidth, themeOk: m.theme === theme, consoleErrors, pageErrors, failedHosts: [...new Set(failed)] })
          await page.close()
        }
        await context.close()
      }
    }
  } finally {
    await browser.close()
    vite.kill()
    fs.rmSync(cfg, { force: true })
  }
  return { rows, hosts: [...hosts].sort(), viteLogTail: log.split('\n').filter((l) => /development keys/i.test(l)).slice(-1).map((l) => l.replace(/pk_\w+/g, '<key>').slice(0, 160)) }
}

function summarize(rows) {
  const total = rows.length
  return {
    total,
    overflow: rows.filter((r) => r.overflow).length,
    themeMismatch: rows.filter((r) => r.themeOk === false).length,
    pageErrors: rows.reduce((n, r) => n + r.pageErrors.length, 0),
    consoleErrors: rows.reduce((n, r) => n + r.consoleErrors.length, 0),
    errorTextScreens: [...new Set(rows.filter((r) => r.errorText).map((r) => r.route))],
    pendingScreens: [...new Set(rows.filter((r) => r.pending).map((r) => r.route))],
    redirected: rows.filter((r) => r.landedOn && r.landedOn !== (ROUTES.find((x) => x.key === r.route) || {}).path && !r.landedOn.startsWith('/opportunities') && !r.landedOn.startsWith('/companies/')).map((r) => `${r.route}->${r.landedOn}`).slice(0, 5),
  }
}

;(async () => {
  const { chromium } = loadPlaywright()
  let report = {}
  try { report = JSON.parse(fs.readFileSync(reportPath, 'utf8')) } catch { /* new report */ }
  report.date = new Date().toISOString().slice(0, 10)
  report.head = cp.execFileSync('git', ['rev-parse', '--short', 'HEAD'], { cwd: repo, encoding: 'utf8' }).trim()
  report.branch = cp.execFileSync('git', ['rev-parse', '--abbrev-ref', 'HEAD'], { cwd: repo, encoding: 'utf8' }).trim()
  if (mode === 'mock') {
    const res = await runMock(chromium)
    report.mock = { widths: WIDTHS, themes: THEMES, routes: ROUTES.map((r) => r.key), summary: summarize(res.rows), unmockedRequests: res.unmocked, blockedHosts: res.blockedHosts, rows: res.rows }
    console.log('mock summary', JSON.stringify(report.mock.summary), 'unmocked', res.unmocked, 'blocked', res.blockedHosts)
  } else if (mode === 'clerk') {
    const res = await runClerk(chromium)
    report.clerkReal = { summary: summarize(res.rows), hosts: res.hosts, viteLogTail: res.viteLogTail, rows: res.rows }
    console.log('clerk summary', JSON.stringify(report.clerkReal.summary), 'hosts', res.hosts)
  } else {
    throw new Error('mode must be mock or clerk')
  }
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n')
})().catch((e) => { console.error(e); process.exit(1) })
