# CARD F20-52 — Y Combinator Jobs / Work at a Startup como fonte de vagas

- **Status:** Fechado — não viável. Revisão de termos em
  [`docs/pesquisas/wellfound-yc-jobs.md`](../../pesquisas/wellfound-yc-jobs.md)
  (2026-09-28): os Termos de Uso da Y Combinator (`ycombinator.com/legal`, seção que também
  descreve o programa Work at a Startup) proíbem, no corpo geral do documento, "data
  mining, robots, scraping ou métodos similares de coleta ou extração de dados" em conexão
  com o uso do Site — sem exceção, sem qualificar por volume ou frequência. Nenhum código
  foi escrito: nenhum arquivo em `src/opportunity_radar/acquisition/` foi criado ou
  alterado para este card.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-27, F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); pedido do usuário em
  2026-09-28 ("automatizar coleta de wellfound.com/jobs e ycombinator.com/jobs"), tratado
  com a mesma régua do F20-32 (Gupy) e do guarda-chuva F17-10.

## Contexto

Y Combinator publica vagas de empresas do seu portfólio em `ycombinator.com/jobs` e no
produto dedicado Work at a Startup (`workatastartup.com`, "WaaS"). Foi avaliado como
candidato a fonte direta de vagas e, alternativamente, como fonte de descoberta de empresa
(lista de empresas do batch YC -> `probe_direct_ats` do F20-27/F20-36 nos ATS já
suportados, já que muitas startups YC usam Ashby/Greenhouse, que o radar já coleta).

## Escopo

1. **Revisão de termos** da YC/WaaS, registrada em `docs/pesquisas/` antes de qualquer
   código, cobrindo: `robots.txt` dos dois domínios, Termos de Uso, existência de API
   pública/Algolia documentada, autenticação e anti-bot. Endpoint/site que proíbe acesso
   automatizado encerra o card.
2. Se viável: coletor com a interface dos atuais (`source_type`, `CollectorCapabilities`,
   `discover`, telemetria, política de rede, retentativa, validador de chave) ou, se viável
   só como descoberta, integração com `limited_discovery.py` (F20-36).
3. Se viável: board falso em `tests/e2e/`, integração com `PROBE_TYPES`/`IDENTIFIER_KEYS`/
   `SUPPORTED_ATS`/formulário de criação de fonte.

## Fora de escopo

- Qualquer fonte que exija login ou proíba automação.
- Reverse engineering de chamada interna (Algolia ou outra) sem contrato de API público.
- Raspagem de HTML/DOM quando não existe endpoint estruturado.

## Resultado da revisão de termos

**Não viável — coleta direta e descoberta de empresa, as duas.** Ver
`docs/pesquisas/wellfound-yc-jobs.md` para o texto completo. Resumo:

- `robots.txt` de `ycombinator.com` (`Allow: /`, sem regra para `/jobs`) e de
  `workatastartup.com` (`Disallow:` vazio) liberam a leitura por si só — mas isso não
  decide a viabilidade (mesma regra do F20-32).
- Termos de Uso da YC: "In connection with your use of the Site you will not engage in or
  use any data mining, robots, scraping or similar data gathering or extraction methods."
  Sem exceção para buscadores (diferente de Wellfound), sem qualificar por volume — mais
  direta que a cláusula da Gupy. A mesma página descreve o programa Work at a Startup, ou
  seja, é o documento que rege o próprio WaaS, não um texto de produto não relacionado.
  `workatastartup.com/terms` existe como página própria sob o mesmo guarda-chuva legal.
  Há também cláusula de uso comercial ("not... exploit... for any commercial purposes, any
  portion of the Site") e de anti-evasão de bloqueio.
- Não há API pública documentada. O front-end de `workatastartup.com` usa Algolia
  internamente, mas sem chave pública nem contrato estável — só observado por projetos de
  terceiros via reverse engineering, o que é a própria "extraction method" proibida.
- Usar YC/WaaS só como lista de nomes de empresa por batch (sem coletar a vaga) ainda é
  "data mining ... data gathering or extraction methods" do Site da YC — a cláusula não
  distingue por tipo de dado extraído.

## Critérios de aceite

- [x] Termos revisados e registrados antes do código — `docs/pesquisas/wellfound-yc-jobs.md`,
      decisão: não viável. Os critérios seguintes não se aplicam: o card fecha aqui,
      conforme a regra "endpoint que proíbe acesso automatizado encerra o sub-card"
      (F17-10) e o mesmo padrão do F20-32.
- [ ] Coletor ou integração de descoberta com teste. — N/A (não viável)
- [ ] Sonda, proposta, cadastro e formulário reconhecem a fonte nova. — N/A (não viável)
- [ ] Pelo menos uma empresa real coletada via YC/WaaS. — N/A (não viável)

## Verificação

- **CI:** nenhuma — nenhum código foi escrito.
- **Máquina de referência:** nenhuma chamada de coleta foi feita; as únicas requisições
  desta pesquisa foram `robots.txt` (dois domínios) e as páginas públicas de Legal/Termos,
  listadas em `docs/pesquisas/wellfound-yc-jobs.md`.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `docs/pesquisas/wellfound-yc-jobs.md` | Revisão de termos, robots.txt, API e anti-bot da Wellfound e da YC/Work at a Startup, feita em conjunto (mesma pesquisa, dois cards). Entregável final deste card: decisão "não viável". |

## Não fazer

- Não implementar coletor, sonda ou integração de descoberta para YC Jobs/Work at a
  Startup.
- Não fazer chamada real a boards/Algolia da YC além das verificações de
  `robots.txt`/Termos já registradas.
- Não fazer reverse engineering de endpoint interno sem contrato de API público.

## Pronto quando

A revisão de termos está registrada com decisão e evidência, e o card está marcado como
fechado — não viável, sem código pendente.
