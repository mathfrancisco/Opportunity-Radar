# CARD F20-70 — Fechar lacunas de palavra-chave do normalizador de senioridade (trainee, estagiário, entry level, new grad, graduate, early career, apprentice/aprendiz)

- **Status:** Feito — regras e testes mesclados (`4d5b973`, `5a1e062`); acervo real reprocessado para `v6`/`seniority-v3` em 2026-09-29 (critério de aceite 4; `docs/44-roadmap-fase-20/evidencias/rebuild-stack-real-2026-09-29.md` §5 e §8). O UNKNOWN geral não mudou (49,42%): nenhuma vaga UNKNOWN do acervo real tem título com essas palavras-chave (próxima fase: F20-76).
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** A — Fechamento do que está em revisão
- **Depende de:** F20-02
- **Origem:** diagnóstico "por que a busca traz tão poucas vagas junior/estágio",
  registrado em
  [`docs/44-roadmap-fase-20/evidencias/diagnostico-vagas-junior-2026-09-28.md`](../evidencias/diagnostico-vagas-junior-2026-09-28.md)
  (2026-09-28). Nenhum código foi alterado durante o diagnóstico; este card
  materializa o que ele encontrou.

## Contexto

`infer_seniority` (`src/opportunity_radar/opportunities/domain.py:845-877`,
`SENIORITY_MAPPING_VERSION = "seniority-v2"`) tem dois problemas de regex confirmados
por teste isolado (interpretador Python do host, sem alterar código):

1. O padrão de INTERN, `r"\best[aá]gi[oa]\b"`, casa só a forma substantivo
   ("estágio"/"estágia"), não a forma pessoa/adjetiva "estagiário"/"estagiária", que é
   a forma mais comum em título de vaga brasileira ("Vaga de Estagiário de X").
2. Não existe nenhum padrão para `trainee`, `entry level`, `new grad`, `graduate`,
   `early career`, `apprentice` ou `aprendiz` — vagas com esses termos explícitos no
   título caem em UNKNOWN.

No acervo real auditado (2288 vagas, base `f20manual`), o impacto medido hoje é **zero**
— nenhum título usa esses termos ainda. É um bug latente que vai comer parte do ganho
de qualquer card que traga fontes brasileiras de estágio/trainee (F20-60 e além).

## Escopo

1. Corrigir o padrão de INTERN para casar também a forma pessoa/adjetiva:
   `estagiário`/`estagiária`/`estagiario`/`estagiaria` (com e sem acento), mantendo
   `estágio`/`estágia` já cobertos.
2. Adicionar padrões para `trainee` → INTERN (o programa trainee brasileiro é
   equivalente a estágio/entry-level no domínio deste app, não um nível intermediário)
   e para `entry level`/`entry-level`, `new grad`, `graduate` (isolado, cuidado com
   falso positivo em "Graduate School"/nome de curso — restringir a
   `\bgraduate\b` só quando não seguido de "school"/"degree"/"program" acadêmico, se o
   teste de regressão mostrar ruído), `early career`, `apprentice`, `aprendiz` → JUNIOR
   ou INTERN, decidir caso a caso com evidência de título real (Greenhouse "Early
   Career" costuma ser JUNIOR, não INTERN).
3. Bump de `SENIORITY_MAPPING_VERSION` (`seniority-v2` → `seniority-v3`), mesma
   convenção usada por `SKILL_TAXONOMY_VERSION`/`NORMALIZER_VERSION` no F20-02.
4. Testes de regressão por termo (pt-BR e EN), incluindo os casos negativos que já
   passam hoje (não regredir `senior`/`sr`/`pleno`/`mid` etc.) e os falsos-positivos
   verificados no diagnóstico (não recapturar "internal"/"international" — isso já não
   ocorre porque o padrão usa título com `\b`, não descrição; manter assim, ver
   F20-71 para a decisão de não estender a descrição).
5. Reprocessamento do acervo real com evidência (mesmo padrão do F20-02:
   `docs/44-roadmap-fase-20/evidencias/reprocessamento-skills-v3-2026-09-27.md`), para
   confirmar que a migração de versão não altera nenhuma vaga já classificada como
   SENIOR/MID/etc. (só preenche parte do UNKNOWN, se houver título correspondente).

## Fora de escopo

- Estender `infer_seniority` para olhar `description` — decisão separada, ver
  observação #4 do diagnóstico; teste do diagnóstico mostrou risco de falso positivo
  com scan simples. Se alguém quiser fazer isso, precisa de padrões de seção estreitos
  como `_work_mode_from_description`, não um scan de palavra solta — card próprio.
- Fechar F20-02 (UNKNOWN geral) — este card corrige regras específicas de
  junior/estágio, não resolve o critério de aceite completo do F20-02.
- Adicionar fontes novas de vagas junior/estágio (ver F20-71).

## Critérios de aceite

- [ ] Teste cobrindo `estagiário`/`estagiária` (com/sem acento) → INTERN.
- [ ] Teste cobrindo `trainee`, `entry level`, `new grad`, `graduate`, `early career`,
      `apprentice`, `aprendiz` com evidência de qual enum cada termo mapeia e por quê.
- [ ] `SENIORITY_MAPPING_VERSION` incrementada com comentário explicando a mudança,
      mesma convenção do F20-02.
- [ ] Reprocessamento do acervo real rodado e verificado: nenhuma vaga que já tinha
      senioridade não-UNKNOWN muda de valor; contagem de quantas vagas UNKNOWN
      passaram a ter senioridade preenchida registrada em
      `docs/44-roadmap-fase-20/evidencias/`.

## Não fazer

- Não tocar `infer_work_mode`/`infer_contract_type` neste card, mesmo que usem o mesmo
  helper `_infer_unique` — escopo é só senioridade.
- Não adicionar campo estruturado a `HOMOLOGATED_SENIORITY_FIELDS` sem evidência de
  fixture real (mesma regra já documentada no comentário do código).

## Verificação

- **CI:** suíte de testes de `opportunities/domain.py` (normalizador).
- **Máquina de referência:** reprocessamento do acervo real, evidência registrada em
  `docs/44-roadmap-fase-20/evidencias/`.

## Pronto quando

Os termos listados no escopo tiverem teste de regressão passando, a versão do mapa
estiver incrementada, e o reprocessamento real confirmar zero regressão nas vagas já
classificadas.
