# Rotulagem F20-01 (full-text) — Relevância da busca sem o viés de título

- **Card:** [F20-01](../fase-20/f20-01-baselines-e-relatorios-da-busca.md)
- **Branch:** `feature/f20-rotulos-2`
- **Objetivo:** o addendum de 2026-09-27 em `f20-01-relevancia-busca.md` deixou registrado que
  o gabarito daquela rodada ainda vinha de correspondência por substring de
  **título/empresa** (mesmo critério do `like`), então `like` recall@10 = 1,0000 não provava
  nada a favor do `like`. Este documento constrói um segundo conjunto de candidatos a partir
  de correspondência por substring na **`description`** (não no título), para as mesmas 14
  consultas anteriores mais `kubernetes` e `frontend` (16 no total) — as duas que antes não
  tinham candidato nenhum por título.
- **Medido em:** 2026-09-27/28, `docker compose -p opportunity-radar exec postgres psql`
  (somente `SELECT`, banco real com a coleção em medição de 7 dias, container já em
  execução, sem `down -v`, sem escrita, sem `restart`).
- **Metodologia:** para cada uma das 16 consultas, os candidatos são as até 8 vagas mais
  recentes cujo campo `description` (não `canonical_title`/`company_name`) contém o termo
  (`lower(description) LIKE '%termo%'`). A justificativa de cada linha usa um trecho curto
  (~140 caracteres) da `description` ao redor do termo — nenhum nome de pessoa, e-mail ou
  telefone aparece nesses trechos (textos de vaga em inglês/português, sem PII). O dataset
  completo (128 casos = 16 consultas × 8 candidatos) está em
  `f20-01-relevancia-busca-fulltext.json`. **Toda recomendação é do agente**; o usuário
  pré-autorizou aceitar as recomendações como estão (`decisao_usuario`: `"aceito
  (pre-autorizado)"` em todas as linhas).

## Resultado da rotulagem: 128 candidatos, 68 relevantes, 19 ambíguos, 41 não relevantes

| Consulta | Candidatos | Relevantes | Ambíguos | Não relevantes |
| --- | --- | --- | --- | --- |
| accounting | 8 | 3 | 3 | 2 |
| aws | 8 | 6 | 1 | 1 |
| backend | 8 | 4 | 1 | 3 |
| devops | 8 | 3 | 1 | 4 |
| frontend | 8 | 3 | 5 | 0 |
| fullstack | 8 | 8 | 0 | 0 |
| java | 8 | 4 | 0 | 4 |
| kubernetes | 8 | 8 | 0 | 0 |
| machine learning | 8 | 3 | 3 | 2 |
| marketing | 8 | 2 | 1 | 5 |
| node | 8 | 5 | 0 | 3 |
| product manager | 8 | 2 | 1 | 5 |
| python | 8 | 7 | 1 | 0 |
| qa | 8 | 1 | 1 | 6 |
| react | 8 | 4 | 0 | 4 |
| sales | 8 | 5 | 1 | 2 |
| **Total** | **128** | **68 (53%)** | **19 (15%)** | **41 (32%)** |

Contraste direto com o gabarito por título: naquele conjunto, 86 de 88 linhas com candidato
(98%) eram "relevante" — porque o candidato só existia se o termo já estivesse no título,
então quase todo candidato "fazia sentido" por construção. Aqui, procurando na descrição
inteira, quase um terço dos candidatos é claramente irrelevante e a metodologia expõe dois
tipos de ruído que o modo `like` sobre título nunca produziria:

### 1. Falsos positivos de substring (sem word boundary)

`LIKE '%termo%'` casa qualquer ocorrência da string, não a palavra inteira:

- **`java` casa `javascript`** em 4 das 8 vagas (`n8n`/Agentic Engineering, Supabase/OrioleDB,
  Firecrawl/Web Automation, RevenueCat/Senior SWE Product) — nenhuma delas pede Java, só
  JavaScript.
- **`react` casa `reactively`** em 2 vagas (Nubank/Lead SWE CloudNetwork ×2) e casa o nome do
  produto da Clerk ("React components") em 2 outras que não são vagas de desenvolvimento
  React.
- **`aws` casa `laws`** ("Mexican banking **laws**") em 1 vaga sem nenhuma relação com AWS.
- **`node` casa `nodes`** (nós de workflow do produto n8n) e **`Node-RED`** (ferramenta de
  terceiros) em 3 das 8 vagas — nenhuma delas pede Node.js.

### 2. Menção real do termo, mas fora da intenção da busca

- **Negação explícita:** a vaga de Analytics Engineer da Cartesia diz literalmente `"NOT
  REQUIRED - Machine learning, ..."` — o termo aparece exatamente onde o requisito é negado.
- **Bônus/opcional, não requisito:** `"[bonus] Background in machine learning"` (Cartesia,
  Engineering Manager) — mencionado como diferencial, não como exigência.
- **Termo descreve o domínio do sistema, não a função do cargo:** duas vagas de Staff
  Software Engineer da Nubank mencionam "double-entry **accounting** engines" — são vagas de
  engenharia que constroem sistemas de contabilidade, não vagas de contabilidade.
- **Termo descreve texto padrão do produto da empresa, repetido em várias vagas não
  relacionadas:** "we provide a complete **backend** solution including Database, Auth..."
  aparece idêntico em 3 vagas da Supabase de áreas diferentes (Deployment Engineer, Database
  Support, Partner Marketing Manager) — é a descrição institucional da empresa, não uma
  característica do cargo.
- **Termo cita a outra equipe/stakeholder, não o próprio cargo:** `"Collaborate with QA to
  investigate defects"` (papel é Mid-Level Software Developer, não QA); `"Product Managers"`
  citados como pessoas com quem um engenheiro se comunica (papel é engenharia, não PM);
  `"DevOps"` citado como perfil de comprador em vagas de vendas do n8n.

`kubernetes` e `frontend` — as duas consultas que o gabarito por título nunca conseguiu
medir (recall@10 = 0 por construção, já documentado no addendum anterior) — agora têm
candidatos reais: `kubernetes` teve 8/8 relevantes (termo técnico específico, baixo ruído);
`frontend` teve 3/8 relevantes e 5/8 ambíguos (nenhum falso positivo claro, mas muita vaga
fullstack que só toca frontend de passagem).

## Como aplicar

`data/search-reference/queries.json` foi reconstruído localmente (fora do git, como o schema
já previa) só com as 68 linhas `relevante` deste conjunto — as 16 consultas, incluindo agora
`kubernetes` e `frontend` com gabarito de verdade. Comando usado:

```bash
python scripts/search_reference.py resolve --json   # opcional, para conferir
```

Na prática, este worker copiou o JSON já resolvido (query → lista de `relevant_urls`,
extraído de `f20-01-relevancia-busca-fulltext.json` filtrando `recomendacao == "relevante"`)
diretamente para `data/search-reference/queries.json`, que é o schema que
`scripts/search_reference.py`/`scripts/eval_search.py` esperam.

## Medição real — bloqueada por interrupção externa do Docker Desktop (2026-09-28)

Depois de copiar o `queries.json` para dentro do container `opportunity-radar-api-1` (via
`docker cp`, sem tocar o volume do Postgres) e pouco antes de rodar
`python scripts/eval_search.py --mode both`, o Docker Desktop da máquina caiu e voltou
sozinho (falha reportada pelo coordenador como "interrupção por limite de gasto da API", não
uma ação deste worker). Ao voltar, os containers `opportunity-radar-{api,worker,postgres,
frontend}-1` estavam todos `Exited (255)` — o motor do Docker reiniciou e nenhum deles tem
`restart` configurado no `compose.yaml` (só `migrate` declara `restart: "no"` explicitamente;
os demais também não reiniciam sozinhos). **Este worker não deu `docker compose down/stop`
nem qualquer comando de escrita** — a instrução era explícita para nunca reiniciar o stack
real, então este worker também não deu `docker compose up`/`docker start` para trazê-lo de
volta, mesmo estando parado por um motivo externo.

**Isto significa que a rodada de `eval_search.py --mode both` desta rotulagem não foi
executada** — o container caiu entre a cópia do arquivo e a execução do comando. O comando
exato para rodar assim que alguém (com autorização para reiniciar o stack real) trouxer os
containers de volta:

```bash
docker cp data/search-reference/queries.json opportunity-radar-api-1:/app/data/search-reference/queries.json
docker exec opportunity-radar-api-1 python scripts/eval_search.py --mode both
```

Sem essa medição, **F17-03/F20-01 continuam "Em revisão"**: o gabarito agora é
metodologicamente mais correto (candidatos vêm de full-text sobre `description`, não de
substring de título), mas os números comparáveis (`recall@10 like` vs `recall@10 fulltext`)
com este gabarito ainda não existem.

## Limitações

- O critério de candidato ainda é `LIKE` sobre `description` (substring simples), não o
  `search_document`/`plainto_tsquery` real do modo `fulltext` do produto — por isso ele
  reproduz falsos positivos de substring (`java`/`javascript`, `aws`/`laws`) que o
  `to_tsvector` com `unaccent` e stemming do produto real provavelmente não teria. Isso é
  intencional: o objetivo aqui é ampliar o universo de candidatos além do título (evitar o
  viés documentado), não reproduzir o ranking exato do produto.
- `kubernetes` e `frontend` seguem sem avaliação por `like` (a consulta antiga nunca teve
  candidato para elas); a comparação `like` vs `fulltext` para essas duas consultas específicas
  só é possível olhando o `recall@10` do modo `fulltext` isoladamente.
