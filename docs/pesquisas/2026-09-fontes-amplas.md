# Pesquisa de fontes amplas com busca por termo

Consulta em 26 de setembro de 2026. Pesquisei documentação oficial de APIs de
emprego amplas e seus termos publicados. Incluí fontes que documentam uma API
pública com consulta por palavra-chave/termo e não proíbem automação nessa API.
Sites cujos termos proíbem automação ficam fora, conforme o Fora de escopo do
[F20-33](../44-roadmap-fase-20/fase-20/f20-33-palavras-chave-do-perfil.md).
Esta triagem não certifica integração nem substitui a revisão de termos por
sub-card.

## Resultado da triagem

| Fonte | API pública | Busca por termo na API | Autenticação | Limites documentados | Paginação estável | Data de publicação | Decisão | Documentação oficial consultada |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Remotive | Sim | Sim, campo `search` | Não documentada como necessária | Recomenda até 4 consultas/dia; bloqueia acima de 2/min | Não documentada; há `limit`, sem página/cursor | Sim, `publication_date` | Aceita; fonte ampla já existente | [API e termos](https://github.com/remotive-com/remote-jobs-api), consultada em 26/09/2026 |
| Adzuna | Sim | Sim, campo `what` | Sim, `app_id` e `app_key` | 25/min, 250/dia, 1.000/semana, 2.500/mês | Número de página no caminho; snapshot estável não documentado | Sim, campo `created` | Candidata; sub-card condicionado à revisão de licença | [Busca](https://developer.adzuna.com/docs/search) e [termos](https://developer.adzuna.com/docs/terms_of_service), consultados em 26/09/2026 |
| USAJOBS | Sim | Sim, `Keyword` | Sim, chave solicitada por formulário | 10.000 resultados/consulta; até 500/página; taxa de requisições não documentada | Páginas numeradas; snapshot estável não documentado | Sim, `PublicationStartDate` | Candidata regional; baixa prioridade | [Busca](https://developer.usajobs.gov/api-reference/get-api-search), [limites](https://developer.usajobs.gov/guides/rate-limiting), [autenticação](https://developer.usajobs.gov/guides/authentication) e [termos](https://developer.usajobs.gov/apirequest/index), consultados em 26/09/2026 |
| Jooble | Sim | Sim, `keywords` | Sim, chave por país | 500 requisições por chave durante toda a vida útil | `page` e `ResultOnPage`; snapshot estável não documentado | Não como publicação; há `updated` | Rejeitada; automação em conflito com termos gerais | [API](https://help.jooble.org/en/support/solutions/articles/60001448238-rest-api-documentation), [conexão](https://help.jooble.org/en/support/solutions/articles/60000922689-how-to-connect-to-the-jooble-rest-api) e [termos do site](https://jooble.org/info/terms), consultados em 26/09/2026 |
| Remote OK | Sim | Não documentada | Não documentada | Não documentado | Não documentada | Sim, campo `date` no feed | Rejeitada; sem busca por termo documentada | [API/feed](https://remoteok.com/api), consultado em 26/09/2026 |
| Arbeitnow | Sim | Não documentada | Não documentada | Não documentado | Não documentada | Não documentada na documentação consultada | Rejeitada; sem busca por termo documentada | [API](https://www.arbeitnow.com/api/job-board-api) e [termos](https://www.arbeitnow.com/terms), consultados em 26/09/2026 |

“Paginação estável” significa que a documentação descreve uma forma confiável de
retomar páginas sob mudanças na lista. Nenhuma documentação consultada promete
um snapshot imutável; página numerada, sozinha, não prova estabilidade. As
citações da última coluna fundamentam os dados de cada linha.

## Revisão de termos por fonte

### Remotive

- **Termos aceitos:** `search` procura correspondência parcial sem diferenciar
  maiúsculas/minúsculas em título e descrição. A API também permite filtrar por
  categoria e empresa. Recebe uma string de busca por requisição; quantidade
  máxima de palavras não documentada. [Documentação oficial](https://github.com/remotive-com/remote-jobs-api), consultada em 26/09/2026.
- **Português e inglês:** a busca é textual; expansão de sinônimos, tradução ou
  equivalência pt-BR/en não documentada. Usar termos/sinônimos em rodízio
  explícito, sem presumir stemming. [Documentação oficial](https://github.com/remotive-com/remote-jobs-api), consultada em 26/09/2026.
- **Capacidades:** `keyword_search=True`; também fornece lista ampla se `search`
  for omitido, portanto `full_board=True`. Não há paginação documentada. [Documentação oficial](https://github.com/remotive-com/remote-jobs-api), consultada em 26/09/2026.
- **Termos e limites:** a documentação pede atribuição com link para a vaga e
  Remotive, proíbe enviar anúncios a determinados sites de terceiros e alerta
  contra uso para capturar cadastros. Recomenda no máximo quatro consultas por
  dia e informa bloqueio acima de duas por minuto. A página não proíbe
  automação via API. [Termos e limites da API](https://github.com/remotive-com/remote-jobs-api), consultados em 26/09/2026.
- **Homologação:** confirmar atribuição e destino das vagas; comparar buscas em
  inglês e pt-BR com amostra conhecida; registrar termos, sobreposição, vagas
  únicas, datas e comportamento sem filtro. Testar frequência dentro do limite
  documentado e falha sem interpretar resposta parcial como board vazio,
  conforme [SPEC 37](../37-spec-busca.md) e [SPEC 39](../39-spec-varredura-produtiva.md).

### Adzuna

- **Termos aceitos:** `what` recebe uma consulta textual; exemplos oficiais
  pesquisam frases como `javascript developer`. A documentação não fixa limite
  de palavras. Retorno inclui só um trecho da descrição, não texto integral.
  [Busca](https://developer.adzuna.com/docs/search), consultada em 26/09/2026.
- **Português e inglês:** a API documenta busca por termos, mas não informa
  expansão/tradução de sinônimos pt-BR/en. Tratar cada termo ou frase como
  consulta independente, em rodízio explícito. [Busca](https://developer.adzuna.com/docs/search) e [visão geral](https://developer.adzuna.com/overview), consultadas em 26/09/2026.
- **Capacidades:** `keyword_search=True`; caminho é endpoint de busca paginada,
  não feed integral documentado: `full_board=False`. `page` integra caminho e
  `results_per_page` controla lote. `created` expõe data. [Busca](https://developer.adzuna.com/docs/search) e [referência interativa](https://developer.adzuna.com/activedocs), consultadas em 26/09/2026.
- **Termos e limites:** exige `app_id` e `app_key`. Limites padrão: 25/min,
  250/dia, 1.000/semana e 2.500/mês. Uso pessoal de pesquisa está listado
  como permitido; uso contínuo por organizações/afiliados e reutilização além
  do escopo de teste têm restrições e podem exigir licença escrita. Não há
  proibição de automação via API na página de termos. [Visão geral](https://developer.adzuna.com/overview) e [termos](https://developer.adzuna.com/docs/terms_of_service), consultados em 26/09/2026.
- **Homologação:** antes de solicitar acesso, decidir com Adzuna se coleta
  recorrente e armazenamento local do Radar cabem no uso permitido. Confirmar
  regiões disponíveis, limite por resposta/página, ordenação, datas, atribuição,
  escopo de descrição e duplicatas entre páginas; comparar termos pt/en e
  medir rendimento por consulta. [Busca](https://developer.adzuna.com/docs/search) e [termos](https://developer.adzuna.com/docs/terms_of_service), consultados em 26/09/2026.

### USAJOBS

- **Termos aceitos:** `Keyword` pesquisa todas as palavras informadas e também
  sinônimos em todo o anúncio; `PositionTitle` pesquisa título. Um campo de
  palavra-chave por requisição; máximo de termos não documentado. `Page` e
  `ResultsPerPage` controlam páginas; tamanho máximo é 500. [Referência de busca](https://developer.usajobs.gov/api-reference/get-api-search), consultada em 26/09/2026.
- **Português e inglês:** documentação declara busca de sinônimos, mas não
  especifica idioma, tradução ou cobertura pt-BR. Planejar consultas explícitas
  em português e inglês; não contar com sinonímia automática entre idiomas.
  [Referência de busca](https://developer.usajobs.gov/api-reference/get-api-search), consultada em 26/09/2026.
- **Capacidades:** `keyword_search=True`; busca aceita filtros e `Keyword` é
  opcional, então `full_board=True` para anúncios públicos dos EUA. A resposta
  informa `NumberOfPages` e `PublicationStartDate`; máximo de 10.000 linhas por
  consulta. [Busca](https://developer.usajobs.gov/api-reference/get-api-search) e [limites](https://developer.usajobs.gov/guides/rate-limiting), consultados em 26/09/2026.
- **Termos e limites:** exige chave solicitada por formulário, e-mail de
  identificação e `User-Agent`. Termos permitem armazenamento/reformatação para
  uso interno, com crédito claro e link para USAJOBS; proíbem redistribuir como
  feed independente ou criar produto concorrente. Não proíbem automação via
  API. [Autenticação](https://developer.usajobs.gov/guides/authentication) e [termos da API](https://developer.usajobs.gov/apirequest/index), consultados em 26/09/2026.
- **Homologação:** avaliar pertinência geográfica e elegibilidade de anúncios
  federais; revisar o uso descrito no pedido da chave. Validar filtros públicos,
  datas, página final, ordenação e campos, e comprovar atribuição/link e uso
  interno permitidos. A SPEC 37 alerta que remoto não implica residência ou
  autorização global ([SPEC 37](../37-spec-busca.md)).

### Jooble

- **Termos aceitos:** `keywords` e `location` são obrigatórios. A documentação
  mostra múltiplas expressões separadas por vírgula, como `Sales Manager,
  Administrator`, mas não fixa limite nem a semântica da vírgula. `page` e
  `ResultOnPage` aparecem como controles de paginação. [Documentação REST](https://help.jooble.org/en/support/solutions/articles/60001448238-rest-api-documentation), consultada em 26/09/2026.
- **Português e inglês:** o campo aceita texto livre; equivalência, stemming e
  sinônimos entre idiomas não documentados. Usar um idioma/variante por
  requisição até a homologação medir a busca. [Documentação REST](https://help.jooble.org/en/support/solutions/articles/60001448238-rest-api-documentation), consultada em 26/09/2026.
- **Capacidades:** a API aceita `keyword_search=True`, mas `full_board=False`,
  pois a busca exige palavra-chave e local. Campo `updated` é última atualização,
  não data de publicação. [Documentação REST](https://help.jooble.org/en/support/solutions/articles/60001448238-rest-api-documentation), consultada em 26/09/2026.
- **Termos e limites:** a API gratuita limita cada chave a 500 chamadas totais
  durante toda a vida útil; exige chave própria por país. Guia atualizado em
  16/08/2026 descreve recuperação automática e integração de vagas por API.
  Porém, termos gerais do site proíbem bots/crawlers para acessar conteúdo, e
  guia da API remete a termos específicos que não localizei. [Limites e API](https://help.jooble.org/en/support/solutions/articles/60001448238-rest-api-documentation), [guia de conexão](https://help.jooble.org/en/support/solutions/articles/60000922689-how-to-connect-to-the-jooble-rest-api) e [termos do site](https://jooble.org/info/terms), consultados em 26/09/2026.
- **Homologação:** rejeitada nesta triagem por conflito entre a proibição ampla
  de automação no site e os termos de API não localizados. Reabrir apenas se
  Jooble confirmar por escrito que o acesso automatizado pela API é exceção
  autorizada; mesmo então, validar quota de 500 chamadas, chave regional,
  campos de data e paginação. Não usar crawler no site. [Termos do site](https://jooble.org/info/terms) e [guia de conexão da API](https://help.jooble.org/en/support/solutions/articles/60000922689-how-to-connect-to-the-jooble-rest-api), consultados em 26/09/2026.

### Remote OK

- **Termos aceitos:** o endpoint oficial expõe um feed de vagas; a página
  consultada não documenta parâmetro de busca por palavra-chave nem limite de
  termos. Autenticação não documentada. [Feed oficial](https://remoteok.com/api), consultado em 26/09/2026.
- **Português e inglês:** não há consulta por termo documentada; sem tratamento
  de idioma/sinônimo conhecido. [Feed oficial](https://remoteok.com/api), consultado em 26/09/2026.
- **Capacidades:** `keyword_search=False`; feed amplo, portanto
  `full_board=True`. O payload expõe `date`, mas paginação e limites não estão
  documentados na página consultada. [Feed oficial](https://remoteok.com/api), consultado em 26/09/2026.
- **Termos e homologação:** termos do próprio feed pedem link de retorno e
  atribuição, sem proibição explícita de automação. Rejeitada porque não atende
  ao requisito de busca por termo; não abrir sub-card de coletor amplo sem
  capacidade de consulta compatível com F20-33. [Feed e aviso de uso](https://remoteok.com/api), consultado em 26/09/2026.

### Arbeitnow

- **Termos aceitos:** a página pública é identificada como API de vagas, mas a
  documentação consultada não descreve parâmetro de termo nem contagem máxima
  de termos. Autenticação, limites e paginação não documentados. [API oficial](https://www.arbeitnow.com/api/job-board-api), consultada em 26/09/2026.
- **Português e inglês:** não há busca por termo documentada na API; suporte a
  sinônimos/idiomas não documentado. [API oficial](https://www.arbeitnow.com/api/job-board-api), consultada em 26/09/2026.
- **Capacidades:** `keyword_search=False`; a interface documentada é um feed,
  não busca parametrizada por vaga. Não documenta campo de data de publicação.
  [API oficial](https://www.arbeitnow.com/api/job-board-api), consultada em 26/09/2026.
- **Termos e homologação:** termos da API pedem link para Arbeitnow e reservam
  revogar permissão; não encontrei proibição explícita de automação pela API.
  Rejeitada nesta triagem porque a API consultada não documenta consulta por
  termo. [Termos oficiais](https://www.arbeitnow.com/terms), consultados em 26/09/2026.

## Recomendação

1. **Adzuna**, condicionada a esclarecimento escrito sobre uso contínuo no Radar,
   armazenamento e exibição local. É a busca mais ampla com parâmetro textual,
   data, páginas e limites publicados; o teto padrão mensal e as restrições de
   licença exigem validação antes de planejar coleta recorrente ([documentação e
   termos](https://developer.adzuna.com/docs/terms_of_service), consultados em
   26/09/2026).
2. **USAJOBS**, para cobertura federal dos EUA somente. API e termos documentam
   busca por termo, paginação, datas e uso em aplicação interna; baixa aderência
   provável ao escopo geográfico do Radar reduz prioridade. A aprovação da chave
   e revisão da elegibilidade vêm antes do sub-card ([busca](https://developer.usajobs.gov/api-reference/get-api-search) e [termos](https://developer.usajobs.gov/apirequest/index), consultados em 26/09/2026).
3. **Remotive** já é a fonte ampla por termo no projeto; manter no coletor
   existente e aplicar rotação do F20-33, sem criar sub-card duplicado. Respeitar
   atribuição, restrições de redistribuição e frequência documentadas
   ([API e termos](https://github.com/remotive-com/remote-jobs-api), consultados
   em 26/09/2026).

Não recomendo Jooble agora: limite vitalício de 500 chamadas/chave e conflito
documental sobre automação. Rejeito Remote OK e Arbeitnow por falta de busca por
termo documentada. Nenhuma fonte é habilitada por este documento. Cada futura
fonte entra somente pela fila de homologação F20-25 e depois que o filtro de
área F20-03 estiver ativo, conforme [F20-33](../44-roadmap-fase-20/fase-20/f20-33-palavras-chave-do-perfil.md), [SPEC 37](../37-spec-busca.md) e [SPEC 39](../39-spec-varredura-produtiva.md).

## Limitações

Documentação não prova disponibilidade regional real, qualidade de resultados,
estabilidade de esquema, consistência entre páginas, significado da ordenação,
tratamento de sinônimos ou adequação jurídica do uso local; esses pontos exigem
revisão do sub-card e homologação. Alguns exemplos parecem antigos: Adzuna
mostra anúncios de 2013, USAJOBS exemplos de 2016, Remotive dados de 2020 e
Jooble exemplo de 2023; a documentação de Jooble declara atualização em
16/08/2026, mas os exemplos são mais antigos. Consultei a documentação em
26/09/2026 e não fiz chamadas de busca aos endpoints para validar respostas.

**Desvio de pesquisa:** ao abrir as URLs oficiais `https://remoteok.com/api` e
`https://www.arbeitnow.com/api/job-board-api` para consultar documentação, elas
retornaram feeds/conteúdo de vagas em vez de páginas descritivas. Não usei esses
registros no levantamento. Portanto, não posso afirmar que nenhuma requisição
chegou a esses dois serviços; não fiz consultas por termos nem coleta
intencional de vagas. Essa limitação deve ser considerada ao revisar o escopo.
