# SPEC — Busca de vagas: cobertura e precisão

- **Status:** Planejada; contratos revisados em 2026-09-24
- **Data:** 2026-09-24
- **Escopo:** o caminho inteiro de "encontrar vagas": catálogo, fontes, coleta,
  normalização, identidade e a busca na Inbox
- **Cards de execução:** [Fase 17](38-roadmap-ia-e-busca/fase-17/README.md)
- **Documentos relacionados:** [SPEC da camada de IA](36-spec-ollama.md),
  [Roadmap de interface](34-roadmap-interface.md), [Matching e scoring](20-matching-scoring.md),
  [Tecnologias](05-tecnologias.md)

---

## 1. Objetivo

"Melhorar a busca" são dois problemas diferentes, com métricas diferentes:

```text
cobertura (quantidade)   das vagas relevantes que existem, quantas o radar encontra
precisão  (acurácia)     das vagas que o radar mostra, quantas são relevantes, únicas e
                         corretamente descritas — e se a busca na Inbox as acha
```

Os dois brigam entre si. Ligar mais fontes aumenta a cobertura e, sem filtro, derruba a
precisão: a Inbox enche de vendas, marketing e duplicatas. Por isso esta SPEC trata as duas
frentes juntas e mede cada uma antes de mexer.

O caminho que uma vaga percorre, e onde cada perda acontece:

```text
catálogo de empresas ─► fontes ─► coleta ─► normalização ─► identidade ─► matching ─► Inbox
      (quem olhar)    (por onde) (quanto)   (o que é)     (é a mesma?)  (serve?)   (achar)
       cobertura      cobertura  cobertura   precisão      precisão     precisão  precisão
```

---

## 2. Estado verificado

Baseline histórico contra código e pesquisa em 24 de setembro de 2026. Os números do
catálogo foram contados com o próprio parser do importador
(`scripts/import_research_catalog.py`, `read_research_rows`).

### 2.1 Cobertura

| Ponto | Hoje | Onde |
| --- | --- | --- |
| Empresas no catálogo | 222 | `docs/pesquisas/*.md` |
| Com ATS identificado | 55 — Ashby 29, Greenhouse 9, Lever 5, Workday 4, Teamtailor 3, Factorial 2, Workable 2, Gupy 1 | idem |
| Só página de carreiras | 115 | idem |
| Em backlog de pesquisa | 52 | idem |
| **Viram fonte** | **6** + Remotive = 7 | `import_research_catalog.py:65-86` |
| Ashby "ATS identificado" sem fonte | 25 (8 com link do board na pesquisa) | idem |
| Coletores | Ashby, Greenhouse, Lever (board inteiro da empresa), Remotive (por palavra-chave), manual | `acquisition/*.py` |
| ATS sem coletor | Workday, Teamtailor, Workable, Factorial, Gupy — 12 empresas | — |
| Palavras-chave da Remotive | estáticas, em `configuration["keywords"]` | `worker.py:356` |
| Medição de cobertura | nenhuma | — |

O gargalo de quantidade não está na coleta, está antes dela. O importador só transforma em
fonte o registro com **API JSON confirmada** (qualquer ATS) ou **Greenhouse** com ATS
identificado e chave (`import_research_catalog.py:69-82`). As 25 empresas Ashby e as Lever
com ATS identificado ficam no catálogo sem fonte. O radar olha 6 das 55 empresas que ele já
sabe onde procurar.

### 2.2 Precisão

| Ponto | Hoje | Onde |
| --- | --- | --- |
| Filtro por área da vaga | nenhum: o board inteiro entra, de engenharia a vendas | coletores |
| Departamento | coletado (Ashby `department`, Greenhouse `departments`) e **não usado** | `ashby.py:278`, `greenhouse.py:310` |
| Senioridade | só do título, ou de metadado da entrada manual; nenhum ATS contribui | `opportunities/domain.py:791` (`seniority-v1`) |
| Taxonomia de skills | 27 entradas (`skills-v1`) | `opportunities/domain.py` |
| Identidade | fingerprint exato que inclui o **dia da publicação** | `opportunities/domain.py:876` |
| Busca na Inbox | `LIKE` em título e empresa; sem descrição, sem radical, sem sinônimo | `dashboard/queries.py:345` |
| Medição de precisão | nenhuma | — |

Três consequências:

- **Mais fontes hoje piorariam a Inbox.** Sem classificar a área da vaga, cada board novo
  traz todas as vagas da empresa. O departamento, que resolveria boa parte disso, já chega
  no `RawItem` e é descartado.
- **A mesma vaga pode aparecer duas vezes.** O fingerprint inclui o dia da publicação, de
  propósito, para não juntar republicações antigas. O efeito colateral é que a mesma vaga
  anunciada em duas fontes em dias diferentes vira duas oportunidades.
- **A busca não acha o que está no texto.** "Kubernetes" ou "remoto LATAM" só aparecem na
  descrição, e a busca não olha a descrição.

---

## 3. Métricas e metas

Nenhuma dessas métricas existe hoje. A primeira entrega (F17-01) cria a medição e registra o
valor inicial; as metas marcadas "a partir do inicial" são fixadas nesse momento, não antes.

| Métrica | Definição | Hoje | Meta |
| --- | --- | --- | --- |
| Empresas com ATS cobertas | empresas canônicas com coleta completa recente ÷ empresas canônicas com ATS identificado, inclusive sem coletor | 6/55 é apenas referência histórica de propostas; cobertura operacional a medir | até 43/55 com coletores existentes e 50/55 com novos, condicionados à homologação |
| Empresas sem ATS conhecido | só página de carreiras ou backlog | 167 | −30% pela descoberta de ATS (§5) |
| Vagas relevantes novas por semana | oportunidades únicas, novas, abertas e julgadas relevantes; área é indicador separado | não medida | meta após baseline; 5× é hipótese, sem piorar precisão ou custo |
| Precisão da Inbox | relevantes no snapshot das 50 primeiras com julgamento completo | não medida | ≥ 80%; sem 50 disponíveis, P@k com k explícito |
| Duplicatas entre fontes | pares da mesma vaga em oportunidades diferentes, em amostra | não medida | < 2% |
| Senioridade desconhecida | oportunidades com `UNKNOWN` | não medida | metade do inicial |
| Área da vaga desconhecida | oportunidades sem área classificada | não existe | < 10% |
| Recall de skills | skills de um conjunto marcado que a extração encontra | não medido | ≥ 90% |
| Busca: recall@10 | relevantes recuperadas ÷ relevantes julgadas no corpus congelado, por consulta | não medido | melhoria sobre baseline; ≥ 0,8 só em consultas cujo máximo teórico permita |
| Vaga encerrada detectada | vagas que saíram do board e foram marcadas como encerradas | não medida | ≥ 95% em até 2 ciclos |

---

### 3.1 Contrato das medidas

- Contar empresas canônicas, reconciliando os 222 registros e os aliases antes de
  fixar denominadores. Separar catálogo total, ATS identificado, coletor disponível,
  homologação, habilitação e coleta completa dentro da janela de frescor.
- Fonte habilitada sem sucesso recente não conta como cobertura operacional.
  Denominadores e versão do catálogo acompanham cada relatório.
- P@50 exige julgar todo o top 50 congelado. Julgamento parcial mostra taxa observada,
  quantidade pendente e `precision_at_50 = null`; ausência de marca não é irrelevância.
- Julgar também amostra estratificada fora do topo, por fonte/área/idioma e UNKNOWN.
  Pares suspeitos estimam duplicação entre candidatos, não a taxa global do acervo.
- Fixar consultas, corpus, filtros, perfil, regras, ranking e julgamentos; separar
  ajuste e avaliação reservada. Com mais de 12 relevantes, recall@10 não pode chegar
  a 0,8. Reportar P@10, nDCG@10, recall e tamanho do conjunto relevante juntos.
- Métricas ainda sem instrumentação ficam nulas com motivo e card responsável.
  F17-01 entrega infraestrutura e baseline disponível; cada card posterior mede sua
  parte antes/depois, sem depender de um baseline impossível de todas as funções.
- O recall da web inteira é desconhecido. F18-01 mede cobertura/frescor no catálogo
  e recall em uma amostra manual de boards, sem chamar isso de recall global.

## 4. Frente A — Cobrir o que o catálogo já sabe

É a frente mais barata e a que mais aumenta a quantidade: nenhuma fonte nova, só parar de
descartar o que a pesquisa já encontrou.

- O importador passa a propor fonte para **todo** registro Ashby, Greenhouse ou Lever com
  ATS identificado, não só os com API JSON confirmada.
- Quando a pesquisa tem o link do board e não a chave, a chave é extraída do link por padrão
  explícito por ATS (`jobs.ashbyhq.com/<chave>`, `boards.greenhouse.io/<chave>`,
  `jobs.lever.co/<chave>`) e validada pelo próprio coletor. Link fora do padrão não gera
  chave: vira pendência de pesquisa, com o motivo.
- Toda proposta nasce inerte, como hoje. Quem confirma a evidência é a sonda da F14-06, e
  a sonda em lote pelo script (`enable_sources.py`) cobre as dezenas de propostas de uma
  vez, com o mesmo espaçamento e o mesmo registro por tentativa.
- A tela de fontes ganha a visão "propostas sem sonda" para o operador revisar termos e
  habilitar em sequência, sem abrir fonte por fonte.

**Resultado esperado:** de 6 para até 43 empresas cobertas com o código de coleta que já
existe, sem afrouxar nenhum gate.

---

## 5. Frente B — Descobrir o ATS de quem só tem página de carreiras

115 empresas têm página de carreiras confirmada e nenhum ATS conhecido. Muitas dessas
páginas são uma casca em volta de um board Ashby, Greenhouse, Lever, Gupy ou Teamtailor.

- Um passo de descoberta faz **uma** requisição à página de carreiras registrada e procura
  assinaturas conhecidas no HTML: URLs de board, scripts de embed e iframes de cada ATS.
- O que encontra vira `CompanySource` com `verification_method = "discovery"`, a URL e o
  trecho do HTML como evidência, no mesmo formato da F14-05. A proposta de fonte continua
  passando pela sonda e pela homologação.
- A descoberta é pesquisa, não coleta: respeita `robots.txt`, identifica o agente, roda sob
  demanda ou em lote agendado de baixa frequência, e nunca segue links para dentro do site.
- Página que não revela ATS fica registrada com a data da tentativa, para não ser
  consultada de novo antes do intervalo configurado.

---

## 6. Frente C — Coletores novos, por demanda medida

A ordem sai do catálogo, não de preferência: quantas empresas do radar cada ATS destrava.

| ATS | Empresas no catálogo hoje | Observação |
| --- | --- | --- |
| Workday | 4 | endpoint de busca por tenant; paginação própria |
| Teamtailor | 3 | board público por empresa |
| Workable | 2 | widget público por conta |
| Factorial | 2 | página pública por empresa |
| Gupy | 1 | pouco no catálogo, muito no mercado brasileiro; reavaliar após a Frente B |

Cada coletor novo:

- passa por revisão dos termos de uso do endpoint público **antes** de ser escrito, com o
  resultado registrado — endpoint que proíbe acesso automatizado não entra;
- nasce com a mesma interface dos atuais (`discover`, `CollectorCapabilities`, telemetria,
  política de rede) e com um board falso nos testes, como `tests/e2e/fake_job_board.py`;
- entra no `PROBE_TYPES` da sonda e no `IDENTIFIER_KEYS` das propostas;
- tem a ordem refeita depois da Frente B: se a descoberta revelar 20 empresas em Gupy, Gupy
  passa na frente.

---

## 7. Frente D — Fontes amplas, guiadas pelo perfil

A Remotive é a única fonte que busca por palavra-chave, e as palavras são fixas na
configuração.

- As palavras-chave passam a vir do perfil ativo: cargos-alvo declarados e as skills de
  maior peso. Mudar o perfil muda a busca na próxima coleta, sem editar fonte.
- O limite de 10 palavras por requisição (`CollectionRequest`) vira rotação: cada coleta
  usa um subconjunto, e o ciclo cobre o conjunto inteiro.
- Outras fontes amplas com API pública e busca por termo entram como candidatas, cada uma
  sujeita à mesma revisão de termos da Frente C. A lista de candidatas é trabalho de
  pesquisa, registrado em `docs/pesquisas/`, não uma decisão desta SPEC.
- Fonte ampla traz muito ruído por natureza. Ela só é habilitada depois da Frente F, que é o
  que impede esse ruído de chegar à Inbox.

---

## 8. Frente E — Coleta completa e vagas encerradas

- Execução completa exige fim de paginação comprovado, sem limite de itens/páginas
  atingido e sem erro. Total anunciado é opcional: contar a própria lista não
  comprova cobertura independente. Detectar cursor repetido e itens únicos.
- Persistir conjunto observado e assinatura do escopo (board, filtros, configuração).
  Checkpoint de retomada de uma execução não é o início de uma nova varredura completa.
- Duas ausências em coletas completas comparáveis encerram a ocorrência da fonte.
  Falha, parcial, filtro novo ou fonte desabilitada não contam como ausência.
- Oportunidade agregada só recebe encerramento automático quando todas as ocorrências
  autoritativas de board estão encerradas e nenhuma outra tem presença posterior.
  Sem fonte autoritativa, apenas desatualizada/desconhecida. Remotive e manual não
  provam ausência global. Guardar execuções e motivo.
- Reaparecimento reativa ocorrência; só desfaz encerramento automático. Não desfaz
  descarte, arquivamento ou fechamento manual. Candidatura ativa recebe aviso,
  preservando o estágio e o histórico.
- Agendamento respeita os limites por fonte. Orçamento por host e adaptação pela
  produtividade entram em F18-04, sem duplicar a lógica do scheduler.

---

## 9. Frente F — Área da vaga: precisão na entrada

É a frente que permite as Frentes A, C e D sem inundar a Inbox.

- **Classificação de área** como campo novo da normalização (`role_family`, versionado como
  `role-family-v1`): engenharia de software, dados, infraestrutura, produto, design,
  segurança, QA, vendas, marketing, operações, pessoas, finanças, jurídico, suporte, outra.
- A regra é determinística e usa, nesta ordem: o departamento que o ATS informa (hoje
  coletado e descartado), padrões no título em português e inglês, e termos da descrição
  só como desempate. Cada classificação guarda qual evidência decidiu, como a senioridade
  já faz.
- O perfil declara as áreas de interesse. A Inbox mostra essas áreas e `UNKNOWN`
  por padrão, com filtro
  visível para ver as outras. Nada é apagado: vaga fora da área continua no acervo,
  classificada, e pode ser encontrada.
- A área é classificação e filtro, sem novo fator no matching nesta fase.
  Acrescentar fator exige avaliação própria e nova versão de regras.
- Classificação incerta vai para `UNKNOWN`, nunca para a área mais provável.
  Medir precisão por área e falso descarte de relevantes; reduzir UNKNOWN não
  autoriza adivinhar classificações. O filtro permite ver todas as vagas.

---

## 10. Frente G — Busca na Inbox

A busca full-text é desta SPEC. A busca por significado (pgvector) é da
[SPEC da camada de IA](36-spec-ollama.md), §7.4, card F16-10, e usa o mesmo conjunto de
referência abaixo para decidir se vira o padrão da Inbox.

- **Full-text do Postgres:** coluna `tsvector` gerada de título (peso A), empresa (A),
  skills e área (B) e descrição (C), dicionários `portuguese` e `english`, índice GIN.
  Consulta por `websearch_to_tsquery`, ordenação por `ts_rank_cd` quando há termo.
- **Sinônimos do domínio:** um dicionário de sinônimos versionado cobre o que o radical não
  resolve: "desenvolvedor"/"developer"/"engineer", "sênior"/"senior"/"sr",
  "remoto"/"remote", "dados"/"data". Ele mora no repositório e é aplicado na consulta, não
  no índice, para poder mudar sem reindexar.
- **Filtros combináveis:** área, senioridade, modo de trabalho, país permitido, faixa de
  remuneração, empresa, fonte e "publicada nos últimos N dias", junto com o termo.
- **Buscas salvas:** o operador salva uma combinação de termo e filtros, e a Visão geral
  mostra quantas vagas novas cada busca salva teve desde a última visita.
- **Conjunto de referência:** 40 consultas reais com as vagas relevantes marcadas no acervo.
  É o mesmo conjunto que decide o gate da busca semântica, e mede recall@10 e nDCG@10 de
  toda mudança nesta frente.

---

## 11. Frente H — Normalização mais precisa

- **Senioridade `seniority-v2`:** mapeamento por coletor dos campos estruturados que cada
  ATS expõe, quando expõe, antes do título. Padrões de título em português ("Pleno",
  "Júnior", "Especialista") ao lado dos em inglês. Cada campo novo é parte da homologação
  do coletor, como o comentário em `SENIORITY_MAPPING_VERSION` já exige.
- **Skills `skills-v2`:** a taxonomia cresce a partir do que falta de verdade. Um relatório
  lista os termos técnicos mais frequentes nas descrições coletadas que não casam com
  nenhuma entrada, e o crescimento é revisado entrada por entrada, com alias e
  desambiguação, como as 27 atuais.
- **Localização e país permitido:** separar local do escritório, residência permitida,
  autorização de trabalho, patrocínio e fuso. Remoto não implica global. Padrões para
  "Remote — Brazil", "LATAM", "Americas",
  "EMEA", "Anywhere", fuso exigido. Região que inclui o Brasil é resolvida por tabela
  versionada, não por palpite.

---

O reprocessamento do F17-06 deve aplicar regras novas mesmo sem
`source_updated_at`, sem regredir a evidência corrente ao reproduzir itens antigos.
Guardar versão do normalizador e da evidência escolhida; mudança semântica invalida
matching, busca e embeddings. Reexecução sem mudança não aumenta a versão.
Payload expirado gera limitação auditável, não promessa de reconstrução completa.

## 12. Frente I — Identidade entre fontes

- O fingerprint exato continua sendo a identidade forte, com o dia da publicação.
- Acrescenta-se um **candidato a duplicata**: mesma empresa canônica, mesmo título
  normalizado e mesma localização normalizada, publicados dentro de uma janela de 14 dias.
- Quando os embeddings existirem (card F16-09), a similaridade de cosseno acima de um
  limiar alto, na mesma empresa, entra como segundo sinal de candidato — cobre título
  reescrito entre fontes ("Sr. Backend Engineer" e "Senior Software Engineer, Backend").
  O candidato não junta nada sozinho. Ele aparece na Inbox como "possível duplicata de…",
  e o operador confirma ou recusa.
- Confirmação vale para aquele par. Junção automática aprendida fica fora desta fase.
  Se ambas possuem candidatura ativa, bloquear a junção até resolução explícita.
  Operação transacional/idempotente preserva ocorrências, avaliações, marcações,
  histórico e redirecionamento de ids; não transfere score como se fosse atual.
- A taxa de duplicatas (§3) é medida antes e depois, na mesma amostra.

---

## 13. Frente J — Medição

Nada acima é demonstrável sem esta frente, e ela vem primeiro.

- **Marcação de relevância:** na Inbox e no detalhe da vaga, o operador marca "relevante" ou
  "não relevante", com motivo opcional (área, senioridade, local, empresa). A marcação é
  dado de avaliação, não entra no score.
- **Relatório de cobertura** por fonte e por empresa: itens anunciados × lidos, novas
  vagas, vagas encerradas, taxa de descarte na normalização, área e senioridade
  desconhecidas.
- **Relatório de precisão:** precisão das primeiras 50 da Inbox a partir das marcações,
  taxa de duplicatas numa amostra semanal, recall@10 das 40 consultas.
- `GET /search-metrics` e uma linha de apoio na Visão geral, no padrão das métricas por
  fonte que já existem.

---

### 13.1 Relevância aprendida

Experimento opcional F17-13, após as entregas de cobertura e busca textual.
Regressão logística sobre embeddings congelados produz estimativa de interesse;
não altera matching e não esconde oportunidades.

Treinar com marcas do perfil ativo. Separar treino e avaliação por tempo e por
grupo de duplicatas; impedir vazamento entre conjuntos. O mínimo de 60 marcas
permite explorar, não liberar P@50. O gate exige pelo menos 50 oportunidades
independentes julgadas na janela reservada, além do conjunto de treino.
Com menos dados, relatar P@k e manter o modo experimental desligado.

Calibração tem métrica própria (Brier e faixas com suporte). A interface exibe
"estimativa de interesse"; percentual probabilístico só após validação suficiente.
Mudança de perfil/modelo/vetor invalida a estimativa. O relatório registra hash
dos dados, divisão, versões e comparação pareada com a ordem padrão.

## 14. Plano de entrega

Proposta de fase na convenção de `docs/33` e `docs/34`. A ordem mede primeiro, depois
ganha precisão, e só então aumenta o volume.

| Ordem | Card | Frente | Depende de |
| --- | --- | --- | --- |
| 1 | F17-01 — marcação de relevância e relatórios de cobertura e precisão | J | Nenhum |
| 2 | F17-02 — área da vaga (`role-family-v1`) e filtro padrão na Inbox | F | F17-01, F18-07 |
| 3 | F17-03 — busca full-text, sinônimos e filtros combináveis | G | F17-01, F17-02 |
| 4 | F17-04 — importador propõe todo ATS identificado, chave extraída do link | A | Nenhum |
| 5 | F17-05 — visão "propostas sem sonda" e homologação em sequência | A | F17-04, F17-02, F17-07 |
| 6 | F17-06 — senioridade `v2`, skills `v2`, localização e país | H | F17-01 |
| 7 | F17-07 — coleta completa, alerta de paginação e vaga encerrada | E | Nenhum |
| 8 | F17-08 — candidato a duplicata entre fontes | I | F17-01 |
| 9 | F17-09 — descoberta de ATS nas páginas de carreiras | B | F17-04 |
| 10 | F17-10 — coletores novos, na ordem medida após F17-09 | C | F17-09, F17-02, F17-06, F17-07 |
| 11 | F17-11 — palavras-chave do perfil e fontes amplas | D | F17-02, F18-07 |
| 12 | F17-12 — buscas salvas | G | F17-03 |
| 13 | F17-13 — relevância aprendida a partir das marcações | J | F17-01, F16-09 |

A numeração identifica cards, não a ordem obrigatória de execução. F17-07 pode
começar em paralelo com F17-01; F17-06 antecede expansão operacional. O Milestone P
inclui F17-01 a F17-07. F16-10 e F17-13 não bloqueiam esse marco.

F17-02 vem antes de qualquer card de volume (F17-04 em diante no efeito, F17-10, F17-11)
porque é o que mantém a precisão enquanto o volume sobe. F17-04 pode propor antes,
mas habilitação em massa espera F17-02 e F17-07, pela fila F17-05.

---

## 15. Invariantes

- Nenhuma fonte é habilitada sem o gate: evidência confirmada por sonda, termos revisados,
  collector testado.
- Evidência antes de inferência: toda classificação guarda o que a decidiu.
- Classificar nunca é apagar: vaga fora do filtro continua no acervo e é encontrável.
- Toda vaga entra por `SourceRun` e `RawItem`, com procedência.
- Nada junta duas oportunidades sem regra exata ou confirmação humana.
- Toda mudança de regra (área, senioridade, skills, sinônimos, identidade) é versionada e
  medida contra o conjunto de referência antes e depois.

---

## 16. Fora de escopo

- Sites que proíbem acesso automatizado nos termos ou exigem login — LinkedIn, Indeed,
  Glassdoor e similares.
- Navegador headless para páginas dinâmicas. Se a descoberta mostrar que muitas empresas
  dependem disso, é SPEC própria.
- Modelo gravando área, senioridade ou elegibilidade automaticamente. A IA pode
  sugerir fatos com evidência para revisão no F18-06, sem substituir o determinístico.
- Candidatura automática ou contato com empresa.

## 17. Continuidade: varredura produtiva

A [SPEC 39](39-spec-varredura-produtiva.md) e a
[Fase 18](40-roadmap-varredura-produtiva/README.md) ampliam a aquisição:
mapa de lacunas, descoberta limitada por site/sitemap, JobPosting público,
agendamento por rendimento, deltas e análise local sob orçamento.
F17-09 continua sendo detecção de ATS em uma página; F18-02 cobre a navegação
limitada quando isso não basta. F17-11 mantém termos explícitos; IA não navega
nem habilita fontes. Produto mede oportunidades úteis encontradas por custo e
atraso, além da qualidade da consulta na Inbox.
