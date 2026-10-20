import { describe, expect, it } from 'vitest'
import { clerkLocalization } from './clerkLocalization'

describe('clerkLocalization', () => {
  it('keeps the official pt-BR locale', () => {
    expect(clerkLocalization.locale).toBe('pt-BR')
    expect(clerkLocalization.formFieldInputPlaceholder__password).toBe('Digite sua senha')
  })

  it('fills the sign-up password placeholder that pt-BR leaves in English', () => {
    expect(clerkLocalization.formFieldInputPlaceholder__signUpPassword).toBe('Crie uma senha')
  })
})
