# CARD F14-03 — Entrada manual de vaga pela interface

- **Status:** Concluído em 2026-09-23
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

- [x] Uma vaga por URL, uma por texto e uma por arquivo podem ser registradas pela tela.
- [x] A mesma submissão repetida é reportada como repetida, e não como nova.
- [x] O resultado mostra contadores do run e o desfecho da normalização por item.
- [x] Item normalizado com sucesso oferece link para a oportunidade.
- [x] Item que falhou na normalização mostra o motivo registrado pelo domínio.
- [x] Nenhuma vaga entra sem `SourceRun` e `RawItem` correspondentes.

## Verificação

Registrar as três formas de entrada pela tela, repetir uma delas e conferir `items_skipped`;
confirmar na API que cada oportunidade criada tem ocorrência e resultado de normalização
apontando para o `RawItem` submetido.

## Nota de execução

A resposta do run diz quantos itens entraram, mas não quais. Para mostrar o desfecho item a
item, a API ganhou `POST /opportunities/normalizations/runs/{run_id}`: ele normaliza os
`RawItem` que aquele run preservou e responde um por um, com o resultado e a oportunidade.
A normalização continua idempotente por item. Um run em que tudo se repetiu responde lista
vazia, e a tela explica que repetida quer dizer já registrada, não perdida.

O painel "Registrar vaga" aparece nos cartões de fonte manual habilitada. Se nenhuma fonte
manual existe, a tela de fontes oferece criá-la pelo formulário de F14-01, já no tipo
manual, em vez de criar uma implícita.

Os metadados do formulário são os que o normalizador lê: `title`, `company_name`,
`location_text` e `skills`. Senioridade não entrou: o normalizador a deriva do título e não
lê metadado para isso, então um campo ali prometeria algo que o domínio ignora.

Limites mostrados antes do envio: arquivo até 5 MB (o contrato aceita 7 000 000 caracteres
de base64) e texto até 2048 caracteres, o `max_length` de `value`.

Verificado no navegador: URL, texto e arquivo na mesma submissão, três oportunidades novas
com link; repetida, `3 repetidas` e nenhuma nova; a oportunidade aberta tem ocorrência e
resultado de normalização apontando para o `RawItem`.

## Arquivos prováveis

- `apps/web/src/routes/SourcesPage.tsx`
- `apps/web/src/features/sources/api.ts`
- `apps/web/src/features/opportunities/api.ts`
- `apps/web/src/features/sources/api.test.ts`
- `.github/workflows/pipeline.yml`
