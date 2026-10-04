# F46-11 — Usabilidade das dez telas do dashboard

## Objetivo e precedência

Esta extensão atende ao pedido do usuário de revisar cada página antes de ativar IA e
busca por oportunidades. A spec 46 original exclui novos filtros de dados; esse limite fica
**superado para esta extensão**. Manter `DESIGN.md` como fonte visual: tema claro, painel e
sidebar existentes, tipografia, tokens, densidade e acento atuais. Melhorar hierarquia,
orientação, legibilidade, controles, estados e uso em telas estreitas sem mudar regras de
negócio ou contratos de API. Criar filtros apenas quando houver campo ou dado já disponível;
não inventar semântica nem sugerir que badge seja decisão automática.

## Regras comuns de aceite

- Cada tela tem um título e uma ação principal identificáveis; conteúdo relacionado fica
  agrupado em seções nomeadas, com espaçamento consistente e sem cartões decorativos em
  excesso.
- Filtros frequentes ficam visíveis junto à lista/tabela. Filtros avançados podem ser
  agrupados em disclosure nativo, nomeado e operável por teclado. Mostrar filtros ativos e
  ação para limpar quando a tela oferecer esses controles. Declarar quando a filtragem for
  local ou limitada à página atual; mudança de filtro reseta a paginação quando aplicável.
- Dropdowns têm rótulo acessível, estado aberto/fechado exposto, fechamento por `Escape`,
  foco previsível e opção selecionada visível. Preferir controles nativos existentes e
  padrões já usados no projeto.
- Tabs só são usadas quando alternam painéis irmãos reais. Implementar `tablist`, `tab`,
  `tabpanel`, foco/teclado e indicação de aba ativa; se forem apenas links de navegação,
  mantê-los como links.
- Badges usam texto explícito além de cor, distinguem estado de dado e de ação, e mostram
  somente informação útil para decidir o próximo passo. Alvos móveis têm pelo menos 44px;
  não há rolagem horizontal da página a 320px. Tabelas podem rolar dentro de seu contêiner.
- Preservar seletores acessíveis e contratos E2E existentes; adicionar/ajustar testes por
  critério, não snapshots frágeis de classes. Conferir cada rota em desktop e 375px com
  dados carregados, vazios e erro quando a tela tiver esses estados.

## Plano por página

| Ordem / rota | Ajustes de usabilidade | Aceite verificável | Teste de página |
| --- | --- | --- | --- |
| 1. `/` — Visão geral | Organizar resumo operacional, atividade e recomendações em seções com títulos; reduzir repetição de métricas; dar rótulos e contexto aos períodos; tornar listas e tabelas escaneáveis. | Período ativo é evidente e altera os dados exibidos; cartões de métrica têm nome, valor e contexto; links para Inbox/fontes têm destino claro; seções mantêm ordem útil em mobile. | `OverviewPage.test.tsx`: seleção de período, navegação para listas, nomes acessíveis e estados vazio/erro; desktop/mobile sem overflow de página. |
| 2. `/inbox` — Oportunidades | Consolidar filtros frequentes em barra curta e avançados em “Mais filtros”; deixar busca, filtros ativos, ordenação, resultados, paginação e buscas salvas fáceis de localizar; densidade da linha sem esconder veredito, duplicata ou selo startup. | Aplicar/remover cada filtro atualiza os resultados, limpa filtros restaura padrão e volta à página 1; busca salva abre/fecha acessivelmente; badges têm rótulos inequívocos; desktop e cartões mobile expõem as mesmas decisões e ações. | `InboxPage.test.tsx`: regressões para busca, filtros avançados/ativos/limpar, dropdown de buscas salvas, paginação e equivalência de campos desktop/mobile. |
| 3. `/opportunities/:opportunityId` — Detalhe da oportunidade | Criar hierarquia para empresa/cargo, decisão e ações; agrupar evidências, critérios, análise e candidatura em seções; usar disclosure para conteúdo secundário extenso. | Cargo, empresa, localização, estado da avaliação e ação “Avaliar agora” são localizados sem percorrer a página; detalhes recolhíveis anunciam estado; tabelas e formulários cabem no viewport móvel. | `OpportunityDetailPage.test.tsx`: hierarquia e ação principal, abrir/fechar detalhes por teclado, badges com texto, campos/ações de candidatura. |
| 4. `/applications` — Candidaturas | Melhorar leitura do pipeline por estágio; tornar estágio e ações de cada cartão distinguíveis; manter navegação horizontal de colunas utilizável em mobile sem deslocar a página toda. | Cada coluna identifica estágio e contagem; cartões identificam vaga/empresa e próximo estado; foco/teclado alcançam todas as ações; mobile permite percorrer colunas sem cortar controles. | Criar `PipelinePage.test.tsx`: estágio/contagem, ações por cartão e navegação/overflow responsivo; verificar lista vazia. |
| 5. `/companies` — Empresas | Dar prioridade à busca e aos filtros disponíveis; alinhar badges de prioridade, situação e verificação; manter tabela e cartões com os mesmos dados e caminhos. Prioridade, status e verificação são filtrados no cliente somente sobre os itens da página já carregada; deixar esse escopo visível junto ao resultado e não sugerir filtro do catálogo inteiro. | O texto de resultados informa quantos itens da página atual correspondem aos filtros locais; badges explicam o estado com texto; abrir empresa funciona em tabela e cartão; paginação/tamanho preservam limites atuais. | `CompaniesPage.test.tsx`: busca, filtros locais explicitamente limitados à página, badges, navegação e paginação em layouts desktop/mobile. Evidência de teste ainda precisa ser registrada. |
| 6. `/companies/:companyId` — Detalhe da empresa | Separar resumo, configuração, fontes e vagas recentes; reduzir exposição de códigos internos; organizar edição e formulários; agrupar informação longa em disclosures. | Identidade e estado da empresa aparecem primeiro; códigos técnicos ganham rótulo humano existente; editar/salvar/cancelar têm controles e feedback distinguíveis; últimas vagas são legíveis em mobile. | Criar `CompanyDetailPage.test.tsx`: navegação/formulário, disclosures acessíveis, estados e leitura dos rótulos/badges. |
| 7. `/sources` — Fontes | Separar catálogo de fontes, operações e histórico; deixar estado, última execução, agendamento e ação por fonte fáceis de comparar; melhorar filtros/ordenação se os campos já estiverem disponíveis. | “Executar agora”, homologar e histórico permanecem associados à fonte correta; formulário aberto e resultado da execução têm status visível; tabela não comprime ações; layout móvel mantém controles alcançáveis. | `SourcesPage.test.tsx`: ações por linha, filtros se adicionados, formulários, histórico e mensagens de execução. |
| 8. `/sources/homologation-queue` — Fila de homologação | Explicar o que está pendente e como avançar; destacar proposta selecionada, resultado da sonda e ações; se existir modo lista/sequencial, oferecer navegação claramente rotulada. | Seleção e progresso da fila são anunciados; homologar/avançar/voltar funcionam por teclado; badges distinguem pendente, aprovado e falha por texto; detalhe não fica cortado em mobile. | `HomologationQueue.test.tsx`: fila/lista e modo sequencial, seleção, ações, status acessível e viewport móvel. |
| 9. `/profile` — Perfil | Agrupar preferências relacionadas em seções; ordenar campos por fluxo de configuração; tornar versões, ajuda e salvamento fáceis de entender. | Cada controle mantém rótulo e dica vinculados; versões podem ser escolhidas sem perder a seleção; salvar/erro/pendências são anunciados e não dependem apenas de cor; formulários funcionam em 320–375px. | `ProfilePage.test.tsx`: grupos, rótulo/dica, seleção de versão, validação e feedback de salvamento. |
| 10. `/status` — Status | Apresentar resumo de prontidão, explicação do estado agregado e próxima ação. A API atual fornece prontidão agregada, combinando `/health/ready` e o sinal de IA de `/health`; não expõe estado nem horário de atualização por componente. Não inventar componentes, timestamps ou granularidade que o contrato não fornece. | Estado agregado de carregamento, erro, degradado e pronto é explicado por texto; próxima ação corresponde ao estado; nenhum horário/componente individual é insinuado. | `StatusPage.test.tsx`: estados agregados, mensagem/ação correspondente e rótulos acessíveis. O teste existe no worktree, mas sua execução ainda precisa ser registrada. |

## Sequência de execução e bloqueio operacional

1. Implementar shell/componentes compartilhados necessários e telas 1–10 na ordem acima;
   após cada fatia, executar os testes de página indicados. Registrar evidência por rota
   somente após inspecionar as alterações e executar seu teste direcionado. A inspeção dos
   arquivos alterados não substitui a evidência de teste. Fazer revisão visual desktop e
   mobile de todas as rotas e corrigir os problemas encontrados.
2. Só considerar concluída a etapa de interface quando as dez rotas atenderem aos critérios
   comuns e específicos, testes pertinentes estiverem verdes e houver evidência visual em
   desktop e mobile.
3. **Depois da interface**, verificar configuração de provedor/modelo e credenciais sem
   expor valores; ativar IA e busca conforme os comandos suportados pelo ambiente. Registrar
   fontes, configuração não secreta, hora de início/fim, duração, quantidades e falhas da
   execução. Se credencial necessária estiver ausente, registrar o bloqueio sem fingir
   ativação ou fabricar resultados.
4. **Depois da busca**, avaliar as vagas realmente coletadas: amostra e total; duplicatas;
   validade do link e evidência de publicação; aderência explícita ao perfil; completude de
   cargo, empresa, local, modalidade, senioridade e remuneração quando disponível; frescor
   das datas; falsos positivos e itens sem evidência. Distinguir fatos observados de
   julgamento manual. Medir duração de ponta a ponta e, se disponível, por fonte/etapa,
   sempre informando o intervalo medido e o volume processado.

## Limites e incerteza

Este documento registra critérios e sequência; não declara concluída nenhuma rota nem
representa resultado visual ou de busca. Os arquivos de páginas e testes já aparecem como
alterados/criados no worktree, mas a implementação por rota só deve ser marcada após revisar
o diff daquela tela e obter evidência do teste direcionado. Validação visual em runtime,
desktop/mobile, e verificações completas continuam pendentes. A disponibilidade de
credenciais de IA/busca e o tempo de execução só podem ser confirmados no ambiente após a
etapa de UI; não fixar nota de qualidade sem examinar as vagas coletadas.

## Evidência automática atual — 2026-10-04

- `cd apps/web && npm run check` terminou com código 0: lint, typecheck, Vitest e build
  concluídos na árvore que contém os ajustes das dez rotas e seus testes de página.
- O container `spec46full-frontend` foi reconstruído da árvore atual; a etapa de build
  concluiu `tsc -b && vite build`. O serviço respondeu saudável em
  `http://localhost:3000`.
- Antes da alteração indevida da fixture operacional, `tests/e2e/browser/specs/03-visual.spec.ts`
  passou com **14 testes em 20,5 s** contra esse frontend: oito telas principais e dois detalhes
  em 1280 px e 375 px, ausência de overflow horizontal em 320 px e interações de teclado/foco.
  Os screenshots desse ensaio estão em `tests/e2e/browser/test-results/visual/` no worktree local.
- Uma repetição posterior, com a fixture reduzida, encontrou overflow horizontal de 357 px em
  `/companies` no viewport de 320 px e não encontrou paginação para marcar a página corrente.
  Reexecutar a verificação visual depois de restaurar o ambiente isolado; não tratar o resultado
  anterior como aprovação da interface atual.
- Não usar os dados produzidos pelos cenários E2E como evidência de catálogo ou IA. A suíte
  cria fontes e vagas sintéticas; a validação operacional do catálogo exige ambiente isolado
  e dados restaurados.

## Pendência humana

Os critérios e as verificações automatizadas das rotas estão registrados, mas a conclusão da
interface ainda depende de uma revisão visual humana dos screenshots desktop e mobile contra
`docs/assets/audit-log-reference.png`. Não registrar essa aprovação sem a comparação humana.
Disponibilidade de credenciais de IA/busca, coleta e qualidade das vagas continuam fora desta
validação de interface.
