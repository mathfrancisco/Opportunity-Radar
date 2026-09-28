# Rotulagem F20-23 — Amostra real de campos UNKNOWN para a medição de precisão

- **Card:** [F20-23](../fase-20/f20-23-classificacao-assistida.md)
- **Branch:** `feature/f20-rotulos-2`
- **Objetivo:** o card F20-23 exige medir a precisão da sugestão do modelo `fast` antes de
  ligar `worker_suggest_enabled` por padrão (`docs/pesquisas/sugestoes-f20-23.md`). Este
  documento é o passo 1 desse plano: uma amostra real de vagas com `role_family`,
  `seniority` ou `work_mode` `UNKNOWN`, cada campo com o valor correto recomendado e a
  evidência literal que sustenta a recomendação — o gabarito contra o qual a rodada real do
  Groq (passo 3 do plano) será comparada.
- **Medido em:** 2026-09-28, `docker compose -p opportunity-radar exec postgres psql`
  (somente `SELECT`, banco real, stack saudável desde `2026-09-28T11:45Z`, janela de sete
  dias até `2026-10-05T12:02Z` — nenhuma escrita, nenhum restart).
- **Metodologia:** as 30 oportunidades mais recentes com pelo menos um dos três campos
  `UNKNOWN` (39 instâncias de campo no total — algumas vagas têm 2 ou 3 campos `UNKNOWN`).
  Para cada campo, buscou-se um trecho literal da `description` que indicasse o valor
  correto (anos de experiência, palavra de nível, modelo de trabalho explícito, natureza do
  papel). **Quando nenhuma evidência textual convincente foi encontrada, a recomendação é
  manter `UNKNOWN`** em vez de adivinhar — isso também é sinal útil: mede o quanto do
  `UNKNOWN` real é genuinamente ambíguo mesmo para leitura humana. Toda recomendação é do
  agente; o usuário pré-autorizou aceitar como estão
  (`decisao_usuario`: `"aceito (pre-autorizado)"`). Dataset completo em
  `f20-23-amostra-unknown.json`. Nenhum nome de pessoa, e-mail ou telefone aparece nas
  evidências usadas (textos de vaga: benefícios, modelo de trabalho, requisitos de
  experiência).

## Resultado: 30 vagas, 39 campos UNKNOWN, 30 corrigidos com evidência, 9 mantidos UNKNOWN

| Campo | Instâncias | Recomendação com evidência | Mantido UNKNOWN (evidência insuficiente) |
| --- | --- | --- | --- |
| `role_family` | 2 | 2 | 0 |
| `seniority` | 24 | 15 | 9 |
| `work_mode` | 13 | 13 | 0 |
| **Total** | **39** | **30 (77%)** | **9 (23%)** |

Confiança das 30 recomendações: 19 `alta` (evidência direta e inequívoca — título com o
nível, frase "on-site"/"remote"/"hybrid" explícita, "Senior Product Manager" etc.) e 11
`media` (evidência indireta — anos de experiência sem palavra de nível explícita, ou
inferência razoável mas não 100% literal).

### Padrões encontrados

- **`work_mode` teve evidência para 100% dos casos** (13/13): a maioria das vagas da Nubank
  usa uma seção padronizada `"Work Model for this Role"` (`Hybrid 2-3 times/week`, etc.) que
  a regra atual aparentemente não lê; duas vagas de SDR do n8n já tinham o modo no próprio
  título (`"(Hybrid)"`, `"(Berlin Hybrid)"`) e mesmo assim ficaram `UNKNOWN` — indício de que
  a extração de `work_mode` não olha o título nesses casos.
- **`seniority` é o campo mais genuinamente ambíguo:** 9/24 (37,5%) não tinham nenhuma
  palavra de nível (`senior`/`staff`/`lead`/`manager`/`junior`) nem menção de anos de
  experiência no texto pesquisado — nem um leitor humano teria uma base literal para decidir.
  Dos 15 restantes, 2 casos (`"Senior Staff Software Engineer"`, `"Senior Engineering
  Manager"`) exigiram uma escolha de mapeamento porque o enum do produto não tem um nível
  composto: `"Staff"` e `"Manager"` foram escolhidos como o termo mais específico do título
  composto, com `"Senior"` tratado como modificador.
- **Falsos positivos de palavra-chave, não usados:** em pelo menos 3 vagas (`Agentic
  Engineering Platform Engineer`, duas de SDR do n8n) a única ocorrência de "senior" no texto
  se referia a *outra pessoa* (colegas, stakeholders do cliente), não ao nível do próprio
  cargo — por isso entraram como "evidência insuficiente" em vez de uma recomendação errada.
- **`role_family` teve só 2 instâncias na amostra** (a maioria das vagas UNKNOWN da amostra
  já tinha `role_family` resolvido pela regra, só `seniority`/`work_mode` faltando); ambas
  tiveram evidência clara (`FINANCE` para um cargo de controladoria, `SALES` para um GTM
  Strategist que qualifica leads para Account Executives).

## Como usar no passo 3 (rodada real do Groq)

Este arquivo é o gabarito: para cada uma das 30 oportunidades, rodar
`opportunity_radar.opportunities.suggestions.suggest_fields` (rota `job_classification`,
modelo `fast`, chave real do Groq) e comparar a saída com `valor_recomendado` de
`f20-23-amostra-unknown.json` — para os 9 campos `manter_unknown_evidencia_insuficiente`, o
comportamento correto do modelo também é não sugerir nada com confiança (ou ser descartado
pelo filtro de evidência), então uma sugestão "confiante" nesses 9 casos conta contra a
precisão, não a favor.

Comando exato (fora deste PR; projeto Docker isolado, nunca `opportunity-radar`, chave real
do Groq só aqui):

```bash
docker compose -p f20cls-precisao -f compose.yaml -f compose.dev.yaml run --rm \
  -e AI_ENABLED=true -e AI_PROVIDER=groq -e GROQ_API_KEY=<chave real> \
  api python scripts/run_f20_23_precision.py \
  --gabarito docs/44-roadmap-fase-20/rotulagem/f20-23-amostra-unknown.json
```

(`scripts/run_f20_23_precision.py` ainda não existe — é um script pontual a escrever no PR
que fizer a rodada real, lendo os 30 `opportunity_id` do gabarito acima, chamando
`suggest_fields` uma vez por oportunidade contra o Postgres isolado do projeto
`f20cls-precisao` — que precisa ter as mesmas 30 linhas replicadas ou apontar para uma cópia
anonimizada do acervo real — e comparando `OpportunitySuggestionModel.value`/`evidence` com
`valor_recomendado`/`evidencia` deste gabarito; nunca contra o projeto `opportunity-radar`
em execução.) Métrica a registrar em `docs/pesquisas/sugestoes-f20-23.md`: precisão
(sugestões que batem com o gabarito / sugestões com evidência válida) e taxa de descarte por
evidência, separado por campo (`role_family`/`seniority`/`work_mode`).
