# CARD F20-27 — Descoberta de ATS

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-09](../../38-roadmap-ia-e-busca/fase-17/f17-09-descoberta-de-ats.md)

## Ajustes da Fase 20

- Sem mudança de escopo. O relatório deste card define a ordem de F20-28 a F20-32.

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
- Relatório: quantas páginas revelaram ATS, por tipo — é o que reordena o F20-28 a F20-32 (antigo F17-10).

## Fora de escopo

- Navegador headless para páginas renderizadas por JavaScript (SPEC §16).
- Habilitar fonte: a descoberta produz evidência; a proposta passa pela sonda e pela
  homologação.

## Continuidade

Este card mantém a descoberta de ATS em uma página. F20-36 (antigo F18-02) amplia para links e
sitemaps com limites, aproveitando as mesmas assinaturas e propostas. Resultado
negativo não significa empresa sem vagas; guardar motivo e próxima pesquisa.

## Notas de implementação

- A descoberta é pesquisa, não coleta: não cria `SourceRun` nem `RawItem`.
- Página que redireciona para domínio de ATS também conta: registrar a URL final.
- A chave do board é extraída pelos mesmos padrões do F20-03 (antigo F17-04).

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

## Não fazer

- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não habilitar fonte sem passar pelo gate de homologação.
- Não fazer chamada real a boards, Groq ou Tavily no CI; usar `httpx.MockTransport` ou os servidores falsos de `tests/e2e/`.
- Não adicionar dependência nova sem registrar o motivo no PR.
- Não usar LLM neste card, salvo quando a seção "Ajustes da Fase 20" disser o contrário.

## Como trabalhar este card

1. Ler "Ajustes da Fase 20" primeiro: eles prevalecem sobre o texto herdado.
2. Ler "Arquivos prováveis" e confirmar cada caminho com `ls`/`grep` antes de editar; caminho inexistente vira nota no PR.
3. Escrever primeiro os testes dos critérios de aceite, depois o código.
4. IDs antigos no texto aparecem como `F20-xx (antigo F1x-yy)`; a tabela completa está no README da Fase 20.
5. O que depende do acervo real ("Máquina de referência") é medido fora do CI e colado no PR.

## Comando de verificação

```bash
docker compose -p f20-27 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-27 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-27 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
