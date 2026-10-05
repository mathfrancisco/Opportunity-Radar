# Preparação: expansão de catálogo de empresas e fontes

## Escopo e estado

Preparação documental apenas. Nenhuma empresa foi importada, nenhuma fonte foi criada,
sondada ou ativada e nenhum endpoint operacional foi chamado. A lista abaixo é um
conjunto de candidatos para deduplicação contra o catálogo recuperado e revisão posterior;
não afirma que a empresa esteja ausente, que tenha vagas abertas, nem que aceite pessoas
no Brasil. A evidência documental preexistente foi coletada em setembro de 2026 e precisa
ser revalidada antes de uso operacional.

## Candidatos prioritários

Todos os tipos de ATS listados abaixo correspondem a coletores presentes no repositório
(Ashby, Greenhouse ou Lever). “ATS identificado” indica evidência de plataforma, não prova
de endpoint permissível ou coletor homologado. O importador mantém fontes desabilitadas e
sem revisão de termos; sondagem e ativação são etapas separadas.

| Empresa | Tipo identificado | Página oficial de carreiras | Evidência / ressalva |
| --- | --- | --- | --- |
| Supabase | Ashby, JSON documentado | [Carreiras](https://supabase.com/careers), [board API](https://api.ashbyhq.com/posting-api/job-board/supabase) | Pesquisa anterior registrou JSON público; revalidar no fluxo permitido. |
| RevenueCat | Ashby, JSON documentado | [Carreiras](https://www.revenuecat.com/careers/), [board API](https://api.ashbyhq.com/posting-api/job-board/revenuecat) | Pesquisa anterior registrou JSON público. |
| Render | Ashby, JSON documentado | [Carreiras](https://render.com/careers), [board API](https://api.ashbyhq.com/posting-api/job-board/render) | Pesquisa anterior; vagas observadas eram majoritariamente EUA/Canadá. |
| WorkOS | Ashby, JSON documentado | [Carreiras](https://workos.com/careers), [board API](https://api.ashbyhq.com/posting-api/job-board/workos) | Pesquisa anterior registrou JSON público. |
| Spotify | Lever, JSON documentado | [Carreiras](https://www.lifeatspotify.com/jobs), [board API](https://api.lever.co/v0/postings/spotify?mode=json) | Pesquisa anterior registrou JSON público; verificar região e termos atuais. |
| CI&T | Lever | [Carreiras](https://ciandt.com/us/en-us/careers), [board](https://jobs.lever.co/ciandt) | Pesquisa anterior viu anúncios Brasil/home office; confirmar vagas atuais. |
| Nubank | Ashby | [Carreiras](https://international.nubank.com.br/careers/), [board](https://jobs.ashbyhq.com/nubank) | Board identificado; confirmar elegibilidade em cada anúncio. |
| Clerk | Ashby | [Carreiras](https://clerk.com/careers), [board](https://jobs.ashbyhq.com/Clerk) | Board identificado; endpoint ainda requer homologação. |
| Firecrawl | Ashby | [Carreiras](https://www.firecrawl.dev/careers), [board](https://jobs.ashbyhq.com/firecrawl) | Pesquisa anterior observou funções de engenharia e algumas referências a Americas; não presumir Brasil. |
| Browserbase | Ashby | [Carreiras](https://www.browserbase.com/careers), [board](https://jobs.ashbyhq.com/browserbase) | Board identificado; endpoint ainda requer homologação. |
| Inngest | Ashby | [Carreiras](https://www.inngest.com/careers), [board](https://jobs.ashbyhq.com/inngest) | Board identificado; endpoint ainda requer homologação. |
| Trigger.dev | Ashby | [Carreiras](https://trigger.dev/careers), [board](https://jobs.ashbyhq.com/triggerdev) | Board identificado; endpoint ainda requer homologação. |
| Buildkite | Greenhouse | [Carreiras](https://buildkite.com/careers) | ATS identificado em pesquisa anterior; obter board oficial na redescoberta. |
| Cartesia | Ashby | [Carreiras](https://cartesia.ai/careers), [board](https://jobs.ashbyhq.com/cartesia) | ATS identificado em pesquisa anterior. |
| Deepgram | Ashby | [Carreiras](https://deepgram.com/careers) | ATS identificado em pesquisa anterior; obter board oficial na redescoberta. |
| GitBook | Ashby | [Carreiras](https://www.gitbook.com/careers) | ATS identificado em pesquisa anterior; obter board oficial na redescoberta. |
| Grafana Labs | Greenhouse | [Carreiras](https://grafana.com/careers/) | ATS identificado em pesquisa anterior; obter board oficial na redescoberta. |
| Langfuse | Ashby | [Carreiras](https://langfuse.com/careers) | Revisar identidade/relacionamento corporativo com ClickHouse antes de importar. |
| LiveKit | Ashby | [Carreiras](https://livekit.io/careers) | ATS identificado em pesquisa anterior; obter board oficial na redescoberta. |
| Mistral AI | Ashby | [Carreiras](https://mistral.ai/careers) | ATS identificado em pesquisa anterior; verificar locais elegíveis. |
| n8n | Ashby | [Carreiras](https://n8n.io/careers/), [board](https://jobs.ashbyhq.com/n8n) | Pesquisa anterior descreveu Europa/Reino Unido e às vezes EUA; Brasil não presumido. |
| Notion | Ashby | [Carreiras](https://www.notion.com/careers) | ATS identificado em pesquisa anterior; obter board oficial na redescoberta. |
| Replit | Ashby | [Carreiras](https://replit.com/careers) | ATS identificado em pesquisa anterior; verificar locais elegíveis. |
| Qonto | Lever | [Carreiras](https://qonto.com/en/careers) | ATS identificado em pesquisa anterior; verificar países/localidades por vaga. |

As pesquisas anteriores estão registradas em [auditoria das 186 empresas](pesquisas/auditoria-186-empresas.md)
e [empresas adicionais](pesquisas/empresas-adicionais.md). A checagem web deste preparo
confirmou páginas públicas de vaga em Ashby para [Supabase](https://jobs.ashbyhq.com/supabase/99a80436-89ec-412b-b782-1dd462bd16dc),
[Linear](https://jobs.ashbyhq.com/linear/2ef60eea-7cff-45c2-abf2-eaedc4ea89bd) e
[Connectly](https://jobs.ashbyhq.com/connectly/d6f5da3c-4937-467f-bcbd-927bce07aa20).
Linear não entrou na lista operacional candidata porque a vaga verificada restringe a
localidade à América do Norte; Connectly é um candidato adicional de validação humana
(vaga encontrada marcada Remote/Brazil), mas ainda precisa entrar no catálogo de pesquisa
com a URL canônica de carreiras e passar pelas mesmas portas.

## Portas e sequência segura para a etapa operacional

1. Comparar nomes normalizados, aliases, domínios e fontes do banco recuperado com esta
   lista; revisar aliases de empresas relacionadas manualmente, sem fusão automática.
2. Adicionar apenas ausentes à pesquisa rastreável, usando `scripts/import_research_catalog.py`
   com `--dry-run` primeiro. O importador reconhece boards Ashby, Greenhouse e Lever e
   valida identificadores com os próprios coletores; as definições novas ficam desabilitadas.
3. Rodar redescoberta ATS apenas após confirmação do operador e fora da recuperação do DB;
   o código `scripts/discover_ats.py` limita a descoberta a páginas de carreiras confirmadas,
   aplica robots e serialização por host, e não é coleta de vagas.
4. Revisar termos de uso e host para cada origem. A lista bloqueada do código inclui Gupy,
   Wellfound, páginas de vagas do YC/Work at a Startup, Careerflow, Crossover, Braintrust
   e Landing.jobs. Não contornar bloqueios via domínio alternativo, agregador ou ATS.
5. Fazer probe de uma fonte por vez com `scripts/enable_sources.py --probe-only` após a
   revisão autorizada. Só prosseguir com endpoint acessível, formato esperado e prova de
   termos; habilitar exige `--accept-terms` e passa por probe antes de ativação. Manter
   `--dry-run` para a prévia e não ligar a fonte por mera descoberta ATS.
6. Após ativação autorizada, acompanhar run, raw items, normalizações, avaliações e
   métricas de recência/duplicatas. Respeitar rate limit e schedule; não inferir cobertura
   Brasil da simples existência de anúncios remotos globais.

## Limites verificados no código

- A registry possui coletores específicos; pesquisa não cria suporte para um ATS novo.
  Workday, Teamtailor, Workable e Factorial não devem entrar nesta lista de ativação até
  haver collector compatível e termos aprovados.
- `enable_sources.py` só admite os tipos de probe atualmente pesquisados e mantém a fonte
  desabilitada quando o probe falha. A opção de aceite de termos é uma confirmação do
  operador, não uma revisão automática.
- Os cartões F48-19 revisam novos termos/plataformas; revisão documental não autoriza
  scrape ou ativação. Gupy continua explicitamente proibida.
