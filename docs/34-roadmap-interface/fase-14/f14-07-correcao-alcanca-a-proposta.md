# CARD F14-07 — Correção do ATS alcança a fonte proposta

- **Status:** Concluído em 2026-09-23
- **Fase:** 14 — Cadastro e curadoria pela interface
- **Depende de:** F14-05
- **Bloqueia:** Nenhum
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §3

## Resultado

Corrigir a chave do ATS de uma empresa depois de propor a fonte não deixa a fonte proposta
apontando para o board errado: ou a correção chega a ela, ou a tela diz por que não chegou e
o que fazer.

## Contexto

A proposta de fonte é encontrada por `company_source_id`. Na F14-05, corrigir a chave de um
`CompanySource` que já foi proposto grava a revisão, mas a `SourceDefinition` existente
continua com a chave antiga, e propor de novo responde `already_proposed`. O operador
corrige, vê o histórico certo na empresa, e a fonte que vai coletar lê outro board.

A F14-05 não mexeu nisso porque a `SourceDefinition` tem gate e versão próprios, e
reescrever a configuração dela por baixo, a partir de outra tela, é o tipo de atalho que a
fase proíbe. Este card decide como a correção chega lá sem esse atalho.

## Escopo

- Ao corrigir um `CompanySource`, localizar a proposta que nasceu dele e classificá-la:
  - **inerte** — desabilitada, sem termos revisados, sem collector testado e com evidência
    ainda de descoberta: a proposta não afirma nada sobre o board antigo, e a correção pode
    atualizar a chave e a `discovery_evidence` dela na mesma transação, com `version + 1`;
  - **homologada ou habilitada** — a evidência, os termos e o teste foram sobre o board
    antigo. A correção não reescreve a fonte: ela devolve que a proposta ficou desatualizada
    e a tela oferece reabrir a homologação.
- "Reabrir a homologação" é uma ação explícita sobre a fonte: desabilita, volta a evidência
  para `ats_identified`, limpa termos revisados e collector testado, e troca a chave — tudo
  com `expected_version` e registrado. Nada disso acontece como efeito colateral de editar a
  empresa.
- A resposta da correção diz qual dos caminhos foi tomado, e o detalhe da empresa mostra a
  fonte proposta com a chave que ela usa hoje, lado a lado com a do registro.

## Fora de escopo

- Criar uma segunda proposta para a chave nova ao lado da antiga.
- Desabilitar uma fonte habilitada sem o operador pedir.
- Mesclar ou excluir propostas.

## Notas de implementação

A classificação lê a própria `SourceDefinition` (`enabled`, `terms_reviewed`,
`collector_local_tested`, `evidence_status`), como o gate já faz, e não um campo novo. A
atualização da proposta inerte e a revisão do `CompanySource` são uma transação só: se a
versão da fonte mudou no meio, as duas recusam juntas.

Reabrir a homologação desliga a coleta de uma fonte que funcionava. É a resposta certa —
a coleta estaria lendo um board que o operador acabou de dizer que é outro —, mas a tela
precisa dizer isso antes do clique, não depois.

## Critérios de aceite

- [x] Corrigir o ATS de uma proposta inerte atualiza a chave e a evidência da proposta, e
      propor de novo responde `already_proposed` com a chave nova.
- [x] Corrigir o ATS de uma fonte homologada não altera a fonte e informa que ela ficou
      desatualizada.
- [x] Reabrir a homologação desabilita, limpa o gate e troca a chave numa única escrita
      versionada.
- [x] Conflito de versão na fonte durante a correção recusa as duas escritas.
- [x] O detalhe da empresa mostra a chave do registro e a chave da fonte proposta.

## Nota de execução

`acquisition/proposals.py` decide o que acontece com a proposta. `is_inert` lê a própria
`SourceDefinition`, sem campo novo: desabilitada, sem termos, sem collector testado e com
evidência ainda de descoberta. A correção do `CompanySource` chama `follow_correction` na
mesma transação. Proposta inerte recebe a chave e a nota novas numa escrita guardada por
versão; proposta que já foi revisada, testada ou habilitada fica como está. Se a proposta
muda entre a leitura e a escrita, `ProposalChangedError` desfaz a correção inteira, e a API
responde 409.

Troca de ATS (Greenhouse para Lever, por exemplo) sempre deixa a proposta desatualizada,
mesmo inerte: uma fonte não muda de collector, e reabrir também recusa esse caso com a
mensagem do domínio.

`PATCH /companies/{id}/sources/{source_id}` passou a responder
`{proposal_outcome, source}`, e cada `CompanySource` da empresa traz a `proposal` com a
chave que ela usa hoje e `outdated`. A página de lista busca as propostas de uma vez, não
uma consulta por registro.

`POST /sources/{id}/reopen-homologation` é a ação explícita: desabilita, volta a evidência
para `ats_identified`, limpa termos, teste e data de revisão e troca a chave, numa escrita
versionada. O `homologation_audit` antigo não é apagado: vai para
`reopened_homologations`, com a chave e a evidência anteriores.

Verificado no navegador: correção de proposta inerte chegando à fonte, correção de proposta
revisada deixada como estava e sinalizada, e reabertura trazendo a chave nova com o gate
zerado. O teste de integração cobre a corrida entre a leitura e a escrita.

## Verificação

Teste de integração dos três caminhos — proposta inerte, fonte homologada, conflito no meio
—, conferindo `version` e histórico dos dois lados; percorrer pela tela a correção de uma
proposta inerte e a reabertura de uma fonte homologada.

## Arquivos prováveis

- `src/opportunity_radar/companies/registration.py`
- `src/opportunity_radar/acquisition/service.py`
- `src/opportunity_radar/presentation/http/companies.py`
- `src/opportunity_radar/presentation/http/acquisition.py`
- `apps/web/src/routes/CompanyDetailPage.tsx`
- `apps/web/src/components/CompanySourceForm.tsx`
