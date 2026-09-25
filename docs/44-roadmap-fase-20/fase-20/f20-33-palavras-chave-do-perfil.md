# CARD F20-33 — Palavras-chave do perfil

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-03, F20-40
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-11](../../38-roadmap-ia-e-busca/fase-17/f17-11-palavras-chave-do-perfil.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Não usar LLM para gerar as palavras-chave nesta fase.

## Resultado

As fontes que buscam por termo passam a buscar pelo que o perfil procura — cargos-alvo e
skills de maior peso —, em rotação, e novas fontes amplas entram só depois de pesquisadas
e com o filtro de área ativo.

## Contexto

A Remotive é a única fonte com busca por termo, e as palavras vêm fixas de
`configuration["keywords"]` (`worker.py:356`). Mudar o foco da busca exige editar a fonte.
O perfil não tem campo de cargos-alvo.

## Escopo

- **Perfil:** preferência `target_titles` (lista curta de cargos, ex.: "backend engineer",
  "engenheiro de software") ao lado das áreas do F20-03 (antigo F17-02).
- **Palavras derivadas:** cargos-alvo + as skills do perfil de maior nível, normalizadas e
  sem duplicata. `configuration["keywords"]` continua valendo como complemento explícito.
- **Rotação:** o limite de 10 termos por requisição (`CollectionRequest`) vira rotação —
  cada coleta usa o próximo bloco de até 10, e o estado da rotação fica no checkpoint da
  fonte.
- **Fontes amplas candidatas:** pesquisa em `docs/pesquisas/` de fontes com API pública e
  busca por termo, cada uma com a mesma revisão de termos do F20-28 a F20-32 (antigo F17-10). A pesquisa é
  entregável; os coletores, sub-cards como no F20-28 a F20-32 (antigo F17-10).
- **Ordem obrigatória:** nenhuma fonte ampla é habilitada antes do F20-03 (antigo F17-02) estar ativo.

## Fora de escopo

- Buscar em sites que proíbem automação.
- Gerar palavras-chave com modelo de linguagem.

## Notas de implementação

- A mudança de perfil passa a mudar a busca na próxima coleta; registrar na execução quais
  termos foram usados, para explicar por que uma vaga entrou.
- Cursor de paginação e rotação de termos são estados separados. Chave de execução
  inclui perfil, conjunto de termos e escopo. Só avançar rotação após confirmação
  durável da página/lote; falha/reinício não pula termos.
- Respeitar capacidades: ATS de board completo não recebe keyword_search.
  Cobrir cargos e sinônimos pt/en por rotação explícita, medindo sobreposição e
  vagas únicas por consulta. Nenhum termo fica permanentemente sem visita.

## Critérios de aceite

- [ ] O perfil declara cargos-alvo.
- [ ] A Remotive busca pelos termos derivados do perfil, em rotação, e a execução
      registra os termos usados.
- [ ] A pesquisa de fontes amplas está registrada.
- [ ] Nenhuma fonte ampla é habilitada antes do filtro de área.

## Verificação

- **CI:** teste da derivação de termos, da rotação entre execuções e do registro dos
  termos na execução; teste do coletor Remotive recebendo os termos derivados.

## Arquivos prováveis

- `src/opportunity_radar/profile/domain.py`, `profile/models.py`
- `src/opportunity_radar/worker.py`, `acquisition/scheduling.py`
- `apps/web/src/routes/ProfilePage.tsx`
- `docs/pesquisas/*-fontes-amplas.md` (novo)

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
docker compose -p f20-33 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-33 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-33 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
