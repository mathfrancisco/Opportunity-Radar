# CARD F10-04 — Origem da execução em SourceRun

- **Status:** In progress
- **Fase:** 10 — Ciclo autônomo
- **Depende de:** Nenhum
- **Bloqueia:** F10-03, F10-06
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§9 e 12; ordem prática 46

## Resultado

Cada `SourceRun` informa se começou por agendamento (`SCHEDULED`) ou demanda
(`ON_DEMAND`), sem alterar o significado de `CollectionMode`.

## Contexto

`CollectionMode` já descreve `DISCOVERY`, `INCREMENTAL` ou `MANUAL`. Ele não
expressa quem disparou a execução. O histórico e a API precisam dessa separação
para explicar o ciclo autônomo.

## Escopo

- Adicionar `execution_trigger` a `SourceRun` por migration compatível.
- Fazer backfill seguro dos runs existentes com a origem correta definida pela
  política de compatibilidade documentada.
- Atualizar modelo, domínio, repositório, criação de runs e contrato HTTP.
- Exibir a origem no histórico de runs.
- Usar `SCHEDULED` no job de F10-03 e `ON_DEMAND` nos fluxos existentes.

## Fora de escopo

- Alterar valores ou semântica de `CollectionMode`.
- Criar outros gatilhos além de `SCHEDULED` e `ON_DEMAND`.
- Mudar a política de agendamento.

## Notas de implementação

Planejar a migration como adição não destrutiva: adicionar coluna, preencher
linhas existentes com a escolha de compatibilidade e só então torná-la
obrigatória, se aplicável. Documentar a escolha de backfill no próprio artefato
de migration ou teste correspondente.

## Critérios de aceite

- [ ] Migration preserva todos os `SourceRun` existentes.
- [ ] Cada novo run tem `execution_trigger` válido.
- [ ] Runs do job usam `SCHEDULED`.
- [ ] Runs por comando, API ou UI usam `ON_DEMAND`.
- [ ] API expõe a origem no histórico.
- [ ] UI diferencia origem de `CollectionMode` sem renomear este último.
- [ ] Testes confirmam que origem e modo coexistem sem ambiguidade.

## Verificação

Executar upgrade de migration sobre banco com runs pré-existentes e testar
serialização da API, criação agendada e sob demanda, e a tela de histórico.

## Arquivos prováveis

- `migrations/versions/<nova_migration>_source_run_execution_trigger.py`
- `src/opportunity_radar/acquisition/models.py`
- `src/opportunity_radar/acquisition/domain.py`
- `src/opportunity_radar/acquisition/repository.py`
- `src/opportunity_radar/acquisition/service.py`
- `src/opportunity_radar/presentation/http/acquisition.py`
- `apps/web/src/`
