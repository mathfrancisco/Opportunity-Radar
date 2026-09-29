# CARD F20-51 — Wellfound como fonte de vagas

- **Status:** Fechado — não viável. Revisão de termos em
  [`docs/pesquisas/wellfound-yc-jobs.md`](../../pesquisas/wellfound-yc-jobs.md)
  (2026-09-28): os Termos de Uso da Wellfound (Seção III — Covenants) proíbem nomeadamente
  "harvesting, collection ou 'scraping'" de Content e uso automatizado do site "for
  competitive purposes" — a descrição exata da operação de um coletor ou de uma sonda de
  descoberta de empresa. Wellfound também usa DataDome + Cloudflare em todo o fluxo de
  busca de vaga, o que bloquearia tecnicamente qualquer coleta de baixa frequência sem
  login mesmo se os Termos permitissem. Nenhum código foi escrito: nenhum arquivo em
  `src/opportunity_radar/acquisition/` foi criado ou alterado para este card.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-27, F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); pedido do usuário em
  2026-09-28 ("automatizar coleta de wellfound.com/jobs e ycombinator.com/jobs"), tratado
  com a mesma régua do F20-32 (Gupy) e do guarda-chuva F17-10.

## Contexto

Wellfound (`wellfound.com/jobs`, ex-AngelList Talent) lista vagas de startups e foi avaliado
como candidato a fonte direta de vagas e, alternativamente, como fonte de descoberta de
empresa (lista de empresas com vaga aberta -> `probe_direct_ats` do F20-27/F20-36 nos ATS já
suportados). Os dois usos exigem acesso automatizado ao site.

## Escopo

1. **Revisão de termos** do Wellfound, registrada em `docs/pesquisas/` antes de qualquer
   código, cobrindo: `robots.txt`, Termos de Uso, existência de API pública, autenticação
   e anti-bot. Endpoint/site que proíbe acesso automatizado encerra o card.
2. Se viável: coletor com a interface dos atuais (`source_type`, `CollectorCapabilities`,
   `discover`, telemetria, política de rede, retentativa, validador de chave) ou, se viável
   só como descoberta, integração com `limited_discovery.py` (F20-36).
3. Se viável: board falso em `tests/e2e/`, integração com `PROBE_TYPES`/`IDENTIFIER_KEYS`/
   `SUPPORTED_ATS`/formulário de criação de fonte.

## Fora de escopo

- Qualquer fonte que exija login ou proíba automação.
- Contornar DataDome/Cloudflare ou qualquer outro bloqueio de bot.
- Raspagem de HTML/DOM quando não existe endpoint estruturado.

## Resultado da revisão de termos

**Não viável — coleta direta e descoberta de empresa, as duas.** Ver
`docs/pesquisas/wellfound-yc-jobs.md` para o texto completo. Resumo:

- `robots.txt` isoladamente não bloqueia `/jobs` nem páginas de vaga sem parâmetros
  específicos — mas isso não decide a viabilidade (mesma regra do F20-32).
- Termos de Uso, Seção III: proíbem nomeadamente "harvesting, collection ou 'scraping'" de
  Content, uso automatizado que gere carga acima do que "a human can reasonably produce"
  e "uso para fins competitivos" (exatamente o que um radar de oportunidades faz ao
  reagregar vagas). A única exceção nomeada é para buscadores públicos, revogável, e não
  cobre agregadores de vaga.
- Não há API pública; o GraphQL interno exige sessão autenticada + CSRF + cookie DataDome.
  DataDome/Cloudflare bloqueiam com 403 + captcha qualquer acesso sem esses cookies —
  barreira técnica, além da contratual.
- Usar Wellfound só como lista de nomes de empresa (sem coletar a vaga) ainda é
  "harvesting/collection" automatizado do Content do site — a cláusula não distingue por
  volume de dado extraído.

## Critérios de aceite

- [x] Termos revisados e registrados antes do código — `docs/pesquisas/wellfound-yc-jobs.md`,
      decisão: não viável. Os critérios seguintes não se aplicam: o card fecha aqui,
      conforme a regra "endpoint que proíbe acesso automatizado encerra o sub-card"
      (F17-10) e o mesmo padrão do F20-32.
- [ ] Coletor ou integração de descoberta com teste. — N/A (não viável)
- [ ] Sonda, proposta, cadastro e formulário reconhecem a fonte nova. — N/A (não viável)
- [ ] Pelo menos uma empresa real coletada via Wellfound. — N/A (não viável)

## Verificação

- **CI:** nenhuma — nenhum código foi escrito.
- **Máquina de referência:** nenhuma chamada de coleta foi feita; as únicas requisições
  desta pesquisa foram `robots.txt` e a página pública de Termos de Uso, listadas em
  `docs/pesquisas/wellfound-yc-jobs.md`.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `docs/pesquisas/wellfound-yc-jobs.md` | Revisão de termos, robots.txt, API e anti-bot da Wellfound e da YC/Work at a Startup, feita em conjunto (mesma pesquisa, dois cards). Entregável final deste card: decisão "não viável". |

## Não fazer

- Não implementar coletor, sonda ou integração de descoberta para Wellfound.
- Não fazer chamada real a boards/GraphQL da Wellfound além das verificações de
  `robots.txt`/Termos já registradas.
- Não contornar DataDome, Cloudflare ou qualquer bloqueio de bot.

## Pronto quando

A revisão de termos está registrada com decisão e evidência, e o card está marcado como
fechado — não viável, sem código pendente.
