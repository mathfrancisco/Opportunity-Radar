# CARD F17-11 — Palavras-chave do perfil e fontes amplas

- **Status:** Backlog
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** F17-02
- **Bloqueia:** Nenhum
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §7

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
  "engenheiro de software") ao lado das áreas do F17-02.
- **Palavras derivadas:** cargos-alvo + as skills do perfil de maior nível, normalizadas e
  sem duplicata. `configuration["keywords"]` continua valendo como complemento explícito.
- **Rotação:** o limite de 10 termos por requisição (`CollectionRequest`) vira rotação —
  cada coleta usa o próximo bloco de até 10, e o estado da rotação fica no checkpoint da
  fonte.
- **Fontes amplas candidatas:** pesquisa em `docs/pesquisas/` de fontes com API pública e
  busca por termo, cada uma com a mesma revisão de termos do F17-10. A pesquisa é
  entregável; os coletores, sub-cards como no F17-10.
- **Ordem obrigatória:** nenhuma fonte ampla é habilitada antes do F17-02 estar ativo.

## Fora de escopo

- Buscar em sites que proíbem automação.
- Gerar palavras-chave com modelo de linguagem.

## Notas de implementação

- A mudança de perfil passa a mudar a busca na próxima coleta; registrar na execução quais
  termos foram usados, para explicar por que uma vaga entrou.
- O checkpoint atual guarda cursor; a rotação pode usar o mesmo registro com
  `checkpoint_type = "keyword_rotation"`.

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
