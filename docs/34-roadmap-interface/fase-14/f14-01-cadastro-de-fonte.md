# CARD F14-01 — Cadastro de fonte pela interface

- **Status:** Concluído em 2026-09-23
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

- [x] Uma fonte de cada tipo suportado pode ser criada pela tela.
- [x] Campos de configuração mudam com o tipo escolhido e são exigidos quando obrigatórios.
- [x] Erro de validação aparece no campo correspondente, sem limpar o formulário.
- [x] A fonte criada aparece na lista já como desabilitada.
- [x] Nenhum caminho da tela cria fonte externa habilitada.
- [x] Tentar salvar segredo em configuração é recusado com a mensagem do servidor.

## Verificação

Criar por tela uma fonte de cada tipo, incluindo um caso inválido por tipo; conferir na API
que o registro nasceu desabilitado e com a configuração esperada. Teste de unidade do
cliente cobrindo o mapeamento de 422 por campo.

## Nota de execução

O formulário está na tela de fontes, atrás de "Nova fonte". Os campos de configuração mudam
com o tipo, e o formulário nunca envia `enabled` nem `evidence_status`: toda fonte nasce
desabilitada e com evidência `unverified`, sem caminho para outra coisa.

Para o 422 chegar ao campo, o servidor passou a dizer qual campo recusou:
`AcquisitionError` ganhou `field`, e a validação de `create_source` atribui cada recusa ao
campo que a causou (`configuration.board_token`, `rate_limit_policy`, `configuration`).
A validação do próprio FastAPI, que chega como lista com `loc`, cai no mesmo
`FieldError` do cliente (`failureFrom` em `lib/api.ts`). Recusa sem campo aparece uma vez,
acima das ações. Nos dois casos o que foi digitado fica.

Como o formulário só tem campos conhecidos, "salvar segredo em configuração" não teria como
acontecer, e o critério não seria demonstrável. Por isso existe o campo "Outros campos de
configuração" (`chave=valor`): ele cobre as chaves opcionais que um collector aceita, e é
nele que `api_key=...` é recusado com a mensagem do servidor, sob o próprio campo.

A verificação pela tela achou um defeito do `Field` da Fase 15: o rótulo envolvia o
controle, e um `select` dentro dele emprestava a opção escolhida ao nome acessível ("Tipo
Greenhouse"). O `Field` agora nomeia o controle por `aria-labelledby`, e lê a dica por
`aria-describedby` junto com o erro.

Verificado no navegador contra a API real: uma fonte de cada tipo criada pela tela e
conferida em `/api/sources` como desabilitada e com a configuração esperada; token inválido
e segredo recusados no campo, sem limpar o formulário.

## Arquivos prováveis

- `apps/web/src/routes/SourcesPage.tsx`
- `apps/web/src/features/sources/api.ts`
- `apps/web/src/features/sources/useSources.ts`
- `apps/web/src/features/sources/api.test.ts`
- `.github/workflows/pipeline.yml`
