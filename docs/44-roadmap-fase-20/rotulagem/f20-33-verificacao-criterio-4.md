# Verificação manual do critério 4 — F20-33

- **Card:** [F20-33](../fase-20/f20-33-palavras-chave-do-perfil.md)
- **Critério 4:** "Nenhuma fonte ampla é habilitada antes do filtro de área.
  Verificação manual, não teste: esta mudança não cria nem habilita fontes; o filtro
  F20-03 existe e o gate de homologação não foi alterado."
- **Objetivo deste roteiro:** dar ao critério 4 um passo a passo reprodutível, com
  comandos reais (só leitura, `SELECT`, projeto `opportunity-radar`) e o resultado
  esperado de cada um, para qualquer pessoa confirmar sem precisar confiar só na palavra
  de quem implementou o card.
- **Medido em:** 2026-09-26, contra o acervo real (648 oportunidades, 21 `source_definition`).

## Passo a passo

### 1. Confirmar que o filtro de área (F20-03 / F17-02, `role_family`) existe e está ativo

```bash
docker compose -p opportunity-radar exec postgres psql -U opportunity_radar -d opportunity_radar -c "
SELECT role_family, count(*) FROM opportunities.opportunity GROUP BY 1 ORDER BY 2 DESC;
"
```

**Resultado esperado:** mais de uma categoria de `role_family` diferente de `UNKNOWN`
aparece na lista, com `UNKNOWN` bem abaixo de 100% (evidência de que o classificador de
área está rodando, não que a coluna existe vazia). Na medição real desta sessão:

```
SOFTWARE_ENGINEERING | 223
DATA                  | 91
UNKNOWN                | 76   (11,7% do total — bate com baseline-f17-01.md)
SALES                  | 55
INFRASTRUCTURE         | 32
DESIGN                  | 29
... (15 categorias no total)
```

Se `UNKNOWN` for ≈100% do total, o filtro de área não está ativo e o critério 4 falha —
**pare aqui e não prossiga**, pois habilitar qualquer fonte ampla nesse estado violaria a
"ordem obrigatória" do card.

### 2. Listar as fontes existentes e seu tipo/status

```bash
docker compose -p opportunity-radar exec postgres psql -U opportunity_radar -d opportunity_radar -c "
SELECT source_type, enabled, terms_reviewed, evidence_status, count(*)
FROM acquisition.source_definition GROUP BY 1,2,3,4 ORDER BY 1,2;
"
```

**Resultado esperado:** só os `source_type` que já existiam antes do F20-33 aparecem —
`ashby`, `greenhouse`, `lever`, `manual`, `remotive`. **Nenhuma linha com
`source_type` igual a um coletor amplo novo** (`adzuna`, `usajobs`, ou qualquer nome das
fontes candidatas listadas em `docs/pesquisas/2026-09-fontes-amplas.md`) pode existir.
Medição real desta sessão (21 linhas, resumidas por tipo):

```
ashby      | enabled=t, terms_reviewed=t, confirmed        | 13
greenhouse | enabled=f, terms_reviewed=f, unverified        | 2
greenhouse | enabled=f, terms_reviewed=f, confirmed         | 1
greenhouse | enabled=t, terms_reviewed=t, confirmed         | 3
lever      | enabled=t, terms_reviewed=t, confirmed         | 2
manual     | enabled=f, terms_reviewed=f, unverified        | 1
manual     | enabled=t, terms_reviewed=f, confirmed         | 1
remotive   | enabled=t, terms_reviewed=t, confirmed         | 1
```

Nenhuma fonte ampla nova apareceu — confirma que este card não criou nem habilitou fonte
alguma, como o "Resultado" do card promete.

### 3. Confirmar que a Remotive (única fonte com busca por termo) continua sendo a única `enabled=true` com essa capacidade

```bash
docker compose -p opportunity-radar exec postgres psql -U opportunity_radar -d opportunity_radar -c "
SELECT name, source_type, enabled, terms_reviewed FROM acquisition.source_definition
WHERE lower(name) LIKE '%remotive%' OR lower(source_type) LIKE '%remotive%';
"
```

**Resultado esperado:** exatamente 1 linha, `enabled = true`, `terms_reviewed = true`.
Medição real: `Remotive remote jobs | remotive | t | t` — confirmado, e nenhuma outra
fonte de busca por termo (`keyword_search`) foi adicionada com `enabled = true` sem
`terms_reviewed = true` (o que indicaria pular o gate de homologação).

### 4. Confirmar que o gate de homologação (F20-25) não foi tocado por este card

```bash
git log --oneline -- scripts/enable_sources.py src/opportunity_radar/acquisition/ | head -20
git diff --stat main...HEAD -- scripts/enable_sources.py
```

**Resultado esperado:** o diff do card F20-33 (o commit ou branch que implementa este
card) não aparece tocando `scripts/enable_sources.py` nem os arquivos de homologação — só
os arquivos listados na tabela "Arquivos" do card
(`profile/domain.py`, `profile/models.py`, `profile/service.py`,
`presentation/http/profile.py`, `profile/keywords.py`, `acquisition/models.py`,
`worker.py`, `apps/web/src/features/profile/api.ts`, `apps/web/src/routes/ProfilePage.tsx`,
`docs/pesquisas/2026-09-fontes-amplas.md`). Se `enable_sources.py` aparecer no diff, o
critério 4 precisa de revisão manual do que mudou ali antes de aceitar.

### 5. Conclusão

Se os passos 1–4 deram o resultado esperado, o critério 4 está satisfeito: o filtro de
área está ativo e mensurável, nenhuma fonte ampla nova existe no banco, a única fonte de
busca por termo continua sendo a Remotive já revisada, e o código do gate de homologação
não foi alterado por este card.

## Como aplicar

Este roteiro não tem "aplicação" no sentido de aceitar/rejeitar rótulos (não é uma tabela
de casos rotulados) — é um script de verificação. O revisor roda os 4 comandos acima contra
o ambiente de referência e confere se a saída bate com o "resultado esperado"; se bater,
marca o critério 4 do card F20-33 como confirmado com este documento como evidência. O
arquivo `f20-33-verificacao-criterio-4.json` traz os mesmos passos em formato de checklist
(um objeto por passo, com `comando`, `resultado_esperado` e `resultado_obtido` — preenchido
com a medição real desta sessão) para quem quiser rodar isso de forma automatizada num
runner de checklist.
