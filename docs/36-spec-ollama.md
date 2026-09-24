# SPEC — Camada local de IA: respostas, tempo, busca e operação

- **Status:** Proposta, para revisão
- **Data:** 2026-09-23, revisada em 2026-09-24 com as decisões da §3.3
- **Escopo:** tudo o que o Opportunity Radar faz com o Ollama — análise semântica,
  desempenho, busca, observabilidade, avaliação e operação
- **Hardware de referência:** Xeon E5-2680 v4, 16 GB de RAM, RTX 5060 8 GB (§3.1)
- **Cards de execução:** [Fase 16](38-roadmap-ia-e-busca/fase-16/README.md)
- **Documentos relacionados:** [SPEC de busca](37-spec-busca.md), [Ollama e prompts](21-ollama-prompts.md),
  [Matching e scoring](20-matching-scoring.md), [Tecnologias](05-tecnologias.md) (§ pgvector),
  [Runbook](30-runbook.md)

---

## 1. Objetivo

A camada de IA existe desde a Fase 10 e funciona no sentido estreito: chama um modelo local,
valida o JSON, degrada sem quebrar o fluxo determinístico. Esta SPEC trata do sentido amplo.
A análise precisa ler a vaga de verdade, responder em português, caber no tempo de uma
fila que roda sozinha, deixar rastro do que custou, poder ser comparada entre versões e,
onde isso se pagar de forma medida, apoiar a busca.

Duas coisas não mudam, e cada requisito abaixo é conferido contra elas:

```text
1. o resultado determinístico é a autoridade: nenhuma saída de modelo altera
   elegibilidade, score, veredito ou fator;
2. a IA é opcional: com o Ollama fora do ar, o radar coleta, normaliza, avalia e mostra
   tudo, só sem o comentário.
```

---

## 2. Estado verificado

Auditoria contra o código em 23 de setembro de 2026.

| Área | O que existe | Onde |
| --- | --- | --- |
| Chamada | `POST /api/chat`, `stream: false`, `format` = JSON Schema, `temperature: 0` | `matching/ollama.py:196` |
| Conexão | um `httpx.AsyncClient` novo a cada análise | `matching/ollama.py:103` |
| Opções do modelo | só `temperature`; sem `num_ctx`, `num_predict`, `seed`, `keep_alive` | `matching/ollama.py:201` |
| Entrada | snapshot estruturado: modo, senioridade, contratos, skills, remuneração, prioridade | `matching/service.py:372` |
| Texto da vaga | **não enviado**: sem título, descrição, empresa, localização | `matching/service.py:387-407` |
| Perfil | skills, países e preferências; **sem experiências nem projetos** | `matching/service.py:410` |
| Prompt | `opportunity_analysis/v1`, em inglês; idioma da saída não especificado | `prompts/opportunity_analysis/v1/` |
| Retentativa | 1 retentativa, 0,5 s de espera; timeout de leitura de 30 s | `platform/config.py:17-20` |
| Cache | LRU em memória de 256 entradas por processo, e a própria tabela de análises | `matching/ollama.py:44` |
| Fila | worker com lote de 10 e concorrência 1; lease de claim de 900 s | `worker.py`, `platform/config.py:34-37` |
| Persistência | status, falha, conteúdo, `model_id`, `prompt_version`, `cache_key` | `matching/models.py:200` |
| Medição | **nenhuma**: sem duração, tokens, tempo de carga ou fila | — |
| Avaliação | `examples.json` com saídas de referência, lidas só por teste | `prompts/.../examples.json` |
| Busca | `LIKE` em título e empresa, sem descrição, sem sinônimo | `dashboard/queries.py:345` |
| Imagem | `ollama/ollama:0.5.13`; `pull` do modelo manual (`runbook`) | `compose.yaml`, `docs/30-runbook.md:211` |
| Modelo | `llama3.2:3b` em todos os usos; `OLLAMA_MODEL_OUTREACH/INTERVIEW` declarados e não usados | `.env.example:42-44` |

### 2.1 O que isso significa

- **A análise comenta a planilha, não a vaga.** Sem título e descrição, o modelo não tem
  como apontar uma responsabilidade que não bate com o perfil, uma exigência escondida no
  texto ou uma contradição entre o anúncio e os campos. O que sobra para ele é reescrever
  em prosa os fatores que o motor determinístico já calculou. É a maior perda de valor da
  camada, e nenhuma otimização de tempo compensa isso.
- **Mandar o texto tem custo.** Uma descrição de vaga costuma ter centenas de palavras — a
  distribuição real do acervo é a primeira coisa que o F16-05 mede. Com o
  contexto padrão do servidor e sem `num_ctx` explícito, um prompt maior que a janela é
  truncado pelo início, que é onde estão as instruções de sistema. O servidor registra
  isso no próprio log, mas a resposta a quem chamou não diz nada: para o radar, a
  truncagem é silenciosa. Levar o texto sem orçar tokens é trocar um problema visível por
  um invisível.
- **O tempo não é conhecido.** Não há como dizer hoje quanto leva uma análise, quanto disso
  é carga de modelo, e se o timeout de 30 s corta respostas que teriam terminado.
- **Nada permite comparar versões.** Mudar prompt ou modelo hoje é aposta: não há conjunto
  fixo de casos nem métrica de qualidade para dizer se `v2` é melhor que `v1`.

---

## 3. Metas mensuráveis

### 3.1 Hardware de referência

| Peça | Especificação | O que decide |
| --- | --- | --- |
| CPU | Intel Xeon E5-2680 v4 — 14 núcleos / 28 threads, AVX2, **sem AVX-512** | inferência em CPU é o caminho lento; serve de reserva, não de padrão |
| RAM | 16 GB | divide espaço com Postgres, API, worker e frontend; modelo em RAM disputa com o banco |
| GPU | NVIDIA RTX 5060, **8 GB de VRAM**, arquitetura Blackwell | é onde a inferência deve rodar; o limite real é a VRAM |

Três consequências para esta SPEC:

- **A GPU é o caminho padrão, não um perfil opcional.** Um modelo de 7–8B em Q4_K_M ocupa
  cerca de 5 GB de VRAM, e o que sobra dos 8 GB é o cache de contexto (KV). Com
  `OLLAMA_KV_CACHE_TYPE=q8_0` e flash attention, uma janela de 8 192 tokens cabe junto.
  Modelos de 12B ou mais em Q4 não cabem com contexto útil e transbordam para a RAM, o que
  derruba a velocidade e compete com o Postgres: ficam fora da comparação (§8.1).
- **Hoje a análise roda em CPU, com certeza.** O serviço `ollama` do `compose.yaml` não
  reserva nenhuma GPU, então o container não enxerga a RTX 5060, qualquer que seja a
  versão. E a GPU, quando reservada, exige servidor recente: Blackwell precisa de CUDA 12.8
  ou superior, e a imagem `ollama/ollama:0.5.13` é muito provavelmente anterior a esse
  suporte — o F16-01 confirma. Reservar a GPU e atualizar a imagem deixam de ser melhoria e
  viram **pré-requisito** (F16-01 abre o plano, §14), com verificação explícita de que o
  modelo carregou na VRAM (`/api/ps`, campo `size_vram`).
- **Docker no Windows passa pelo WSL2.** A GPU chega ao container pelo Docker Desktop com
  backend WSL2 e o driver NVIDIA do Windows. O runbook ganha esse passo, e o `doctor` passa
  a recusar a análise habilitada com o modelo carregado fora da VRAM.

`OLLAMA_NUM_PARALLEL=1`: cada requisição paralela reserva outro cache de contexto, e com
8 GB isso cabe em uma, não em duas. `OLLAMA_MAX_LOADED_MODELS=2` só quando o modelo de
embedding (§7.2) existir, porque ele é pequeno (menos de 1 GB) e pode ficar residente ao lado
do modelo de análise.

### 3.2 Metas

Os números de latência são estimativas para 7–8B em Q4 nessa GPU — geração na casa de
dezenas de tokens por segundo e avaliação do prompt na casa dos milhares. O F16-03 mede o
valor real antes de qualquer otimização, e as metas são recalculadas a partir dele se a
medição cair fora da faixa. Cada meta tem a medição que a prova, na §9.

| Meta | Hoje | Alvo |
| --- | --- | --- |
| Análise que lê título e descrição da vaga | 0% | 100% das análises com descrição disponível |
| Prompt truncado sem aviso | desconhecido | 0, com contagem de tokens antes do envio |
| Análise em pt-BR | não especificado | 100% dos campos textuais |
| Latência p50 com modelo aquecido, na GPU | não medida | ≤ 8 s |
| Latência p95 com modelo aquecido, na GPU | não medida | ≤ 15 s |
| Análises executadas com o modelo inteiro na VRAM | 0% (compose sem GPU) | 100% |
| Primeira análise após ociosidade (carga do modelo) | não medida | ≤ 1,5 × p95, com aquecimento no início do worker |
| Análises que falham por timeout | não medida | < 2% em janela de 7 dias |
| Taxa de `SCHEMA_MISMATCH` / `INVALID_JSON` | não medida | < 1% |
| Análises reaproveitadas pelo cache persistente após reinício | 0% (cache em memória) | 100% das chaves já gravadas |
| Qualidade no conjunto de avaliação (§8) | inexistente | nota ≥ baseline `v1` em todos os critérios, e maior em fidelidade |
| Busca que encontra por termo da descrição | não | sim, com Postgres full-text |
| Vagas com embedding atual | não existe | 100% das oportunidades não rejeitadas, em até 2 ciclos do worker |

### 3.3 Decisões tomadas

Decididas pelo operador em 24 de setembro de 2026, e tratadas daqui em diante como o
padrão a implementar, não como hipótese a comparar:

| Decisão | Valor | Substitui | Fonte |
| --- | --- | --- | --- |
| Modelo de análise | `qwen3:8b-q4_K_M` — 5,2 GB, contexto nativo de 40K, saída estruturada | `llama3.2:3b` | [Ollama](https://ollama.com/library/qwen3/tags) |
| Raciocínio do modelo | desligado por requisição (`think: false`) | — | §4.4 |
| Imagem do servidor | `ollama/ollama:0.34.4`, fixada por digest `sha256:8262851b2846…0841551` | `0.5.13` | Docker Hub, release de 23/09/2026 |
| Modelo de embedding | `qwen3-embedding:0.6b` — 639 MB, multilíngue, 1 024 dimensões | — | [Ollama](https://ollama.com/library/qwen3-embedding/tags) |
| Banco vetorial | pgvector 0.8.6, compilado sobre a imagem `postgres:17.2-alpine` atual | — | §7.2 |
| Execução | GPU por padrão; CPU como perfil de reserva | CPU | §3.1 |

A regra de troca da §8 continua valendo, mas agora para **sair** desse padrão: um modelo
ou uma quantização diferente só substitui o `qwen3:8b-q4_K_M` com relatório de avaliação
mostrando que não piora nenhum critério e melhora pelo menos um.

O suporte da RTX 5060 foi confirmado contra a fonte: o problema de GPUs Blackwell ficando
em CPU foi corrigido no Ollama em novembro de 2025
([issue #13163](https://github.com/ollama/ollama/issues/13163)), bem antes da 0.34.4.

---

## 4. Frente A — Qualidade da resposta

### 4.1 Levar a vaga ao modelo

- Acrescentar ao payload um bloco `posting`, separado do snapshot determinístico:
  `title`, `company_name`, `location_text` e `description`. O snapshot continua como está,
  porque ele é a identidade da avaliação e entra no `input_hash`.
- A descrição entra **limpa e orçada**: HTML removido, espaços colapsados, seções de
  boilerplate reconhecidas descartadas ("About us", "Equal opportunity", "Benefits"
  genéricos), e o resultado cortado por orçamento de tokens (§5.2), nunca por caracteres
  no meio de uma palavra. O corte é registrado no payload (`description_truncated: true`)
  para o modelo saber que não viu tudo.
- O `content_version` da oportunidade já entra na chave de cache. Mudar o texto da vaga,
  portanto, já invalida a análise, sem regra nova.

### 4.2 Levar o perfil ao modelo

- Acrescentar ao perfil um resumo das experiências e projetos: cargo, empresa, período,
  tecnologias e uma linha de descrição por item, os 5 mais recentes. Esse resumo sai da
  versão do perfil, que já entra na chave de cache.
- O perfil não inclui dados de contato nem nada que não sirva para comparar com uma vaga.

### 4.3 Prompt `v2`

- `prompts/opportunity_analysis/v2`, criado ao lado do `v1`, que continua carregável. A
  troca é por configuração (`OLLAMA_ANALYSIS_PROMPT=v2`), e as análises antigas guardam o
  `prompt_version` com que foram feitas.
- Saída em **português do Brasil**, declarada no system prompt e conferida pelo avaliador
  (§8).
- Instruções que usam o texto: apontar exigências do anúncio ausentes do perfil, citar o
  trecho da vaga que sustenta cada força ou risco, separar o que o anúncio afirma do que o
  modelo inferiu.
- Schema `analysis-v2`: cada item de `strengths` e `risks` passa a ser
  `{ "claim": string, "evidence": string | null }`, onde `evidence` é o trecho literal da
  vaga ou do perfil. O validador confere que o trecho aparece no payload enviado.
  Afirmação com evidência inventada é `SCHEMA_MISMATCH`, não resposta aceita.
- O schema continua sem score, sem elegibilidade e sem desqualificador. O validador
  continua recusando campo desconhecido.
- Poucos exemplos no prompt (1–2, curtos) só se o avaliador mostrar ganho. Exemplo custa
  token em toda chamada.

### 4.4 Determinismo

- `seed` fixo em `options`, junto com `temperature: 0`, para que a mesma entrada no mesmo
  modelo produza a mesma saída. Isso é o que torna a comparação entre versões (§8) justa.
- `think: false` em toda requisição de análise. O Qwen3 raciocina antes de responder por
  padrão; numa análise que é um resumo estruturado, esses tokens custam segundos e janela
  de contexto sem melhorar a saída. Ligar o raciocínio é experimento da §8, não padrão.
- `top_k`/`top_p` explícitos no `metadata.yaml` da versão do prompt, para que a
  configuração de amostragem seja parte do artefato versionado e não um padrão do servidor.

---

## 5. Frente B — Contexto e tokens

### 5.1 Contexto explícito

- `num_ctx` explícito em toda chamada, configurável (`OLLAMA_ANALYSIS_NUM_CTX`, padrão
  8192). A janela nunca fica por conta do padrão do servidor, que muda entre versões.
- `num_predict` explícito (`OLLAMA_NUM_PREDICT`, padrão 1024): o limite de saída corta
  resposta que desanda, em vez de deixar o modelo gerar até o timeout.
- O `qwen3:8b` aceita 40K de contexto, mas a janela usada é a que cabe na VRAM junto com os
  pesos (§3.1), não a que o modelo aceita. Subir o `num_ctx` é decisão medida, com a VRAM
  ocupada no relatório.

### 5.2 Orçamento antes do envio

- Estimar os tokens do prompt montado antes de enviar. A primeira versão usa o tokenizer do
  próprio servidor, contando pela resposta de uma chamada de aquecimento
  (`prompt_eval_count`) e calibrando uma razão caracteres/token por modelo. A estimativa
  fica persistida por modelo.
- Orçamento: `num_ctx − num_predict − margem de 10%`. A descrição (§4.1) é a única parte
  elástica: system prompt, snapshot e perfil são fixos, e o que sobra é o espaço da
  descrição.
- Se nem a parte fixa couber, a análise não é enviada: falha classificada como
  `CONTEXT_OVERFLOW` (código novo). Nunca truncamento silencioso.
- Toda análise grava `prompt_tokens` (o `prompt_eval_count` real devolvido) e a estimativa
  feita antes. A diferença entre as duas é o indicador de calibração.

---

## 6. Frente C — Tempo e vazão

### 6.1 Conexão e modelo quentes

- **Cliente HTTP persistente não se paga aqui.** O worker chama cada análise com
  `asyncio.run` (`worker.py:163`), o que cria um loop de eventos novo por análise, e um
  `httpx.AsyncClient` não pode ser reaproveitado entre loops. Trocar isso exigiria mudar o
  modelo de execução do worker para economizar milissegundos de conexão local. O ganho real
  de tempo está no modelo carregado, não na conexão: a proposta de cliente persistente sai
  desta SPEC.
- `keep_alive` explícito por chamada (`OLLAMA_KEEP_ALIVE`, padrão `30m`), para que a fila
  não pague a carga do modelo a cada lote.
- **Aquecimento** no início do worker e antes de cada lote após ociosidade maior que o
  `keep_alive`: uma chamada mínima (`num_predict: 1`) que carrega o modelo e mede a
  calibração de tokens (§5.2). A carga passa a ser um evento medido do worker, não o
  primeiro item da fila pagando por ela. O aquecimento usa `POST /api/generate` com
  `prompt` vazio, que carrega o modelo sem gerar nada, e nunca falha a subida do worker.

### 6.2 Timeouts pelo que se sabe

- Separar o timeout de carga do timeout de geração. Com aquecimento, o timeout da análise
  deixa de absorver a carga do modelo. O valor passa a derivar do p99 medido (§9), com
  piso de 30 s e teto de 120 s, em vez de um número fixo escolhido antes de haver medição.
- Retentativa só para falha de transporte e 5xx, com backoff exponencial e jitter. Timeout
  não é retentado de imediato: um modelo que estourou o tempo com essa entrada tende a
  estourar de novo, e a retentativa já é papel do cooldown da fila (`analysis_retry_*`).

### 6.3 Vazão da fila

- Concorrência do worker alinhada ao servidor: `WORKER_ANALYSIS_CONCURRENCY` igual a
  `OLLAMA_NUM_PARALLEL` (padrão 1, pela VRAM da §3.1). Mandar duas requisições para um servidor que
  atende uma só enfileira no Ollama, que já tem fila.
- Ordem da fila por valor: `HIGH_PRIORITY` e `RECOMMENDED` antes de `WATCHLIST` e
  `REVIEW_REQUIRED`, e dentro de cada veredito, publicação mais recente primeiro. Com a
  fila atrasada, o que o operador vai ler primeiro é o que fica pronto primeiro.
- Configuração do servidor aplicada no compose, com medição antes e depois (§9):
  `OLLAMA_FLASH_ATTENTION=1` e `OLLAMA_KV_CACHE_TYPE=q8_0`. As duas reduzem a memória do
  cache de contexto, e é isso que permite modelo de 7–8B e `num_ctx` de 8 192 caberem juntos
  nos 8 GB de VRAM da referência (§3.1). `OLLAMA_NUM_PARALLEL=1` pelo mesmo motivo.

### 6.4 Cache que sobrevive

- Antes de chamar o modelo, consultar a tabela de análises pela `cache_key` e reaproveitar
  uma análise `AI_COMPLETED` com a mesma chave. Hoje o reaproveitamento é só em memória e
  morre a cada reinício do worker.
- O LRU em memória continua como primeiro nível, e a tabela vira o segundo. A chave não
  muda: ela já cobre modelo, prompt, schema, versão da vaga e versão do perfil.

---

## 7. Frente D — Vetores: pgvector e embeddings

A busca textual sem IA (Postgres full-text) é da [SPEC de busca](37-spec-busca.md), card
F17-03. Esta frente trata do que só vetores fazem: aproximar vagas pelo significado.

### 7.1 Decisão

A versão anterior desta SPEC condicionava o pgvector a um protótipo medido, como
`docs/05-tecnologias.md` pedia. O operador decidiu construir a infraestrutura agora
(§3.3). O que continua medido é o **uso**: a busca semântica só vira o padrão da Inbox
se superar a busca full-text no conjunto de referência (§7.4). A infraestrutura vale
sozinha, porque ela alimenta as vagas parecidas (§7.3) e as ferramentas de apoio ao modelo
(§11).

### 7.2 Infraestrutura

- **Postgres com pgvector sem trocar de imagem base.** O banco roda em
  `postgres:17.2-alpine` (musl). A imagem oficial `pgvector/pgvector` é Debian (glibc), e
  trocar a base sobre o volume existente muda a ordenação de texto sob índices já
  construídos, o que corrompe índices em silêncio. Por isso o pgvector 0.8.6 é compilado
  numa imagem própria derivada da alpine atual (`docker/postgres/Dockerfile`), com
  `OPTFLAGS=""` para que o binário não fique preso às instruções da CPU que fez o build, e
  sem bitcode LLVM (`with_llvm=no`).
- No CI, o serviço de Postgres do job de backend começa sempre vazio, então pode usar a
  imagem oficial `pgvector/pgvector:0.8.6-pg17`. O job de compose constrói a imagem do
  projeto, como em produção.
- **Tabela derivada.** `opportunities.opportunity_embedding`: uma linha por oportunidade,
  com a versão de conteúdo e o modelo que produziram o vetor, um hash do texto usado e o
  vetor `vector(1024)`. Índice HNSW com `vector_cosine_ops`. Pode ser apagada e refeita a
  qualquer momento: não é evidência.
- **Tipo sem dependência nova.** O projeto não precisa do pacote `pgvector` do Python: o
  formato de texto do pgvector é `[1,2,3]`, e um tipo SQLAlchemy próprio converte nos dois
  sentidos, sempre com `CAST(... AS vector(1024))` explícito, para o driver não adivinhar
  o tipo e um vetor de tamanho errado falhar no banco.
- **Texto que vira vetor.** Título, empresa, localização, modo de trabalho, senioridade,
  skills e a descrição limpa (sem HTML, espaços colapsados), cortada em tamanho fixo. O
  mesmo limpador da §4.1.
- **Assimetria de consulta.** O `qwen3-embedding` espera uma instrução antes da consulta
  de busca (`Instruct: …\nQuery: …`) e nenhuma nos documentos. A instrução é versionada
  junto com o modelo.
- **Job do worker.** `embed_opportunities`, com chave de desligar própria
  (`WORKER_EMBED_ENABLED`), processa em lotes as oportunidades sem vetor, com versão de
  conteúdo mais nova ou com modelo diferente do configurado. O `/api/embed` recebe o lote
  inteiro numa chamada.
- **Troca de modelo de embedding.** Modelo de outro tamanho exige migração da coluna e
  reindexação completa. Mesmo tamanho, modelo diferente: o job refaz tudo, porque vetores
  de modelos diferentes não se comparam.

### 7.3 Vagas parecidas

- `GET /opportunities/{id}/similar`: as vagas mais próximas pelo cosseno, do mesmo modelo
  de embedding, excluindo a própria.
- Seção "Vagas parecidas" no detalhe da oportunidade, com o veredito de cada uma, para o
  operador ver como vagas semelhantes foram avaliadas.
- Candidatos a duplicata (similaridade acima de um limiar alto, empresa igual) aparecem
  como sugestão para revisão, no fluxo da [SPEC de busca](37-spec-busca.md) §12. O vetor
  nunca junta duas oportunidades sozinho.

### 7.4 Busca por significado, com gate de uso

- `GET /search/semantic?q=`: a consulta vira vetor com a instrução de busca e é comparada
  aos vetores das vagas.
- **Gate:** medir recall@10 e nDCG@10 nas 40 consultas de referência da
  [SPEC de busca](37-spec-busca.md) §10 para três modos — full-text, vetorial e híbrido
  (fusão por *reciprocal rank*). A Inbox adota o modo que vencer. Se o full-text vencer, a
  busca semântica fica disponível pela API e fora da tela, com os números registrados.

---

## 8. Frente E — Avaliação

Sem avaliação, as frentes A e B são opinião. Esta frente vem antes de qualquer troca de
prompt ou modelo.

- **Conjunto fixo:** 30 pares vaga/perfil reais, anonimizados, em
  `prompts/opportunity_analysis/eval/`, cobrindo vaga forte, vaga fraca, vaga ambígua,
  descrição longa, descrição em inglês e vaga sem descrição.
- **Critérios, pontuados por caso:**
  - **fidelidade:** toda `evidence` aparece no payload (conferido por código, não por
    modelo);
  - **aderência ao determinístico:** o texto não contradiz o veredito;
  - **cobertura:** as exigências do anúncio que faltam no perfil aparecem em `risks`, contra
    uma lista marcada à mão por caso;
  - **idioma:** saída em pt-BR;
  - **custo:** tokens de entrada e saída, latência.
- **Comando:** `make eval-analysis PROMPT=v2 MODEL=...` roda o conjunto contra o Ollama
  local, grava o relatório em `data/evals/` e compara com o último baseline salvo.
- **Regra de troca:** um prompt ou modelo novo só vira padrão se não piorar nenhum critério
  e melhorar pelo menos um, no mesmo hardware. O relatório entra no PR que faz a troca.
- **CI:** o conjunto não roda no CI, que usa o Ollama falso. O CI confere só o que é
  determinístico: schema, validador de evidência, montagem do payload e orçamento de
  tokens contra uma razão caracteres/token fixa.

### 8.1 Confirmação do modelo

O padrão já é o `qwen3:8b-q4_K_M` (§3.3). Com o conjunto de avaliação pronto, confirmar a
escolha contra: o `llama3.2:3b` anterior, como baseline de piso; um 8B de outra família
(Llama 3.1 8B); o próprio Qwen3 8B em Q5_K_M (§12); e o Qwen3 8B com raciocínio ligado.
Pelos critérios da §8, pela latência na GPU e pela VRAM ocupada com `num_ctx` de 8 192.
Modelo que transborda para a RAM está desclassificado, qualquer que seja a nota. O
relatório fica em `docs/pesquisas/` e fecha a decisão, mantendo ou trocando o padrão.

---

## 9. Frente F — Observabilidade

- Gravar em cada análise, a partir da resposta do Ollama: `total_duration`,
  `load_duration`, `prompt_eval_count`, `prompt_eval_duration`, `eval_count`,
  `eval_duration`, e a estimativa de tokens (§5.2). Migração com colunas anuláveis: as
  análises antigas não têm esses dados, e isso aparece como indisponível, nunca como zero.
- Log estruturado por análise com os mesmos números, no formato que o worker já usa.
- `GET /analysis-metrics?window=24h|7d`: p50/p95/p99 de latência, tokens médios de entrada
  e saída, taxa por código de falha, taxa de acerto do cache e tamanho da fila pendente. A
  Visão geral ganha uma linha de apoio no bloco de operação, no mesmo padrão das métricas
  por fonte.
- O `doctor` passa a conferir, além do modelo instalado: versão do servidor, `keep_alive`
  efetivo, modelo carregado (`/api/ps`) e memória usada.

---

## 10. Frente G — Operação

- **Imagem:** `ollama/ollama:0.34.4` fixada por digest (§3.3). Atualizações futuras
  passam pelo conjunto de avaliação (§8): versão de servidor muda tokenizer, padrões e
  desempenho.
- **Modelos instalados sem terminal:** serviço `ollama-init` no compose, com a mesma
  imagem, que roda `ollama pull` do modelo de análise e do de embedding contra o serviço
  `ollama` (`OLLAMA_HOST`) e termina. Ninguém depende dele para subir: a análise é
  opcional, e um modelo ainda baixando aparece como `MODEL_UNAVAILABLE` classificado.
- **Recursos:** limite de RAM no serviço `ollama` do compose, para que um transbordo da VRAM
  não tome a memória do Postgres nos 16 GB da referência. Um modelo que não cabe deve falhar
  na subida, não derrubar o banco.
- **Configuração enxuta:** remover `OLLAMA_MODEL_OUTREACH` e `OLLAMA_MODEL_INTERVIEW` do
  `.env.example`. Declarar modelo para funcionalidade que não existe é documentação falsa.
- **GPU por padrão:** o serviço `ollama` reserva a GPU NVIDIA (`deploy.resources.
  reservations.devices`), e o runbook documenta o pré-requisito no Windows: Docker Desktop
  com WSL2 e driver NVIDIA recente. Numa máquina sem GPU, o compose com reserva de GPU
  nem sobe o serviço; por isso existe `compose.cpu.yaml`, que remove a reserva
  (`deploy: !reset null`). O `compose.ci.yaml` faz o mesmo sobre o Ollama falso, porque o
  runner do CI não tem GPU.

---

## 11. Frente H — Ferramentas de apoio ao modelo

Modelo de 8B erra menos quando recebe o contexto certo pronto do que quando precisa
procurar. Por isso as "ferramentas" aqui são código determinístico que roda **antes** da
chamada e entrega o resultado no payload — não chamadas de ferramenta feitas pelo modelo.
Chamada de ferramenta pelo modelo acrescenta turnos, latência e uma decisão não
determinística sobre quando chamar, num fluxo que precisa ser reproduzível.

| Ferramenta | O que faz | Onde |
| --- | --- | --- |
| Limpador de descrição | remove HTML, colapsa espaço, descarta boilerplate reconhecido | §4.1 |
| Orçamento de tokens | calcula quanto da descrição cabe e marca o corte | §5.2 |
| Validador de evidência | confere que cada `evidence` aparece literalmente no payload | §4.3 |
| Saída estruturada | `format` com o JSON Schema da versão do prompt | já existe |
| Aquecimento | carrega o modelo antes da fila | §6.1 |
| Contexto recuperado | vagas parecidas e como foram decididas | §11.1 |

### 11.1 Contexto recuperado (RAG)

- Para cada análise, recuperar pelo pgvector as 3 vagas mais parecidas que já têm decisão
  do operador — candidatura aberta, descarte, ou marcação de relevância da
  [SPEC de busca](37-spec-busca.md) §13 — e entregar ao modelo título, veredito e decisão de
  cada uma, num bloco `similar_decisions` separado do snapshot.
- O modelo usa isso para comentar ("vaga parecida com X, que você descartou por
  localização"), nunca para decidir: o schema continua sem score e sem veredito.
- **Reprodutibilidade:** o contexto recuperado muda com o tempo, então os identificadores
  recuperados entram na chave de cache da análise. A mesma vaga com contexto diferente é
  outra análise, e a análise guarda quais vagas recebeu.
- Entra só depois do conjunto de avaliação (§8) mostrar que o bloco melhora a cobertura ou a
  fidelidade sem piorar o custo além da meta de latência.

---

## 12. Frente I — Quantização

A quantização decide quanto do modelo cabe na VRAM e quanto sobra para o contexto.
Números de tamanho vêm da página de tags do Ollama; a VRAM real é medida (§9).

| Componente | Padrão | Alternativas a medir | Limite |
| --- | --- | --- | --- |
| Pesos do modelo de análise | Q4_K_M (5,2 GB) | Q5_K_M, Q6_K | o que sobrar precisa acomodar o cache de 8K de contexto; Q8_0 (8,9 GB) não cabe |
| Cache de contexto (KV) | `q8_0` | `f16` (mais memória), `q4_0` (menos qualidade) | medido com `num_ctx` de 8 192 |
| Modelo de embedding | a tag padrão do `qwen3-embedding:0.6b` (639 MB) | `fp16` (1,2 GB) | cabe ao lado do modelo de análise com `OLLAMA_MAX_LOADED_MODELS=2` |

- A quantização vai sempre no nome da tag (`qwen3:8b-q4_K_M`), nunca implícita: uma tag
  sem quantização deixa o registro decidir quais pesos rodam, e uma atualização do
  registro trocaria o modelo sem ninguém mudar a configuração.
- Subir de Q4_K_M para Q5_K_M ou Q6_K é troca de modelo, com a regra da §8: relatório de
  qualidade, latência e VRAM no mesmo documento.
- Quantizar ou converter modelo localmente (GGUF próprio, `ollama create`) fica fora do
  escopo enquanto existir tag oficial que atenda.

---

## 13. Descobertas técnicas que os cards precisam respeitar

Levantadas numa tentativa de implementação em 24 de setembro de 2026, interrompida para
virar cards. Valem como notas de implementação:

- **Loop de eventos por análise.** `worker.py:163` usa `asyncio.run` por análise; qualquer
  recurso assíncrono compartilhado (cliente HTTP, semáforo) não sobrevive entre chamadas.
- **Ollama falso do CI.** `tests/e2e/fake_ollama.py` responde só `/api/tags` e
  `/api/chat`, sem campos de duração. Ele precisa responder `/api/embed` (vetor
  determinístico de 1 024 posições), `/api/generate` (aquecimento) e devolver
  `eval_count`/`total_duration` no chat, senão o E2E não exercita nada disto.
- **Asserção exata dos jobs no E2E.** O passo "Verify the kill switches reach the worker"
  compara o dicionário de jobs com igualdade exata. Um job novo (`embed_opportunities`)
  exige atualizar esse passo e o `FUNCTIONAL_JOB_IDS`, junto com `tests/backend/test_worker.py`.
- **Ordem de rotas.** `GET /opportunities/{opportunity_id}` é declarado antes; uma rota
  `/opportunities/semantic-search` seria capturada por ele e responderia 422. A busca por
  significado vai num roteador próprio (`/search/semantic`).
- **Nome acessível do modelo no health.** O `health` compara o modelo configurado com
  `/api/tags`; trocar o padrão para `qwen3:8b-q4_K_M` muda o que o Ollama falso precisa
  (ou não) listar para manter o estado `degraded` que o primeiro passo do E2E espera.
- **Criação da extensão.** `CREATE EXTENSION vector` exige superusuário ou extensão
  confiável; o usuário do compose e o do CI são superusuários, e o runbook registra isso
  para instalações fora do compose.

---

## 14. Plano de entrega

Os cards detalhados estão em
[`38-roadmap-ia-e-busca/fase-16`](38-roadmap-ia-e-busca/fase-16/README.md). Ordem e
dependências:

| Ordem | Card | Frente | Depende de |
| --- | --- | --- | --- |
| 1 | F16-01 — GPU, imagem 0.34.4, `ollama-init` e perfis de execução | G | Nenhum |
| 2 | F16-02 — `qwen3:8b-q4_K_M` como padrão e opções explícitas da chamada | B, A | F16-01 |
| 3 | F16-03 — custo de cada análise: durações e tokens | F | F16-02 |
| 4 | F16-04 — aquecimento, `keep_alive` e fila por valor | C | F16-02 |
| 5 | F16-05 — orçamento de tokens, limpador e `CONTEXT_OVERFLOW` | B | F16-03 |
| 6 | F16-06 — conjunto de avaliação e `make eval-analysis` | E | F16-03 |
| 7 | F16-07 — vaga e experiências no payload, prompt `v2` pt-BR com evidência | A | F16-05, F16-06 |
| 8 | F16-08 — cache persistente na tabela de análises | C | F16-03 |
| 9 | F16-09 — pgvector e embeddings das vagas | D | F16-01 |
| 10 | F16-10 — vagas parecidas e busca por significado com gate | D | F16-09, F17-03 |
| 11 | F16-11 — contexto recuperado para a análise | H | F16-06, F16-07, F16-09 |
| 12 | F16-12 — confirmação do modelo e da quantização | E, I | F16-06, F16-07 |
| 13 | F16-13 — métricas da análise na API, na Visão geral e no `doctor` | F | F16-03 |

F16-01 vem primeiro porque, no hardware de referência, sem ele tudo roda em CPU e
qualquer medição anterior seria do caminho errado. F16-09 só depende da infraestrutura e
pode andar em paralelo com F16-02 a F16-08.

---

## 15. Invariantes

- A saída do modelo não altera elegibilidade, score, veredito nem fator.
- Com o Ollama indisponível, nada além do comentário deixa de funcionar.
- Nenhum prompt é truncado sem que isso esteja registrado na análise.
- Toda análise registra modelo, versão de prompt, versão de schema e o que custou.
- Toda troca de prompt, modelo, quantização ou versão de servidor passa pelo conjunto de
  avaliação.
- Embedding é dado derivado: pode ser apagado e refeito, e nunca junta nem decide nada.
- Nenhum dado do operador sai da máquina: nenhuma frente introduz serviço de IA remoto.

---

## 16. Riscos

| Risco | Mitigação |
| --- | --- |
| Descrição longa estoura a janela e o tempo | orçamento de tokens (§5.2), `num_predict`, limpeza de boilerplate |
| Modelo ou quantização maior melhora a qualidade e estoura a latência | a regra de troca (§8) exige as duas medidas no mesmo relatório |
| `evidence` inventada que parece plausível | conferência literal por código, não por outro modelo |
| Avaliação com poucos casos dá conclusão frágil | 30 casos cobrindo os tipos listados; diferença pequena não troca o padrão |
| Busca semântica vira custo sem ganho | gate de recall@10 antes de virar o padrão da Inbox (§7.4) |
| Trocar a base do Postgres corrompe índices de texto | pgvector compilado sobre a mesma imagem alpine (§7.2) |
| Máquina ou CI sem GPU não sobe o compose | `compose.cpu.yaml` e `compose.ci.yaml` removem a reserva (§10) |
| Raciocínio do Qwen3 ligado por engano | `think: false` explícito em toda requisição, conferido em teste do payload |
| Atualizar o Ollama muda o comportamento em silêncio | imagem fixada por digest e troca só com relatório de avaliação |

---

## 17. Fora de escopo

- Serviços de IA remotos (OpenAI, Anthropic, etc.) ou envio de dados para fora da máquina.
- Modelo decidindo elegibilidade, score ou veredito.
- Geração de carta de apresentação, mensagem de contato ou preparação de entrevista — os
  usos que o `.env.example` sugeria. Se voltarem, é SPEC própria, sobre esta base.
- Fine-tuning de modelo.
- Streaming da análise para a tela: a análise roda na fila, e ninguém espera por ela na
  frente do monitor.
