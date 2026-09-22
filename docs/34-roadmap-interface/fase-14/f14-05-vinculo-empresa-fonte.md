# CARD F14-05 — Vínculo entre empresa e fonte pela interface

- **Status:** Backlog
- **Fase:** 14 — Cadastro e curadoria pela interface
- **Depende de:** F14-04
- **Bloqueia:** Milestone M
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §3

## Resultado

O operador registra o ATS de uma empresa pela tela, corrige o que a descoberta encontrou e
transforma esse registro em uma proposta de fonte auditável.

## Contexto

`POST /companies/{id}/detect-source` já propõe uma fonte a partir de um `CompanySource`
pesquisado, e `CompanyDetailPage` já a exibe. O que falta é o passo anterior: quando a
descoberta não encontra nada, ou encontra o identificador errado, não há como registrar ou
corrigir o `CompanySource` sem banco. A proposta fica dependendo de dados que só o
importador consegue escrever.

## Escopo

- `POST /companies/{id}/sources` e `PATCH /companies/{id}/sources/{source_id}` com tipo,
  endpoint, chave externa e nota de evidência.
- Formulário no detalhe da empresa para adicionar e corrigir esse registro.
- Encadear a proposta existente: registrado o ATS, a tela oferece propor a fonte e mostra se
  o resultado foi `proposed`, `already_proposed` ou `not_detected`.
- Deixar explícito que a proposta nasce inerte e ainda passa pelo gate de homologação.

## Fora de escopo

- Habilitar a fonte proposta, que é F14-02.
- Testar o endpoint do ATS ao vivo a partir da tela.
- Inferir o identificador a partir da URL colada.

## Notas de implementação

`CompanySource` já carrega evidência e é a base da proposta; o card não inventa outro lugar
para guardar isso. A nota de evidência é o que um revisor lê depois para decidir se a fonte
merece ser homologada, então ela é obrigatória na criação manual.

## Critérios de aceite

- [ ] Registrar um ATS para uma empresa sem fonte pesquisada é possível pela tela.
- [ ] Corrigir a chave externa de um `CompanySource` existente é possível e auditável.
- [ ] Propor a fonte a partir do registro devolve e exibe o desfecho da proposta.
- [ ] A fonte proposta aparece desabilitada e com a evidência que a originou.
- [ ] Repetir a proposta não cria uma segunda `SourceDefinition`.
- [ ] Tipo de ATS não suportado é recusado com a mensagem do domínio.

## Verificação

Em uma empresa sem ATS pesquisado, registrar um `CompanySource`, propor a fonte e conferir
em `/api/sources` que ela nasceu desabilitada com `evidence_status` de descoberta; repetir a
proposta e confirmar `already_proposed`.

## Arquivos prováveis

- `src/opportunity_radar/presentation/http/companies.py`
- `src/opportunity_radar/companies/repository.py`
- `src/opportunity_radar/acquisition/service.py`
- `apps/web/src/routes/CompanyDetailPage.tsx`
- `apps/web/src/features/companies/api.ts`
- `tests/backend/companies/`
