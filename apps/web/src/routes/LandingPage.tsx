import { Link } from 'react-router-dom'
import { BrandMark } from '../components/ui/BrandMark'

const benefits = [
  ['Inbox com contexto', 'Reúna vagas relevantes e retome a decisão com as informações essenciais à vista.'],
  ['Matching explicável', 'Compare a vaga com critérios do seu perfil e use a IA como apoio consultivo à leitura.'],
  ['Pipeline para agir', 'Acompanhe etapas, próximas ações e candidaturas sem perder o fio da busca.'],
]

const faqs = [
  ['A Bateia envia candidaturas?', 'Não. A plataforma organiza sua busca e ajuda você a decidir a próxima ação; a candidatura continua sob seu controle.'],
  ['Como o matching ajuda na decisão?', 'Ele apresenta critérios do perfil ao lado da vaga. A análise por IA, quando disponível, é um apoio consultivo e não substitui sua avaliação.'],
  ['Posso começar por uma vaga específica?', 'Sim. Ao entrar, você pode usar a inbox, registrar uma candidatura e acompanhar a próxima ação pelo pipeline.'],
]

function ProductPreview() {
  return (
    <section aria-label="Demonstração do produto" className="min-w-0 rounded-panel border border-line bg-surface p-3 sm:p-5" data-testid="product-preview">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-divider pb-4">
        <div>
          <p className="text-caption font-semibold uppercase tracking-[0.12em] text-muted">Visão da semana</p>
          <h2 className="mt-1 text-section">Vagas para decidir</h2>
        </div>
        <span className="rounded-chip border border-line-strong bg-panel px-2 py-1 text-caption text-neutral-ink">Demonstração com dados fictícios</span>
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(12rem,0.72fr)]">
        <div className="min-w-0 rounded-control border border-divider bg-canvas p-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold">Inbox</h3>
            <span className="text-caption text-muted">3 para avaliar</span>
          </div>
          <ul className="mt-3 divide-y divide-divider border-y border-divider bg-surface">
            <li className="flex min-h-16 items-center justify-between gap-3 px-3 py-2">
              <div className="min-w-0"><p className="truncate text-sm font-semibold">Produto · São Paulo</p><p className="text-caption text-muted">Remoto · adicionada hoje</p></div>
              <span className="shrink-0 rounded-chip bg-success-surface px-2 py-1 text-caption font-semibold text-success-ink">Priorizar</span>
            </li>
            <li className="flex min-h-16 items-center justify-between gap-3 px-3 py-2">
              <div className="min-w-0"><p className="truncate text-sm font-semibold">Operações · Brasil</p><p className="text-caption text-muted">Híbrido · revisar contexto</p></div>
              <span className="shrink-0 rounded-chip bg-panel px-2 py-1 text-caption font-semibold text-neutral-ink">Ler</span>
            </li>
          </ul>
        </div>
        <div className="rounded-control border border-divider bg-accent-surface p-3">
          <p className="text-caption font-semibold uppercase tracking-[0.12em] text-accent-ink">Leitura da vaga</p>
          <h3 className="mt-2 text-sm font-semibold">Produto · São Paulo</h3>
          <dl className="mt-4 space-y-3 text-body-sm">
            <div className="flex items-center justify-between gap-3"><dt className="text-subtle">Perfil</dt><dd className="font-semibold text-success-ink">Alinhado</dd></div>
            <div className="flex items-center justify-between gap-3"><dt className="text-subtle">Próxima ação</dt><dd className="font-semibold text-warning-ink">Ler requisitos</dd></div>
            <div className="border-t border-line pt-3"><dt className="text-subtle">Apoio por IA</dt><dd className="mt-1 text-caption text-ink">Resumo consultivo disponível para conferir.</dd></div>
          </dl>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between rounded-control border border-divider bg-panel px-3 py-3 text-body-sm">
        <span className="font-semibold">Pipeline</span>
        <span className="text-subtle">Avaliar <span aria-hidden="true">→</span> Candidatar <span aria-hidden="true">→</span> Acompanhar</span>
      </div>
    </section>
  )
}

export function LandingPage() {
  return (
    <main className="min-h-screen overflow-x-hidden bg-canvas text-ink">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex min-h-16 max-w-7xl items-center justify-between gap-4 px-5 sm:px-8 lg:px-10">
          <Link aria-label="Bateia — início" className="inline-flex min-h-11 min-w-11 items-center" to="/"><BrandMark /></Link>
          <nav aria-label="Navegação da página" className="hidden items-center gap-6 text-sm text-subtle md:flex">
            <a className="hover:text-accent-ink" href="#como-funciona">Como funciona</a>
            <a className="hover:text-accent-ink" href="#recursos">Recursos</a>
            <a className="hover:text-accent-ink" href="#perguntas">Perguntas</a>
          </nav>
          <div className="flex items-center gap-2 sm:gap-3">
            <Link className="inline-flex min-h-11 items-center justify-center rounded-control px-3 text-sm font-semibold text-ink hover:text-accent-ink sm:px-4" to="/sign-in">Entrar</Link>
            <Link className="inline-flex min-h-11 items-center justify-center rounded-control bg-accent px-3 text-sm font-semibold text-surface hover:bg-accent-hover sm:px-4" to="/sign-up">Criar conta</Link>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-10 px-5 py-14 sm:px-8 sm:py-20 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:items-center lg:px-10 lg:py-24">
        <div className="max-w-2xl">
          <p className="text-caption font-semibold uppercase tracking-[0.16em] text-accent-ink">Decisões de carreira, com clareza</p>
          <h1 className="mt-5 max-w-xl text-4xl font-display tracking-tight text-ink sm:text-5xl sm:leading-[1.08]">Menos vagas, cada uma com o porquê.</h1>
          <p className="mt-6 max-w-xl text-body text-subtle">Veja por que cada vaga combina com você, o que falta e o que impede. A leitura da IA apoia, a decisão é sua. Nenhuma empresa vê seu perfil aqui.</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link className="inline-flex min-h-11 items-center justify-center rounded-control bg-accent px-5 text-sm font-semibold text-surface hover:bg-accent-hover" to="/sign-up">Começar a organizar</Link>
            <a className="inline-flex min-h-11 items-center justify-center rounded-control border border-line-strong bg-surface px-5 text-sm font-semibold text-ink hover:border-ink" href="#como-funciona">Ver como funciona</a>
          </div>
          <p className="mt-4 text-body-sm text-muted">Sem automatizar candidaturas. Você mantém o controle de cada decisão.</p>
        </div>
        <ProductPreview />
      </section>

      <section id="recursos" className="border-y border-line bg-surface">
        <div className="mx-auto max-w-7xl px-5 py-14 sm:px-8 lg:px-10">
          <div className="max-w-2xl"><p className="text-caption font-semibold uppercase tracking-[0.16em] text-accent-ink">Uma busca mais intencional</p><h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Menos abas abertas. Mais contexto para decidir.</h2></div>
          <div className="mt-9 grid gap-4 md:grid-cols-3">
            {benefits.map(([title, description]) => <article className="rounded-panel border border-line bg-canvas p-5" key={title}><p className="text-section">{title}</p><p className="mt-3 text-body-sm text-subtle">{description}</p></article>)}
          </div>
        </div>
      </section>

      <section id="como-funciona" className="mx-auto max-w-7xl px-5 py-14 sm:px-8 lg:px-10">
        <div className="grid gap-8 lg:grid-cols-[minmax(0,0.75fr)_minmax(0,1.25fr)]">
          <div><p className="text-caption font-semibold uppercase tracking-[0.16em] text-accent-ink">Do interesse à ação</p><h2 className="mt-3 text-3xl font-semibold tracking-tight">Uma sequência que respeita o seu julgamento.</h2></div>
          <ol className="grid gap-3 sm:grid-cols-3">{['Centralize o que quer avaliar', 'Compare com o seu contexto', 'Defina a próxima ação'].map((step, index) => <li className="rounded-panel border border-line bg-surface p-4" key={step}><span className="text-caption font-semibold text-accent-ink">0{index + 1}</span><p className="mt-5 text-sm font-semibold">{step}</p></li>)}</ol>
        </div>
      </section>

      <section id="perguntas" className="border-y border-line bg-panel">
        <div className="mx-auto grid max-w-7xl gap-8 px-5 py-14 sm:px-8 lg:grid-cols-[minmax(0,0.6fr)_minmax(0,1fr)] lg:px-10">
          <div><p className="text-caption font-semibold uppercase tracking-[0.16em] text-accent-ink">Perguntas frequentes</p><h2 className="mt-3 text-3xl font-semibold tracking-tight">Transparência para começar.</h2></div>
          <div className="divide-y divide-line border-y border-line">{faqs.map(([question, answer]) => <details className="group py-4" key={question}><summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 text-sm font-semibold">{question}<span aria-hidden="true" className="text-lg text-accent-ink group-open:hidden">+</span><span aria-hidden="true" className="hidden text-lg text-accent-ink group-open:block">−</span></summary><p className="pb-2 pr-8 text-body-sm text-subtle">{answer}</p></details>)}</div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-14 sm:px-8 lg:px-10"><div className="rounded-panel bg-ink px-6 py-10 text-surface sm:px-10"><p className="text-caption font-semibold uppercase tracking-[0.16em] text-sidebar">Comece pelo que importa</p><div className="mt-4 flex flex-col justify-between gap-6 md:flex-row md:items-end"><div className="max-w-2xl"><h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">Sua busca pode ter mais critério e menos ruído.</h2><p className="mt-3 text-body-sm text-sidebar">Crie seu espaço de decisão e avance uma próxima ação por vez.</p></div><Link className="inline-flex min-h-11 shrink-0 items-center justify-center rounded-control bg-surface px-5 text-sm font-semibold text-ink hover:bg-panel" to="/sign-up">Criar conta</Link></div></div></section>

      <footer className="border-t border-line bg-surface"><div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-7 text-body-sm text-subtle sm:flex-row sm:items-center sm:justify-between sm:px-8 lg:px-10"><BrandMark /><div className="flex gap-3"><a className="inline-flex min-h-11 items-center px-1 hover:text-accent-ink" href="#recursos">Recursos</a><a className="inline-flex min-h-11 items-center px-1 hover:text-accent-ink" href="#perguntas">Perguntas</a><Link className="inline-flex min-h-11 items-center px-1 hover:text-accent-ink" to="/sign-in">Entrar</Link></div></div></footer>
    </main>
  )
}
