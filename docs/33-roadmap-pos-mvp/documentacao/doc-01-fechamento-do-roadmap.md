# CARD DOC-01 — Fechar documentação do roadmap

- **Status:** Backlog
- **Fase:** Documentação transversal
- **Depende de:** Cards que alteram contratos ou operação
- **Bloqueia:** Critério final de aceite
- **Origem no roadmap:** [Higiene de documentação](../../33-roadmap-pos-mvp.md#27-higiene-de-documentação)

## Resultado

Roadmap do MVP, roadmap pós-MVP, runbook e índice de cards descrevem o comportamento que
foi realmente entregue.

## Contexto

O doc 29 mantém a Definition of Done desmarcada enquanto os critérios globais estão
concluídos. A operação autônoma também exige novos comandos, kill switches, alertas e
procedimentos de diagnóstico no runbook.

## Escopo

- Resolver a contradição entre os §§72 e 77 do doc 29.
- Apontar o doc 29 para o roadmap pós-MVP e seu índice de cards.
- Atualizar o runbook com jobs, execução forçada, kill switches, alertas e recuperação.
- Revisar links, nomes de configuração e exemplos contra o código final.

## Fora de escopo

- Marcar card funcional como concluído sem sua verificação.
- Documentar comportamento ainda não implementado como disponível.
- Reescrever documentos arquiteturais não afetados.

## Notas de implementação

Atualizar a documentação junto do card funcional quando possível. DOC-01 faz a passagem
final de consistência; não deve acumular toda a escrita para o fim.

## Critérios de aceite

- [ ] O doc 29 não contém checklists contraditórios.
- [ ] O doc 29 aponta para este roadmap e para o índice de cards.
- [ ] O runbook explica como desligar e forçar cada job funcional.
- [ ] O runbook explica alertas, recuperação e diagnóstico de cobertura parcial.
- [ ] Todos os links relativos resolvem para arquivos existentes.
- [ ] Nenhum item futuro aparece como funcionalidade já disponível.

## Verificação

Revisar cada comando e variável contra o código e o Compose, validar os links relativos e
executar o cenário documental somente quando o card funcional correspondente autorizar.

## Arquivos prováveis

- `docs/29-roadmap-mvp.md`
- `docs/30-runbook.md`
- `docs/33-roadmap-pos-mvp.md`
- `docs/33-roadmap-pos-mvp/`
- `README.md`
