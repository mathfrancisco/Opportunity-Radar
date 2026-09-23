# CARD F15-03 — Estados de carregamento, vazio, erro e conflito

- **Status:** Concluído em 2026-09-22
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

- [x] As quatro variantes existem uma vez e são usadas por todas as rotas.
- [x] Toda mudança de estado é anunciada em região viva.
- [x] Taxa ou métrica indisponível aparece como indisponível, nunca como zero.
- [x] Erro recuperável oferece nova tentativa; conflito oferece recarregar o registro.
- [x] Nenhuma rota mantém bloco próprio de carregando, vazio ou erro.

## Verificação

Teste de unidade por variante, incluindo o caso de valor `null`; percorrer cada rota com a
API fora do ar, com resposta vazia e com conflito forçado.

## Nota de execução

O conflito passou a ser um tipo, e não uma mensagem: `requestFailure` em `lib/api.ts`
devolve `ConflictError` para 409, e as escritas versionadas — perfil e candidatura — o
propagam. Sem isso, a tela não teria como distinguir "o registro mudou, releia" de "a
requisição falhou, tente de novo", e repetir uma escrita conflitante é o caminho mais
curto para uma das duas edições sumir.

As regiões vivas saíram dos contêineres das rotas e foram para os próprios componentes de
estado: uma `aria-live` em volta de uma tabela inteira anuncia a tabela inteira a cada
refetch, e um alerta aninhado nela seria anunciado duas vezes.

## Arquivos prováveis

- `apps/web/src/components/`
- `apps/web/src/routes/`
- `apps/web/src/features/dashboard/api.ts`
