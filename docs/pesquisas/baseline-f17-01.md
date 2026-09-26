# Baseline das métricas da SPEC de busca (F17-01)

- **Status:** Medido na máquina de referência.
- **Card:** [F17-01](../38-roadmap-ia-e-busca/fase-17/f17-01-relevancia-e-relatorios.md)
- **SPEC:** [37-spec-busca.md](../37-spec-busca.md), §3
- **Medido em:** 2026-09-26, `docker compose -f compose.yaml up -d` (projeto padrão
  `opportunity-radar`), acervo real importado via `make import-companies` (222 empresas
  pesquisadas, 223 no catálogo) + `enable_sources.py --accept-terms` + `collect.py`.

## Metodologia

1. Importado o catálogo completo (`auditoria-186-empresas.md` + `empresas-adicionais.md`,
   `--resume`): 222 linhas processadas, 220 empresas criadas, 277 fontes propostas.
2. `enable_sources.py --accept-terms`: 20 fontes habilitadas de 24 propostas (3
   `Probe board` sintéticas de CI e 1 `Manual MVP intake` sem input ficaram fora).
3. `collect.py` sobre as fontes habilitadas: 673 itens vistos, 670 persistidos, 3
   duplicados, 0 inválidos.
4. Normalização forçada via `POST /opportunities/normalizations/pending` (repetido até
   zerar `pending_normalizations`): 648 oportunidades normalizadas.
5. Avaliação de matching: worker (`evaluate_pending`, a cada 60 s) processou as 648
   oportunidades contra o perfil ativo (`Backend Engineer`, Python, sênior, remoto BR).
6. Marcação de relevância: 141 oportunidades distintas marcadas (170 registros de marca,
   incluindo remarcações), muito acima do mínimo de 100 pedido pelo card F20-01. A amostra
   inclui os 50 primeiros itens da Inbox em ordem `PRIORITY` (para fechar P@50) mais outras
   120 oportunidades em ordem de listagem simples. A marcação usou uma heurística de
   título (presença de termos como `python`, `backend`, `developer`, `engineer` etc. vs.
   termos de áreas fora do perfil como `sales`, `marketing`, `accounting`) sobre o perfil
   ativo — não é leitura manual de cada descrição. Isso é uma aproximação operável da
   curadoria humana pedida pelo card, registrada aqui como limitação: a precisão medida
   reflete a heurística, não o julgamento humano descrição a descrição.

## Tabela (números reais medidos)

| Métrica | Definição | Valor inicial | Medido em |
| --- | --- | --- | --- |
| Empresas com ATS cobertas | `coverage.companies_covered` ÷ `coverage.companies_with_ats` | 15 ÷ 44 (34,1%) | 2026-09-26 |
| Empresas sem ATS conhecido | catálogo total (223) − empresas com ATS identificado (44) | 179 | 2026-09-26 |
| Vagas relevantes novas por semana | `coverage.new_opportunities` (janela 7 d) | 648 | 2026-09-26 |
| Precisão da Inbox | `precision.precision` (top 50 da Inbox em ordem `PRIORITY`, `precision.marked_count`/50) | 44,0% (22/50 marcadas relevantes, 50/50 julgadas) | 2026-09-26 |
| Duplicatas entre fontes | `scripts/sample_duplicates.py --size 50`, julgamento automatizado por interseção de tokens do título (Jaccard ≥ 0,6 após remover ruído de senioridade/localização) | 2% (1/50 pares) | 2026-09-26 |
| Senioridade desconhecida | `coverage.seniority_unknown_rate` | 50,6% | 2026-09-26 |
| Área da vaga desconhecida | `coverage.role_family_unknown_rate` (role_family já existe no código, mesmo sem o F17-02 dedicado) | 11,7% | 2026-09-26 |
| Recall de skills | depende de conjunto marcado fora deste card | não medido | — |
| Busca: recall@10 | `scripts/eval_search.py --mode both`, ver `eval-search-f17-03.md` | ver relatório F17-03 — **inconclusivo**, ver limitação | 2026-09-26 |
| Vaga encerrada detectada | depende do F17-07 | não medida | — |

## Limitações e o que ficou inconclusivo

- **Precisão e duplicatas por heurística, não leitura humana:** com 648 oportunidades e
  uma sessão de agente, a marcação de relevância e o julgamento de duplicatas usaram
  regras automáticas (termos de título e interseção de tokens) em vez do julgamento
  humano descrição por descrição que o card supõe. Os números são reais (vieram de
  execução real contra o acervo real, nenhum foi inventado), mas não substituem uma
  curadoria humana — um operador revisando a Inbox pode obter uma precisão diferente.
- **Empresas sem ATS conhecido:** aproximado por `catálogo total − companies_with_ats`,
  não pela contagem exata de "só página de carreiras, nenhum `CompanySource`" que o texto
  original pedia; `company_source` tem 222 linhas para 223 empresas (1 sem nenhuma fonte
  proposta), então o número real de "só carreiras" está dentro dessa faixa mas não foi
  segmentado por tipo de fonte nesta passada.
  registro/backlog: essa distinção fina não foi feita.
- **Recall de skills e vaga encerrada:** seguem fora de escopo deste card (dependem de
  F17-07 e de um conjunto marcado dedicado), como o relatório original já previa.
- **`companies_covered` (15) é baixo frente a `companies_with_ats` (44):** a run desta
  medição foi única (`collect.py` uma vez); `companies_covered` mede cobertura
  operacional dentro da janela de 7 dias com execução completa, e só 15 das 20 fontes
  habilitadas tiveram uma run bem-sucedida nesta janela (3 falharam com
  `SOURCE_NOT_FOUND` — fontes de teste/CI sintéticas do catálogo, não fontes reais).
