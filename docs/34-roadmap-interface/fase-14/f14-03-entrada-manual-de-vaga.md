# CARD F14-03 — Entrada manual de vaga pela interface

- **Status:** Backlog
- **Fase:** 14 — Cadastro e curadoria pela interface
- **Depende de:** F14-01
- **Bloqueia:** Milestone M
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §3

## Resultado

O operador registra uma vaga avulsa por URL, texto ou arquivo e acompanha, na mesma tela, o
que a aquisição preservou e o que a normalização decidiu.

## Contexto

O collector manual aceita `URL`, `TEXT` e `FILE` e é exercitado pelo E2E por `curl`. A
interface não expõe esse caminho, então uma vaga encontrada fora das fontes configuradas
não tem como entrar sem terminal — e o radar perde exatamente o caso que motivou a entrada
manual existir.

## Escopo

- Formulário de submissão com tipo de entrada, valor, tipo de conteúdo e metadados básicos
  reconhecidos pelo normalizador, como título, empresa, localidade e senioridade.
- Permitir mais de uma entrada na mesma submissão, como o contrato já aceita.
- Exibir o resultado do `SourceRun`: itens vistos, persistidos, repetidos e inválidos.
- Disparar a normalização do lote e mostrar o resultado por item, com link para a
  oportunidade quando houver.
- Deixar explícito quando o item foi ignorado por já existir, em vez de parecer perda.

## Fora de escopo

- Buscar a URL submetida, raspar página protegida ou inferir campo ausente.
- Criar `Opportunity` diretamente, sem `RawItem` e sem procedência.
- Editar a oportunidade normalizada por formulário livre.

## Notas de implementação

O envio usa a fonte manual escolhida pelo operador; se nenhuma existir, a tela oferece criar
uma por F14-01 em vez de criar uma implícita. Arquivo vai em `content_base64` com o
`content_type` declarado, e o limite do contrato precisa aparecer antes do envio, não como
erro depois.

## Critérios de aceite

- [ ] Uma vaga por URL, uma por texto e uma por arquivo podem ser registradas pela tela.
- [ ] A mesma submissão repetida é reportada como repetida, e não como nova.
- [ ] O resultado mostra contadores do run e o desfecho da normalização por item.
- [ ] Item normalizado com sucesso oferece link para a oportunidade.
- [ ] Item que falhou na normalização mostra o motivo registrado pelo domínio.
- [ ] Nenhuma vaga entra sem `SourceRun` e `RawItem` correspondentes.

## Verificação

Registrar as três formas de entrada pela tela, repetir uma delas e conferir `items_skipped`;
confirmar na API que cada oportunidade criada tem ocorrência e resultado de normalização
apontando para o `RawItem` submetido.

## Arquivos prováveis

- `apps/web/src/routes/SourcesPage.tsx`
- `apps/web/src/features/sources/api.ts`
- `apps/web/src/features/opportunities/api.ts`
- `apps/web/src/features/sources/api.test.ts`
- `.github/workflows/pipeline.yml`
