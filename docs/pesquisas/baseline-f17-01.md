# Baseline das métricas da SPEC de busca (F17-01)

- **Status:** Pendente — a coletar na máquina de referência.
- **Card:** [F17-01](../38-roadmap-ia-e-busca/fase-17/f17-01-relevancia-e-relatorios.md)
- **SPEC:** [37-spec-busca.md](../37-spec-busca.md), §3

## Por que este relatório está vazio

Os números da tabela §3 da SPEC exigem o acervo real (vagas coletadas, empresas do
catálogo, marcações do operador). Este ambiente de implementação não tem esse acervo, e
preenchê-lo aqui seria inventar dado. O relatório é o entregável manual da fase — quem
roda a máquina de referência preenche esta tabela com os números reais e commita o
resultado.

## Como medir cada linha

1. Suba a API contra o banco da máquina de referência e rode as migrações
   (`alembic upgrade head`).
2. Marque relevância em algumas dezenas de vagas da Inbox (via `POST
   /opportunities/{id}/relevance`, pela tela) para que a precisão não fique `null`.
3. Rode:

   ```
   curl "$API_URL/search-metrics?window=7d"
   ```

   e leia `coverage` e `precision` do corpo da resposta.
4. Rode `python scripts/sample_duplicates.py --size 50` e julgue os 50 pares para a taxa
   de duplicatas.
5. Rode `python scripts/search_reference.py init` e preencha as 40 consultas com
   `python scripts/search_reference.py add --query "..." --opportunity-id <uuid>` para o
   conjunto que o F17-03 vai usar no recall@10 (essa métrica só existe depois do F17-03).
6. Para "empresas com ATS cobertas" e "empresas sem ATS conhecido", use
   `coverage.companies_covered` e `coverage.companies_with_ats` do mesmo endpoint, e a
   contagem de empresas com página de carreiras e nenhum `CompanySource` (consulta
   direta ao catálogo).

## Tabela (preencher com os números reais)

| Métrica | Definição | Valor inicial | Medido em |
| --- | --- | --- | --- |
| Empresas com ATS cobertas | `coverage.companies_covered` ÷ `coverage.companies_with_ats` | — | — |
| Empresas sem ATS conhecido | só página de carreiras ou backlog | — | — |
| Vagas relevantes novas por semana | `coverage.new_opportunities` nas áreas de interesse | — | — |
| Precisão da Inbox | `precision.precision` (`precision.marked_count` marcadas) | — | — |
| Duplicatas entre fontes | `scripts/sample_duplicates.py`, amostra julgada | — | — |
| Senioridade desconhecida | `coverage.seniority_unknown_rate` | — | — |
| Área da vaga desconhecida | depende do F17-02, ainda não existe | não existe | — |
| Recall de skills | depende de conjunto marcado, fora deste card | não medido | — |
| Busca: recall@10 | depende do F17-03 e de `scripts/search_reference.py` | não medido | — |
| Vaga encerrada detectada | depende do F17-07 | não medida | — |
