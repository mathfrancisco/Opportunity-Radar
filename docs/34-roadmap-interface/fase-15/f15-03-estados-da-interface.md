# CARD F15-03 — Estados de carregamento, vazio, erro e conflito

- **Status:** Backlog
- **Fase:** 15 — Design, consistência e acesso
- **Depende de:** F15-02
- **Bloqueia:** Milestone N
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §4

## Resultado

Carregando, vazio, erro e conflito têm uma implementação compartilhada, e a diferença entre
"sem dados" e "não medido" continua visível.

## Contexto

Cada rota reescreve seus estados: `OverviewPage` usa um bloco, `SourcesPage` outro,
`InboxPage` um terceiro, com textos e classes próximos mas diferentes. O operador reaprende
a mesma informação em cada tela. Pior, a Fase 13 introduziu métricas que valem `null` quando
não há execução na janela — um componente genérico que trate ausência como zero apagaria
justamente a distinção que aquela fase existiu para criar.

## Escopo

- Componentes `LoadingState`, `EmptyState`, `ErrorState` e `ConflictNotice`, com ação de
  recuperação quando ela existir.
- Migrar as nove rotas, preservando o texto específico de cada contexto.
- Padronizar a região viva que anuncia mudança de estado a leitor de tela.
- Definir e aplicar a representação de valor indisponível: `—` com rótulo acessível, nunca
  `0` nem célula vazia.

## Fora de escopo

- Toast global, fila de notificações ou sistema de mensagens.
- Alterar política de retry das consultas.
- Reescrever o texto de domínio de cada tela.

## Notas de implementação

Erro de rede, erro do servidor e conflito de versão são três coisas diferentes, e a única
com recuperação automática é a primeira. `ConflictNotice` existe para o 409 dos recursos
versionados — perfil, candidatura e, a partir da Fase 14, fonte e empresa.

## Critérios de aceite

- [ ] As quatro variantes existem uma vez e são usadas por todas as rotas.
- [ ] Toda mudança de estado é anunciada em região viva.
- [ ] Taxa ou métrica indisponível aparece como indisponível, nunca como zero.
- [ ] Erro recuperável oferece nova tentativa; conflito oferece recarregar o registro.
- [ ] Nenhuma rota mantém bloco próprio de carregando, vazio ou erro.

## Verificação

Teste de unidade por variante, incluindo o caso de valor `null`; percorrer cada rota com a
API fora do ar, com resposta vazia e com conflito forçado.

## Arquivos prováveis

- `apps/web/src/components/`
- `apps/web/src/routes/`
- `apps/web/src/features/dashboard/api.ts`
