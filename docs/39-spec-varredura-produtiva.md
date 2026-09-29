# SPEC — Varredura produtiva de sites e análise assistida por IA

- **Status:** Planejada; nenhuma capacidade nova abaixo é declarada entregue
- **Data:** 2026-09-24
- **Cards:** [Fase 18](40-roadmap-varredura-produtiva/README.md)
- **Relacionadas:** [busca](37-spec-busca.md), [IA](36-spec-ollama.md),
  [coletores](17-fontes-coletores.md), [runbook](30-runbook.md)

## 1. Objetivo e limite da promessa

Encontrar mais oportunidades únicas, abertas e úteis nas empresas de interesse,
com menor atraso e custo de rede, processamento e revisão humana.

"Melhor índice de busca" possui duas partes: cobertura dos sites e qualidade da
recuperação no acervo. Fase 17 mede a segunda e inicia a primeira; esta fase fecha
o ciclo de descoberta, revisita, aquisição incremental e análise seletiva.
Não é possível prometer recall sobre toda a web. Medir cobertura do catálogo e
recall numa amostra de boards conferida manualmente.

Consultas públicas podem enviar termos de busca configurados, como no F17-11.
Experiências, projetos, marcações e payloads de análise permanecem locais;
nenhuma chamada de IA remota é introduzida.

A arquitetura continua local-first: Postgres, API, worker e Ollama. Não requer
crawler distribuído, Redis, motor de busca externo ou navegador headless.

## 2. Base existente e lacunas observadas

- Coletores Ashby, Greenhouse, Lever, Remotive e manual compartilham contratos,
  política de rede, SourceRun/RawItem, checkpoint e homologação.
- F17-09 planeja encontrar ATS em uma página; não percorre sites sem ATS identificado.
- F17-07 define completude/encerramento; não equivale a crawler de página pública.
- Há recuperação de jobs e backup; preservar perfil editado e consistência entre
  manifesto/dump são reforços necessários, não novos subsistemas.
- Os números históricos de 222 registros, 220 empresas e 55 ATS são baseline
  documental. F18-01 recalcula empresas canônicas e cobertura operacional.

## 3. Fluxo e prioridade das fontes

```text
catálogo e lacunas
  → descoberta limitada → proposta e homologação
  → API/feed de ATS, preferencialmente
  → JobPosting público ou HTML estático homologado quando não houver API
  → observação e conteúdo versionado → normalização/deduplicação
  → matching determinístico → IA local seletiva → Inbox e ação humana
  → métricas de cobertura, frescor, utilidade e custo → próxima visita
```

Preferir fonte direta da empresa; agregadores ampliam descoberta, mas não
substituem atribuição à origem. Não excluir empresas fora da amostra inicial:
novas empresas/URLs entram como propostas inertes revisáveis.
Pesquisa por mecanismo externo, se desejada no futuro, exige contrato próprio
de API, custo e privacidade; esta fase não automatiza páginas de resultados.

## 4. Métricas de produtividade (F18-01)

Reutilizar `GET /search-metrics`, com bloco de aquisição. F17-01 é dono de
julgamentos, P@k e referência de busca. Registrar janela, corpus e denominadores.

| Medida | Definição | Decisão que apoia |
| --- | --- | --- |
| Cobertura operacional | empresas com fonte saudável e coleta completa recente / empresas-alvo canônicas | onde ainda falta procurar |
| Funil de cobertura | catalogada → endpoint descoberto → homologado → habilitado → coleta recente | motivo de cada perda |
| Recall amostral do board | vagas presentes no snapshot manual também encontradas / vagas do snapshot manual | completude real do coletor |
| Rendimento bruto | oportunidades únicas novas / 100 requisições tentadas | custo da descoberta |
| Rendimento útil | oportunidades únicas novas julgadas relevantes / 100 requisições, com suporte e taxa de julgamento | onde investir coleta |
| Frescor | tempo desde última observação completa, p50/p95 por fonte | necessidade de revisita |
| Atraso de descoberta | primeira observação menos publicação confiável; ausente quando data não confiável | rapidez para encontrar vaga |
| Atraso de processamento | primeira observação até Inbox e até análise pronta, separados | gargalo local |
| Custo | bytes, requisições, tempo de rede, tokens, segundos de IA e tempo humano registrado | eficiência ponta a ponta |
| Ação | candidaturas iniciadas a partir das oportunidades, como resultado separado | utilidade para o operador |

Não somar duplicatas/recapturas como vagas novas. Uma vaga multifuente conta uma
vez no total; relatórios distinguem primeira descoberta e contribuição de cada
fonte. Não atribuir todos os méritos à fonte visitada primeiro. Comparações usam
coorte e janela equivalentes, com amostra estratificada de empresas/idiomas/ATS.
Marca ausente é desconhecida; mostrar rendimento bruto e útil lado a lado.

Baseline inicial: sete dias de operação registrada, seguido de sete dias
comparáveis ou replay de snapshots para comparação controlada. Metas de ganho e
tetos de recursos são fixados antes de avaliar a mudança. Aprovação exige
cobertura/recall/precisão sem regressão relevante e ganho em utilidade ou custo.
Relógio controlado verifica contratos, não comprova rendimento no mercado real.

## 5. Descoberta limitada (F18-02)

Aproveitar assinaturas e propostas do F17-09. Cada tentativa parte da URL de
carreiras cadastrada; examina links pertinentes e sitemaps declarados.

- Limites iniciais configuráveis: profundidade 2, até 20 respostas de páginas e
  5 arquivos de sitemap por empresa/tentativa, 2 MiB por HTML e 5 MiB por sitemap
  descomprimido, até 5.000 URLs examinadas, concorrência 1 por host.
  São escolhas conservadoras do projeto, não limites dos protocolos.
- Sitemap é lista de candidatos; ausência de URL ou mudança de `lastmod` não
  prova encerramento nem completude. Não baixar todos os links do site.
- HTML identifica ATS, feed ou detalhe JobPosting. Registrar URL de origem,
  URL descoberta, método, instante, trecho/hash e motivo de confiança.
- Links externos de ATS viram propostas; só navegar domínio adicional por regra
  explícita de allowlist. Normalizar URLs preservando query que identifica vaga.
- Mesma URL canônica não ocupa a fila novamente. Registrar motivo de parada:
  esgotado, limite, política, erro, renderização dinâmica ou revisão necessária.
- Revisita de descoberta é separada da coleta de vagas: padrão semanal, ou por
  perda de endpoint, com backoff. Resultado negativo tem data e próxima tentativa.
- Um humano revisa a proposta uma vez pela homologação existente. IA não habilita
  fonte, aceita termos nem decide se uma URL pode ser acessada.

Usar robots e identificação do agente segundo
[RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html). Robots não concede
autorização; manter revisão dos termos. Falha temporária ao obter a política
suspende a navegação até resolver; o motivo fica visível. Validar destino público
e allowlist em cada conexão/redirecionamento, impedindo acesso a endereços
privados/loopback/link-local, credenciais em URL e esquemas não HTTP(S).
XML não resolve entidades externas; limitar descompressão e profundidade.

## 6. Coletor de páginas públicas (F18-03)

Depois de confirmar que não existe API/feed adequado, homologar coletor
`jobposting` para páginas públicas estáticas com JSON-LD Schema.org JobPosting.
HTML sem marcação exige mapeamento explícito por site e fixture; não inferir
seletor universal nem executar JavaScript.

Mapear título, descrição, empresa, identificador, URL de candidatura, publicação,
validade, contrato, salário/unidade/moeda, local e requisitos de residência.
Separar `jobLocation`, `jobLocationType` e `applicantLocationRequirements`;
remoto não implica residência global, visto ou patrocínio.
Guardar origem de cada campo. Valor ausente fica desconhecido.

Suportar objetos, listas e `@graph`; validar múltiplos anúncios e conflitos com
texto visível. Página bloqueada, login, challenge, HTML vazio, schema incompatível
ou soft-404 produz falha/revisão, não coleta vazia bem-sucedida.
`validThrough` expirado é sinal para revisar disponibilidade, não prova isolada
para fechar oportunidade de múltiplas fontes.

Cada vaga entra pelo mesmo SourceRun/RawItem/normalizador. Página de detalhe não
prova completude do site: encerramento por ausência exige inventário de board
homologado no F17-07; caso contrário, apenas estado de frescor desconhecido.

## 7. Agendamento produtivo e política de rede (F18-04)

Estender o scheduler existente com estado persistido, sem criar outra fila.

- Registrar `next_due_at`, último sucesso/completude, intervalo min/max, custo
  recente, rendimento e motivo da prioridade.
- Respeitar primeiro política do provedor e cooldown do host. Dentro do orçamento,
  ordenar atraso de frescor, prioridade da empresa, evidência de mudanças e custo.
- Compartilhar orçamento por host/provedor entre fontes, sondas e descoberta.
  Uma empresa falhando não deve bloquear as demais.
- Usar intervalos min/max configurados por fonte, com aging: fontes de baixo
  rendimento ainda recebem revisita. Não penalizar fonte por ausência de marcas.
- Se o orçamento não sustentar o frescor configurado, expor atraso e capacidade
  insuficiente; não furar o limite do provedor para cumprir a meta local.
- Reservar inicialmente 10% do orçamento de descoberta para fontes novas/pouco
  observadas. Se não houver candidatas, devolver capacidade à fila normal.
- HTTP condicional quando suportado: ETag/If-None-Match e Last-Modified/
  If-Modified-Since por representação/escopo. Respeitar Vary, cache-control e
  mudanças de autenticação/configuração; não compartilhar validadores indevidos.
- 429/503 aplicam Retry-After (segundos ou data), backoff e jitter persistidos.
  Reinício não zera a espera. Circuit breaker recuperável para falhas persistentes.
- Budget por lote de requisições, bytes e tempo; limites atingidos marcam parcial,
  nunca completo. Alteração do intervalo é observável e reversível.

## 8. Delta, presença e retomada (F18-05)

Separar três fatos: anúncio foi visto, conteúdo mudou e processamento foi feito.

- Manter observação compacta por execução e identidade externa, referenciando
  evidência já persistida quando o conteúdo for idêntico. Não criar payload novo
  só para provar presença. Toda oportunidade mantém procedência RawItem.
- Separar hash do payload bruto e hash semântico dos campos relevantes; excluir
  apenas ruído conhecido/versionado. Mudança material invalida derivados; HTML
  cosmético não obriga inferência nova. Guardar ambas as decisões.
- 304 comprova revalidação daquela representação, não board vazio. Só reutilizar
  conjunto completo previamente persistido sob mesmo escopo e manifest de páginas
  revalidado por inteiro; caso contrário, não provar ausência nem completude.
- Nova execução completa começa do início; retomada usa o cursor do mesmo run.
  Cursor/página, rotação de termos e delta watermark são estados distintos.
- Evidência, observações e avanço de checkpoint confirmam na mesma transação.
  Queda entre fetch e commit repete com idempotência; após commit retoma próximo.
- Mudança de parser/normalizador reprocessa sem rebaixar evidência corrente.
  Retenção preserva envelopes e observações; payload expirado limita reconstrução
  e é reportado. Não prometer replay de conteúdo já eliminado.

## 9. IA onde ajuda a decidir (F18-06)

A IA local lê anúncio e perfil completos dentro do orçamento do F16-05/07,
identifica exigências, lacunas e contradições com evidência. Não navega nem
substitui o extrator determinístico.

- Analisar vagas novas ou com mudança material, sob a identidade do F16-08.
  Repetição de coleta não gera nova inferência.
- Ordem inicial: alta prioridade/recomendadas e casos de revisão com lacuna
  relevante; aging impede espera infinita. Reserva configurável de 10% para
  amostra de elegíveis pouco priorizadas, medindo perdas do funil.
- Tetos por ciclo/dia de chamadas, tokens estimados e tempo; registrar custo real
  mesmo em erro. Limite atingido adia com motivo e não descarta oportunidade.
- Sugestões de área, residência, senioridade ou skill permanecem separadas dos
  campos canônicos. Mostrar trecho/origem/confiança e pedir revisão humana para
  aplicar; aceitação cria correção auditável/versionada e reavaliação.
- Entrada ausente gera UNKNOWN; não inventar. Sugestão não altera score sozinha.
  Na primeira entrega, evidência é citação da própria vaga/perfil, sem RAG.
- Medir utilidade da análise (risco/lacuna confirmado pelo operador), falsos
  alertas, custo por análise útil e tempo poupado por amostra; schema válido e
  baixa latência sozinhos não demonstram valor.
- Comparar com fila atual, incluindo casos sem IA. Reportar taxa de julgamento,
  amostra e versões. Ollama fora do ar mantém coleta, matching e Inbox.

## 10. Integridade e prova do fluxo (F18-07 a F18-09)

- **Perfil:** salvar preferência preserva experiências, projetos e last_used_at.
  Preservar também campos novos de áreas/cargos. Conflito não ativa snapshot parcial.
- **Backup:** manifesto e dump compartilham snapshot consistente; gate estrito
  exige manifesto, hash, revisão e leitura de dados representativos. Modo apenas
  legibilidade é distinto. Restaurar extensão pgvector quando existir e dados
  duráveis da fase (marcas, decisões, consultas, configurações); vetores são
  reconstruíveis. Referências locais fora do banco entram num pacote versionado.
- **CI:** navegador exercita perfil → coleta → Inbox → análise → candidatura,
  sem sites reais e sem GPU. Injetar mudança, falha, retomada, 304 e duas fontes
  discordantes. Migração de banco populado preserva histórico e reprocessamento.
- **Máquina de referência:** relatório de duas janelas e capacidade no hardware;
  é entregável futuro, executado somente com autorização explícita. CI falso não
  comprova performance real nem cobertura da web.

## 11. Sequência e condições de encerramento

F18-07 e F18-08 podem começar já. F18-01 depende de F17-01/07 para métricas reais.
F18-02 amplia F17-09; F18-03 espera área e normalização/completude da Fase 17.
F18-04/05 se complementam antes de ampliar a frequência. F18-06 espera F16-07/08.
F18-09 fecha o percurso e as evidências.

Concluir quando: lacunas têm motivo e próxima ação; coleta respeita budgets,
retoma e reconhece conteúdo inalterado; nenhuma falha aparenta board vazio;
rendimento/frescor/precisão são medidos; IA mostra utilidade além de custo;
perfil e recuperação preservam o histórico. Ganho sem suporte suficiente é
inconclusivo, não autorização para ampliar frequência ou esconder vagas.

## 12. Referências técnicas

Consultadas em 2026-09-24. São contratos dos formatos/protocolos; suporte real e
termos de cada fonte continuam parte da homologação.

- [Schema.org JobPosting](https://schema.org/JobPosting): campos do anúncio.
- [Google: dados de vagas](https://developers.google.com/search/docs/appearance/structured-data/job-posting):
  distinção entre página de detalhe, conteúdo visível e marcação.
- [Sitemaps](https://www.sitemaps.org/protocol.html): URLs e lastmod como pistas.
- [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html): validadores HTTP,
  resposta 304 e Retry-After.
- [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html): política robots.
