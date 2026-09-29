# CARD F20-76 — Classificar senioridade pelo conteúdo da vaga

- **Status:** Backlog (próxima fase; não bloqueia o F20-50 nem o merge do PR #25)
- **Fase:** 20 — IA cloud e consolidação (item herdado para a próxima fase)
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-02, F20-23, F20-70
- **Origem:** remedição de senioridade na stack real em 2026-09-29
  ([`rebuild-stack-real-2026-09-29.md`](../evidencias/rebuild-stack-real-2026-09-29.md) §8):
  `UNKNOWN` 339/686 = 49,42%, contra a meta de ~25% do F17-06/F20-02 (metade de 50,62%).

## Resultado

A senioridade de vagas sem sinal no título passa a ser inferida do corpo da vaga, reduzindo o
`UNKNOWN` em direção à meta de ~25% sem inventar valor.

## Contexto

O `seniority-v3` (F20-70) só preenche título `UNKNOWN` com palavra-chave (trainee,
estagiário, entry level, new grad, graduate, early career, apprentice/aprendiz). Depois do
reprocessamento `v6`/`seniority-v3` na stack real, o `UNKNOWN` ficou em 49,42% e
JUNIOR+INTERN em 0,73% (5 vagas): nenhuma das 339 vagas `UNKNOWN` tem título com esses
termos. O grosso é título sem sinal de senioridade, fora do alcance de regra por título.

## Escopo

- Levantar, no acervo real, sinais de senioridade no corpo da vaga (anos de experiência,
  "junior", "entry-level", "senior" em requisitos) e medir precisão por regra contra um
  gabarito rotulado, antes de qualquer gravação.
- Avaliar o uso das sugestões do F20-23 (`field_suggestion`, `seniority`) quando a cota do
  Groq permitir: ampliar o gabarito (hoje 30 vagas, precisão de `seniority` 73%) e só ligar
  `worker_suggest_enabled` para `seniority` se o critério do card permitir.
- Manter valor canônico do normalizador intacto: a sugestão propõe, o humano aceita.

## Fora de escopo

- Alterar elegibilidade, score, veredito ou fatores do matching.
- Reprocessar o acervo sem backup verificado.

## Critérios de aceite

- [ ] Regra ou sugestão com precisão medida contra gabarito versionado, sem valor errado
      gravado como canônico.
- [ ] Remedição do `UNKNOWN` no acervo real, com o número antes e depois registrado em
      `evidencias/`.
- [ ] Se a meta de ~25% não for atingida, registrar o motivo verificado.

## Testes

- Teste por regra nova com texto real (fixture) e teste de que título com sinal continua
  vencendo o corpo.

## Pronto quando

Os critérios de aceite estão marcados e o CI está verde.
