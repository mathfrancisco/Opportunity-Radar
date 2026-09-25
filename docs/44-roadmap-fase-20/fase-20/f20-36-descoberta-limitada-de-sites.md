# CARD F20-36 — Descoberta limitada de sites e sitemaps

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** D — Varredura produtiva
- **Depende de:** F20-27, F20-35
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-02](../../40-roadmap-varredura-produtiva/fase-18/f18-02-descoberta-limitada-de-sites.md); [SPEC 39](../../39-spec-varredura-produtiva.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Dependências antigas de F17 foram fechadas por F20-01 a F20-03.

## Resultado

Empresas cuja página não revela ATS ganham pesquisa limitada de links/sitemaps, com proposta rastreável e custo controlado.

## Escopo

- Reutilizar assinaturas/propostas de F20-27 (antigo F17-09). Semear pela página de carreiras cadastrada e seguir apenas links pertinentes dentro da allowlist.
- Aplicar os limites de profundidade, respostas, tamanho descomprimido e URLs da SPEC; registrar parada por limite, erro, política ou site dinâmico.
- Deduplicar URL normalizada sem remover query identificadora; persistir origem, evidência e data da tentativa.
- Robots/termos, agente identificável, validação de DNS/destino e de cada redirect. Recusar rede privada e XML com entidades externas.
- Resultado negativo tem próxima revisão semanal/backoff. ATS externo vira proposta inerte; nenhuma navegação livre ou habilitação por IA.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [ ] Loops, sitemaps grandes e múltiplos redirects param dentro do orçamento.
- [ ] Nenhum destino privado ou fora da allowlist é acessado.
- [ ] Limite/erro não significa empresa sem vagas.
- [ ] Proposta existente é reutilizada com histórico da descoberta.

## Verificação

- **CI:** Servidor falso com sitemap/index/loop, URL com query, redirect privado, robots indisponível, XML inválido e orçamento esgotado.
- **Máquina de referência:** Medir empresas novas com endpoint encontrado e requisições por descoberta numa coorte fixa.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`acquisition/probing.py`, `proposals.py`, novo módulo de descoberta limitada, scripts/discover_sources.py, fixtures HTTP.

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
docker compose -p f20-36 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-36 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-36 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
