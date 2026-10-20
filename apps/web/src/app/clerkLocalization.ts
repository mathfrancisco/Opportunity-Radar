import { ptBR } from '@clerk/localizations'

/**
 * Official pt-BR plus the strings @clerk/localizations leaves `undefined` on screens Bateia
 * shows. An undefined key falls back to the English default, so each one is filled here.
 */
export const clerkLocalization = {
  ...ptBR,
  formFieldInputPlaceholder__signUpPassword: 'Crie uma senha',
}
