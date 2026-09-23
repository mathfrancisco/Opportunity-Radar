import { describe, expect, it } from 'vitest'
import { ConflictError, requestFailure } from './api'

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
