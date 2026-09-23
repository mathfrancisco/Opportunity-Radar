import { describe, expect, it } from 'vitest'
import { ConflictError, FieldError, failureFrom, requestFailure } from './api'

describe('requestFailure', () => {
  it('marca 409 como conflito, porque repetir a escrita apagaria a outra edição', () => {
    const error = requestFailure(409, 'A candidatura mudou.')

    expect(error).toBeInstanceOf(ConflictError)
    expect(error.message).toBe('A candidatura mudou.')
  })

  it('mantém erro comum para as demais falhas', () => {
    const error = requestFailure(503, null)

    expect(error).not.toBeInstanceOf(ConflictError)
    expect(error.message).toBe('A API respondeu com 503.')
  })

  it('prefere a mensagem do domínio à do status', () => {
    expect(requestFailure(422, 'Fonte externa exige termos revisados.').message).toBe(
      'Fonte externa exige termos revisados.',
    )
  })
})

function reply(body: unknown, status: number) {
  return new Response(JSON.stringify(body), { status })
}

describe('failureFrom', () => {
  it('leva a recusa do domínio ao campo que a causou', async () => {
    const error = await failureFrom(
      reply(
        {
          detail: {
            code: 'INVALID_CONFIGURATION',
            message: 'Greenhouse company_reference must be a non-empty board token',
            field: 'configuration.board_token',
          },
        },
        422,
      ),
    )

    expect(error).toBeInstanceOf(FieldError)
    expect((error as FieldError).field).toBe('configuration.board_token')
    expect(error.message).toContain('board token')
  })

  it('lê a validação do FastAPI pelo mesmo caminho, sem o prefixo body', async () => {
    const error = await failureFrom(
      reply(
        { detail: [{ loc: ['body', 'name'], msg: 'String should have at least 1 character' }] },
        422,
      ),
    )

    expect(error).toBeInstanceOf(FieldError)
    expect((error as FieldError).field).toBe('name')
  })

  it('trata versão desatualizada como conflito, para reler e não reenviar', async () => {
    const error = await failureFrom(
      reply({ detail: { code: 'version_conflict', message: 'source definition was changed' } }, 409),
    )

    expect(error).toBeInstanceOf(ConflictError)
  })

  it('não confunde conflito de identidade com corrida de versão', async () => {
    const error = await failureFrom(
      reply(
        {
          detail: {
            code: 'identity_conflict',
            message: 'domain acme.com already belongs to Acme',
            field: 'domain',
          },
        },
        409,
      ),
    )

    expect(error).not.toBeInstanceOf(ConflictError)
    expect(error).toBeInstanceOf(FieldError)
    expect((error as FieldError).field).toBe('domain')
  })

  it('mantém a mensagem do domínio quando não há campo', async () => {
    const error = await failureFrom(
      reply(
        {
          detail: {
            code: 'INVALID_CONFIGURATION',
            message: 'external sources require confirmed evidence',
          },
        },
        422,
      ),
    )

    expect(error).not.toBeInstanceOf(FieldError)
    expect(error.message).toBe('external sources require confirmed evidence')
  })
})
