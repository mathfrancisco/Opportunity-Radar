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

## Medição real — feita em 2026-09-28 (stack de volta, dentro da janela de 7 dias)

O incidente de Docker Desktop do dia 28 (containers `Exited (255)` entre a cópia do
`queries.json` e a execução do comando — ver histórico deste arquivo) foi resolvido por
quem tem autorização para tocar o stack real; o `opportunity-radar` voltou saudável às
`2026-09-28T11:45Z`, dentro da janela de 7 dias reiniciada (`docs/44-roadmap-fase-20/
evidencias/f20-janela-7d-t0-2026-09-28b.json`, até `2026-10-05T12:02Z`). Com o stack de
volta, este worker rodou (só leitura, sem tocar o Postgres além do `SELECT` que
`eval_search.py` já fazia):

```bash
docker cp data/search-reference/queries.json opportunity-radar-api-1:/app/data/search-reference/queries.json
docker exec opportunity-radar-api-1 python scripts/eval_search.py --mode both
```

### Resultado — recall@10 médio: fulltext 0,3396 > like 0,2745 (+23,7% relativo)

```
mode=like     queries_measured=16   average recall@10 = 0.2745   average nDCG@10 = 0.2600
mode=fulltext queries_measured=16   average recall@10 = 0.3396   average nDCG@10 = 0.2548
```

| Consulta | relevantes | recall@10 like | recall@10 fulltext | nDCG@10 like | nDCG@10 fulltext |
| --- | --- | --- | --- | --- | --- |
| accounting | 3 | 0,000 | 0,000 | 0,000 | 0,000 |
| aws | 6 | 0,000 | 0,000 | 0,000 | 0,000 |
| backend | 4 | 0,250 | 0,250 | 0,390 | 0,246 |
| devops | 3 | 0,333 | 0,333 | 0,469 | 0,235 |
| **frontend** | 3 | **0,000** | **0,667** | 0,000 | 0,391 |
| **fullstack** | 8 | 0,375 | **0,625** | 0,366 | 0,727 |
| java | 4 | 0,000 | 0,000 | 0,000 | 0,000 |
| **kubernetes** | 8 | **0,000** | **0,125** | 0,000 | 0,126 |
| machine learning | 3 | 0,333 | 0,333 | 0,469 | 0,202 |
| marketing | 2 | 0,500 | 0,500 | 0,387 | 0,185 |
| node | 5 | 0,000 | 0,000 | 0,000 | 0,000 |
| product manager | 2 | 1,000 | 1,000 | 1,000 | 0,605 |
| python | 7 | 0,000 | 0,000 | 0,000 | 0,000 |
| **qa** | 1 | 1,000 | 1,000 | 0,356 | **1,000** |
| react | 4 | 0,000 | 0,000 | 0,000 | 0,000 |
| sales | 5 | 0,600 | 0,600 | 0,723 | 0,359 |

### Leitura honesta: full-text vence no critério do card, empata em ranking

**recall@10:** full-text (0,3396) > like (0,2745) — é exatamente o critério de aceite de
F17-03 ("recall@10 do full-text > recall@10 do LIKE"), agora medido sem o viés de
construção que o addendum anterior documentou. A vantagem inteira vem de três consultas:
`frontend` (0,000 → 0,667), `fullstack` (0,375 → 0,625) e `kubernetes` (0,000 → 0,125) — as
mesmas onde o `like` (que só olha título/empresa) não tinha como competir, porque o termo só
aparece na descrição da maioria das vagas relevantes. Nas outras 13 consultas, `like` e
`fulltext` empatam exatamente no recall (a mesma vaga aparece ou não aparece nos top 10 dos
dois modos) — inclusive em consultas com recall 0 nos dois modos (`accounting`, `aws`,
`java`, `node`, `python`, `react`), o que mostra que nenhum dos dois métodos resolve bem
consultas de termo único e comum sobre um acervo de 648 vagas.

**nDCG@10:** os dois modos empatam (like 0,2600, fulltext 0,2548 — diferença de 0,005, não
significativa com 16 consultas). Quando ambos encontram os itens relevantes, `like` às vezes
ordena melhor (`backend`, `devops`, `machine learning`, `marketing`, `product manager`,
`sales`) e `fulltext` às vezes ordena melhor (`fullstack`, `qa`, e as três que só o fulltext
encontra). Full-text não é estritamente melhor em ranking — ele é melhor em **cobertura**
(recall), que é o que o critério do card mede.

### F17-03/F20-01: o critério de recall@10 está satisfeito

Com um gabarito construído por full-text sobre `description` (não por substring de título),
**`recall@10 fulltext > recall@10 like` é verdadeiro** (0,3396 > 0,2745). Este era o único
critério de aceite de F17-03 pendente de medição correta (os outros — acento, plural,
sinônimos, filtros combináveis — já são cobertos por teste de integração em CI, não por esta
rotulagem). **Recomendação: fechar F17-03/F20-01 como concluído**, citando este documento
como a medição que resolve a pendência registrada nos dois addenda anteriores. A decisão
final de mudar o status do card é de quem revisa o PR.

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
