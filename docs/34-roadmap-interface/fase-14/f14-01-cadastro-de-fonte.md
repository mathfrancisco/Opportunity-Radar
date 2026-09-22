# CARD F14-01 — Cadastro de fonte pela interface

- **Status:** Backlog
- **Fase:** 14 — Cadastro e curadoria pela interface
- **Depende de:** Fase 13
- **Bloqueia:** F14-02, F14-03
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §3

## Resultado

O operador cria uma `SourceDefinition` pela tela de fontes, com a configuração que o
collector escolhido exige, e a fonte nasce desabilitada como qualquer outra.

## Contexto

`POST /sources` existe, é testado e valida a configuração por tipo de collector.
`apps/web/src/routes/SourcesPage.tsx` não tem um único formulário: a tela sabe executar e
inspecionar fontes que alguém criou por fora. Uma fonte nova exige `curl` ou script, o que
faz do catálogo de aquisição algo fechado depois da importação inicial.

## Escopo

- Formulário de criação com tipo, nome, agendamento, prioridade e política de rate limit.
- Campos de configuração condicionados ao tipo: `board_identifier` para Ashby,
  `site_identifier` e `api_region` para Lever, `board_token` para Greenhouse, nenhum para
  Remotive e manual.
- Exibir, no próprio formulário, por que a fonte nasce desabilitada e o que falta para
  habilitá-la.
- Mapear o erro 422 do servidor para o campo que o originou, preservando o que foi digitado.
- Atualizar a lista de fontes sem recarregar a página.

## Fora de escopo

- Habilitar a fonte no ato da criação, testar o endpoint ao vivo ou aceitar segredo em
  campo de configuração.
- Editar o tipo de uma fonte existente.

## Notas de implementação

O contrato já rejeita segredo em `configuration` e exige o gate de habilitação; a tela
espelha essas regras em vez de reimplementá-las. Use o componente de campo da Fase 15 se ele
já existir; se não, crie-o em `apps/web/src/components/` no formato que F15-02 define.

## Critérios de aceite

- [ ] Uma fonte de cada tipo suportado pode ser criada pela tela.
- [ ] Campos de configuração mudam com o tipo escolhido e são exigidos quando obrigatórios.
- [ ] Erro de validação aparece no campo correspondente, sem limpar o formulário.
- [ ] A fonte criada aparece na lista já como desabilitada.
- [ ] Nenhum caminho da tela cria fonte externa habilitada.
- [ ] Tentar salvar segredo em configuração é recusado com a mensagem do servidor.

## Verificação

Criar por tela uma fonte de cada tipo, incluindo um caso inválido por tipo; conferir na API
que o registro nasceu desabilitado e com a configuração esperada. Teste de unidade do
cliente cobrindo o mapeamento de 422 por campo.

## Arquivos prováveis

- `apps/web/src/routes/SourcesPage.tsx`
- `apps/web/src/features/sources/api.ts`
- `apps/web/src/features/sources/useSources.ts`
- `apps/web/src/features/sources/api.test.ts`
- `.github/workflows/pipeline.yml`
