# CARD F17-09 — Descoberta de ATS nas páginas de carreiras

- **Status:** Backlog
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** F17-04
- **Bloqueia:** F17-10
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §5

## Resultado

Para as empresas que só têm página de carreiras, o radar descobre o ATS por trás dela
quando a página o revela, e registra a descoberta como evidência para virar proposta de
fonte.

## Contexto

115 empresas do catálogo têm página de carreiras confirmada e nenhum ATS conhecido; outras
52 estão em backlog. Muitas dessas páginas são uma casca em volta de um board Ashby,
Greenhouse, Lever, Gupy ou Teamtailor, embutido por link, iframe ou script.

## Escopo

- Comando `make discover-ats` (e job opcional de baixa frequência, desligado por padrão):
  para cada empresa com página de carreiras e sem ATS, faz **uma** requisição GET à página
  registrada.
- **Assinaturas** por ATS no HTML (links, `iframe src`, `script src`): `jobs.ashbyhq.com`,
  `boards.greenhouse.io`/`job-boards.greenhouse.io`, `jobs.lever.co`, `*.gupy.io`,
  `*.teamtailor.com`, `apply.workable.com`, `*.myworkdayjobs.com`, `*.factorialhr.com`.
- **Resultado** vira `CompanySource` com `verification_method = "discovery"`,
  `verification_status = "ats_identified"`, a URL encontrada e o trecho do HTML como
  evidência — o mesmo formato da F14-05, com revisão registrada.
- **Tentativas** em `company_radar.discovery_attempt` (empresa, URL, status HTTP, ATS
  encontrado, data), para não repetir antes do intervalo configurado (padrão 30 dias).
- **Boas maneiras:** respeita `robots.txt` (`urllib.robotparser`), `User-Agent` que
  identifica o radar, uma requisição por segundo no total, timeout curto, nunca segue
  links para dentro do site.
- Relatório: quantas páginas revelaram ATS, por tipo — é o que reordena o F17-10.

## Fora de escopo

- Navegador headless para páginas renderizadas por JavaScript (SPEC §16).
- Habilitar fonte: a descoberta produz evidência; a proposta passa pela sonda e pela
  homologação.

## Notas de implementação

- A descoberta é pesquisa, não coleta: não cria `SourceRun` nem `RawItem`.
- Página que redireciona para domínio de ATS também conta: registrar a URL final.
- A chave do board é extraída pelos mesmos padrões do F17-04.

## Critérios de aceite

- [ ] Uma execução percorre as empresas elegíveis com uma requisição cada, respeitando
      `robots.txt` e o ritmo.
- [ ] ATS encontrado vira `CompanySource` com evidência e método `discovery`.
- [ ] Tentativas ficam registradas e não se repetem antes do intervalo.
- [ ] O relatório por tipo de ATS está em `docs/pesquisas/`.

## Verificação

- **CI:** testes do detector de assinaturas com páginas de exemplo de cada ATS (HTML fixo)
  e páginas sem ATS; teste do respeito a `robots.txt` com servidor falso; teste do
  intervalo entre tentativas.
- **Máquina de referência:** execução real sobre o catálogo, com o relatório anexado.

## Arquivos prováveis

- `src/opportunity_radar/companies/discovery.py` (novo)
- `scripts/discover_ats.py` (novo), `Makefile`
- `migrations/versions/*_discovery_attempt.py`
- `tests/backend/companies/`
