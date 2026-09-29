# CARD F18-02 — Descoberta limitada de sites e sitemaps

- **Status:** Backlog
- **Fase:** 18 — Varredura produtiva
- **Depende de:** F17-09, F18-01
- **Bloqueia:** F18-03
- **Origem:** [SPEC 39](../../39-spec-varredura-produtiva.md), §5

## Resultado

Empresas cuja página não revela ATS ganham pesquisa limitada de links/sitemaps, com proposta rastreável e custo controlado.

## Escopo

- Reutilizar assinaturas/propostas de F17-09. Semear pela página de carreiras cadastrada e seguir apenas links pertinentes dentro da allowlist.
- Aplicar os limites de profundidade, respostas, tamanho descomprimido e URLs da SPEC; registrar parada por limite, erro, política ou site dinâmico.
- Deduplicar URL normalizada sem remover query identificadora; persistir origem, evidência e data da tentativa.
- Robots/termos, agente identificável, validação de DNS/destino e de cada redirect. Recusar rede privada e XML com entidades externas.
- Resultado negativo tem próxima revisão semanal/backoff. ATS externo vira proposta inerte; nenhuma navegação livre ou habilitação por IA.

## Fora de escopo

- Ampliar para serviços distribuídos, IA remota ou coleta autenticada.
- Executar testes, migrações ou coletas reais nesta revisão documental.

## Critérios de aceite

- [ ] Loops, sitemaps grandes e múltiplos redirects param dentro do orçamento.
- [ ] Nenhum destino privado ou fora da allowlist é acessado.
- [ ] Limite/erro não significa empresa sem vagas.
- [ ] Proposta existente é reutilizada com histórico da descoberta.

## Verificação

- **CI:** Servidor falso com sitemap/index/loop, URL com query, redirect privado, robots indisponível, XML inválido e orçamento esgotado.
- **Máquina de referência:** Medir empresas novas com endpoint encontrado e requisições por descoberta numa coorte fixa.
- Conforme AGENTS.md, validação local depende de pedido explícito.

## Arquivos prováveis

`acquisition/probing.py`, `proposals.py`, novo módulo de descoberta limitada, scripts/discover_sources.py, fixtures HTTP.
