import { type FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import { type ManualInput, type ManualInputKind } from '../features/sources/api'
import { useManualIntake } from '../features/sources/useSources'
import { Button } from './Button'
import { Field, controlClassName } from './Field'
import { ErrorState } from './states'

/*
 * O contrato aceita até 7 000 000 caracteres de base64 por arquivo, o que dá pouco mais de
 * 5 MB de conteúdo. O limite aparece antes do envio: descobrir depois, pela recusa, é
 * perder o upload inteiro.
 */
const MAX_FILE_BYTES = 5_000_000

interface Entry {
  id: number
  kind: ManualInputKind
  value: string
  file: File | null
  contentType: string
  title: string
  companyName: string
  locationText: string
  skills: string
}

let nextId = 1
function emptyEntry(): Entry {
  return {
    id: nextId++,
    kind: 'URL',
    value: '',
    file: null,
    contentType: '',
    title: '',
    companyName: '',
    locationText: '',
    skills: '',
  }
}

const kindLabels: Record<ManualInputKind, string> = {
  URL: 'Endereço da vaga',
  TEXT: 'Texto da vaga',
  FILE: 'Arquivo',
}

function problemOf(entry: Entry): string | null {
  if (entry.kind === 'FILE') {
    if (!entry.file) return 'Escolha um arquivo.'
    if (entry.file.size > MAX_FILE_BYTES) return 'O arquivo passa de 5 MB, o limite do contrato.'
    return null
  }
  const value = entry.value.trim()
  if (!value) return entry.kind === 'URL' ? 'Cole o endereço da vaga.' : 'Cole o texto da vaga.'
  if (entry.kind === 'URL' && !/^https?:\/\/\S+$/i.test(value)) {
    return 'Use um endereço completo, começando por http:// ou https://.'
  }
  if (entry.kind === 'URL' && value.length > 2048) return 'O endereço passa de 2048 caracteres.'
  if (entry.kind === 'TEXT' && value.length > 2048) {
    return 'O texto passa de 2048 caracteres; envie como arquivo .txt.'
  }
  return null
}

async function toInput(entry: Entry): Promise<ManualInput> {
  const metadata: Record<string, string> = {}
  if (entry.title.trim()) metadata.title = entry.title.trim()
  if (entry.companyName.trim()) metadata.company_name = entry.companyName.trim()
  if (entry.locationText.trim()) metadata.location_text = entry.locationText.trim()
  if (entry.skills.trim()) metadata.skills = entry.skills.trim()
  if (entry.kind !== 'FILE' || !entry.file) {
    return { kind: entry.kind, value: entry.value.trim(), metadata }
  }
  const bytes = new Uint8Array(await entry.file.arrayBuffer())
  let binary = ''
  for (let index = 0; index < bytes.length; index += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000))
  }
  return {
    kind: 'FILE',
    value: entry.file.name,
    contentBase64: btoa(binary),
    contentType: entry.contentType.trim() || entry.file.type || undefined,
    metadata,
  }
}

const outcomeLabels: Record<string, string> = {
  SUCCEEDED: 'Normalizada',
  REVIEW_REQUIRED: 'Normalizada, pede revisão',
  FAILED: 'Falhou na normalização',
}

const decisionLabels: Record<string, string> = {
  NEW: 'oportunidade nova',
  MERGED: 'juntada a uma oportunidade existente',
  REFRESHED: 'atualizou uma oportunidade existente',
  REVIEW: 'identidade ambígua, para revisão',
}

export function ManualIntakePanel({ sourceId }: { sourceId: string }) {
  const [entries, setEntries] = useState<Entry[]>(() => [emptyEntry()])
  const [problems, setProblems] = useState<Record<number, string>>({})
  const intake = useManualIntake(sourceId)

  function change(id: number, patch: Partial<Entry>) {
    setEntries((current) =>
      current.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry)),
    )
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const found: Record<number, string> = {}
    for (const entry of entries) {
      const problem = problemOf(entry)
      if (problem) found[entry.id] = problem
    }
    setProblems(found)
    if (Object.keys(found).length > 0) return
    intake.mutate(await Promise.all(entries.map(toInput)))
  }

  const headingId = `intake-${sourceId}`
  const result = intake.data

  return (
    <section aria-labelledby={headingId} className="mt-4 rounded-2xl border border-line bg-panel p-4">
      <h3 className="font-semibold" id={headingId}>
        Registrar vaga avulsa
      </h3>
      <p className="mt-1 max-w-2xl text-sm text-subtle">
        A vaga entra como qualquer outra coleta: uma execução, a evidência preservada como
        chegou, e depois a normalização. O endereço não é visitado — o que vale é o que você
        enviar aqui.
      </p>

      <form className="mt-4 grid gap-4" noValidate onSubmit={(event) => void submit(event)}>
        {entries.map((entry, index) => (
          <fieldset className="rounded-2xl border border-line bg-surface p-4" key={entry.id}>
            <legend className="px-1 text-sm font-semibold">Vaga {index + 1}</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Forma de entrada">
                <select
                  className={controlClassName}
                  onChange={(event) =>
                    change(entry.id, { kind: event.target.value as ManualInputKind })
                  }
                  value={entry.kind}
                >
                  {(Object.keys(kindLabels) as ManualInputKind[]).map((kind) => (
                    <option key={kind} value={kind}>
                      {kindLabels[kind]}
                    </option>
                  ))}
                </select>
              </Field>
              {entry.kind === 'URL' && (
                <Field error={problems[entry.id]} label="Endereço">
                  <input
                    className={controlClassName}
                    inputMode="url"
                    onChange={(event) => change(entry.id, { value: event.target.value })}
                    placeholder="https://"
                    value={entry.value}
                  />
                </Field>
              )}
              {entry.kind === 'FILE' && (
                <Field
                  error={problems[entry.id]}
                  hint="Até 5 MB. Texto, HTML ou PDF exportado da página da vaga."
                  label="Arquivo"
                >
                  <input
                    className={controlClassName}
                    onChange={(event) =>
                      change(entry.id, { file: event.target.files?.[0] ?? null })
                    }
                    type="file"
                  />
                </Field>
              )}
              {entry.kind === 'TEXT' && (
                <Field className="sm:col-span-2" error={problems[entry.id]} label="Texto">
                  <textarea
                    className={controlClassName}
                    maxLength={2048}
                    onChange={(event) => change(entry.id, { value: event.target.value })}
                    rows={5}
                    value={entry.value}
                  />
                </Field>
              )}
              {entry.kind === 'FILE' && (
                <Field hint="Vazio usa o tipo que o navegador informar." label="Tipo de conteúdo">
                  <input
                    className={controlClassName}
                    onChange={(event) => change(entry.id, { contentType: event.target.value })}
                    placeholder={entry.file?.type || 'text/plain'}
                    value={entry.contentType}
                  />
                </Field>
              )}
              <Field label="Título (opcional)">
                <input
                  className={controlClassName}
                  onChange={(event) => change(entry.id, { title: event.target.value })}
                  value={entry.title}
                />
              </Field>
              <Field label="Empresa (opcional)">
                <input
                  className={controlClassName}
                  onChange={(event) => change(entry.id, { companyName: event.target.value })}
                  value={entry.companyName}
                />
              </Field>
              <Field label="Localidade (opcional)">
                <input
                  className={controlClassName}
                  onChange={(event) => change(entry.id, { locationText: event.target.value })}
                  value={entry.locationText}
                />
              </Field>
              <Field hint="Separadas por vírgula." label="Habilidades (opcional)">
                <input
                  className={controlClassName}
                  onChange={(event) => change(entry.id, { skills: event.target.value })}
                  value={entry.skills}
                />
              </Field>
            </div>
            {entries.length > 1 && (
              <Button
                className="mt-3"
                onClick={() =>
                  setEntries((current) => current.filter((item) => item.id !== entry.id))
                }
                size="sm"
                variant="secondary"
              >
                Remover vaga {index + 1}
              </Button>
            )}
          </fieldset>
        ))}

        {intake.isError && <ErrorState>{intake.error.message}</ErrorState>}

        <div className="flex flex-wrap gap-3">
          <Button disabled={intake.isPending} type="submit">
            {intake.isPending
              ? 'Registrando…'
              : entries.length === 1
                ? 'Registrar vaga'
                : `Registrar ${entries.length} vagas`}
          </Button>
          <Button
            onClick={() => setEntries((current) => [...current, emptyEntry()])}
            variant="secondary"
          >
            Adicionar outra vaga
          </Button>
        </div>
      </form>

      {result && (
        <div className="mt-5" role="status">
          <p className="text-sm">
            Execução {result.run.status}: {result.run.itemsSeen} recebidas,{' '}
            {result.run.itemsPersisted} novas, {result.run.itemsSkipped} repetidas,{' '}
            {result.run.itemsInvalid} inválidas.
          </p>
          {result.run.itemsSkipped > 0 && (
            <p className="mt-2 text-sm text-subtle">
              Repetida quer dizer que a mesma evidência já tinha sido registrada: nada se perdeu,
              e a vaga continua onde a primeira entrada a deixou.
            </p>
          )}
          {result.run.errorSummary && (
            <p className="mt-2 text-sm text-danger-ink">
              {result.run.errorCode}: {result.run.errorSummary}
            </p>
          )}
          {result.items.length > 0 && (
            <ul className="mt-3 grid gap-2">
              {result.items.map((item) => (
                <li
                  className="break-anywhere rounded-2xl border border-line bg-surface p-3 text-sm"
                  key={item.rawItemId}
                >
                  <p className="font-medium">
                    {outcomeLabels[item.status] ?? item.status}
                    {item.identityDecision &&
                      ` — ${decisionLabels[item.identityDecision] ?? item.identityDecision}`}
                  </p>
                  {item.opportunityId ? (
                    <Link
                      className="mt-1 inline-block underline decoration-accent decoration-2 underline-offset-4"
                      to={`/opportunities/${item.opportunityId}`}
                    >
                      {item.opportunityTitle ?? 'Abrir a oportunidade'}
                    </Link>
                  ) : (
                    <p className="mt-1 text-danger-ink">
                      {item.errorSummary ?? 'O domínio não registrou o motivo.'}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
