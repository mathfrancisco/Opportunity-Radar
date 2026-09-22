# CARD F14-04 — Cadastro e edição de empresa pela interface

- **Status:** Backlog
- **Fase:** 14 — Cadastro e curadoria pela interface
- **Depende de:** Fase 13
- **Bloqueia:** F14-05
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §3

## Resultado

O operador cria uma empresa e corrige seus dados pela tela, e um nome já conhecido vira
alias em vez de uma segunda empresa.

## Contexto

`src/opportunity_radar/presentation/http/companies.py` expõe apenas leitura e a proposta de
fonte. O catálogo só cresce pelo importador da pesquisa, o que torna toda descoberta
posterior — uma empresa citada numa vaga, um nome corrigido — impossível de registrar sem
acesso ao banco. `CompanyService.reconcile` já resolve identidade e alias; falta o contrato
HTTP que a use.

## Escopo

- `POST /companies` e `PATCH /companies/{id}` com nome canônico, domínio, prioridade,
  status de radar e aliases.
- Reconciliação na criação: nome equivalente a uma empresa existente devolve a existente com
  o alias registrado, e a resposta diz qual caminho foi tomado.
- Concorrência otimista com a versão que `Company` já persiste.
- Formulário de criação e edição na tela de empresas, com o resultado da reconciliação
  visível.

## Fora de escopo

- Excluir empresa, mesclar duas empresas existentes ou reescrever histórico de aquisição.
- Importar lote pela interface.
- Alterar `CompanySource`, que é escopo de F14-05.

## Notas de implementação

A normalização do nome é a mesma do importador, não uma segunda regra na camada HTTP. Um
domínio repetido colide por índice único: essa colisão é conflito de identidade e precisa
chegar à tela como tal, não como erro genérico.

## Critérios de aceite

- [ ] Criar empresa pela tela grava nome canônico, normalizado e prioridade.
- [ ] Criar empresa com nome equivalente a uma existente registra alias e não duplica.
- [ ] Editar empresa exige a versão esperada e reporta conflito quando ela mudou.
- [ ] Domínio já usado por outra empresa é recusado com mensagem de identidade.
- [ ] A empresa criada aparece na listagem e no detalhe sem recarregar a página.
- [ ] Nenhum campo de auditoria existente é sobrescrito pela edição.

## Verificação

Criar empresa nova, recriar com variação do mesmo nome e conferir que virou alias; editar
com versão desatualizada e confirmar o conflito; conferir no E2E que o total do catálogo
cresce em um após a criação.

## Arquivos prováveis

- `src/opportunity_radar/presentation/http/companies.py`
- `src/opportunity_radar/companies/service.py`
- `src/opportunity_radar/companies/repository.py`
- `apps/web/src/routes/CompaniesPage.tsx`
- `apps/web/src/features/companies/api.ts`
- `tests/backend/companies/`
