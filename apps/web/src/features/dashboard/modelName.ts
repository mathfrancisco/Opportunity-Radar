/** The model name without its provider prefix ("cerebras:gpt-oss-120b" becomes "gpt-oss-120b"). */
export function modelName(model: string, provider: string): string {
  const prefix = `${provider}:`
  return provider && model.startsWith(prefix) ? model.slice(prefix.length) : model
}
