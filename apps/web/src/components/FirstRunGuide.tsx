import { ButtonLink } from './Button'

const steps = [
  ['Diga o que você procura', 'Cargo, senioridade e regime de trabalho.'],
  ['Diga o que você sabe', 'Skills, nível e tempo de uso.'],
  ['Defina seus limites', 'Salário mínimo e países aceitos. Vaga fora deles perde pontos no match.'],
] as const

/** Shown while there is no active profile: nothing can be matched until the profile exists. */
export function FirstRunGuide() {
  return (
    <section aria-labelledby="first-run-title" className="rounded-panel border border-line bg-surface p-6 sm:p-8">
      <h2 className="font-display text-3xl text-ink" id="first-run-title">Monte sua bateia</h2>
      <p className="mt-3 max-w-xl text-body-sm text-subtle">
        Sem perfil, não há como dizer por que uma vaga combina com você. Três passos e as vagas
        chegam com o porquê.
      </p>
      <ol className="mt-6 grid gap-3 sm:grid-cols-3">
        {steps.map(([title, description], index) => (
          <li className="rounded-control border border-divider bg-canvas p-4" key={title}>
            <span className="text-caption font-semibold text-accent-ink">0{index + 1}</span>
            <p className="mt-3 text-sm font-semibold text-ink">{title}</p>
            <p className="mt-1 text-body-sm text-subtle">{description}</p>
          </li>
        ))}
      </ol>
      <div className="mt-6">
        <ButtonLink to="/profile">Começar pelo perfil</ButtonLink>
      </div>
    </section>
  )
}
