# F51-11 — protocolo de gold para classificação por descrição

> Atualização Terra: o gold legado de 39 casos continua somente diagnóstico. Rótulos `legacy`
> não contam como revisão humana nem completam a população; `GATED_RULES` continua vazio.

Este documento define como medir as regras `seniority-v4`, `work-mode-v7` e
`allowed-countries-v2` sem produzir rótulos automaticamente. `scripts/measure_content_classification.py`
é um leitor/medidor; não altera o banco nem ativa regras.

## O que existe hoje

O gold herdado de F50-01 contém 39 casos, sem `source_type` e sem estado explícito de
aplicabilidade. Ele continua legível para compatibilidade e pode ser usado para inspeção,
mas aparece como `legacy` e bloqueia o gate. A linha de base F50-01 registra que faltava
gold humano com 200 oportunidades, 50 por tipo de fonte; não tratamos o conjunto existente
como prova de precisão nem completamos seus rótulos.

## Formato dos próximos julgamentos humanos

Cada linha é uma oportunidade e um campo, com texto da descrição e tipo de fonte conhecido.
O revisor registra `judgment` como `applicable`, `inapplicable` ou `unknown`. Para
`applicable`, `valor_recomendado` contém o valor humano e `evidencia` aponta o trecho literal.
Para os outros estados, o valor esperado deve ficar nulo, com justificativa humana em
`evidencia`/anotação. `expected_rule` é opcional e permite atribuir uma omissão a uma regra
específica. Duplicatas de oportunidade/campo e estados contraditórios bloqueiam a leitura.

`unknown` é um estado inconclusivo, não é `false` nem “manter UNKNOWN”: continua visível,
mas não entra em precisão nem satisfaz suporte rotulado. `inapplicable` também não é uma
classe prevista: suas emissões são contadas à parte e ficam fora do denominador da regra. Campo sem
`source_type` fica no total sem atribuição e não contribui para suporte por fonte.

O gate de população exige pelo menos 200 oportunidades distintas, pelo menos 50 por cada
tipo de fonte, nenhum caso legado/`unknown`/inválido e tipo de fonte conhecido. `unknown`
continua fora da precisão, mas bloqueia aprovação do gold. Depois da população, cada regra
tem elegibilidade independente: suporte mínimo de 20 emissões e precisão mínima de 90%.
`--check-gate` exige selecionar explicitamente uma ou mais regras com `--candidate-rule`;
todas as selecionadas precisam passar. Sem seleção, o relatório é diagnóstico, não aprovação.
O relatório inclui TP/FP/FN e suporte
por regra. Uma omissão sem `expected_rule` fica em `<campo>:no_emission`; a atribuição
específica exige anotação humana, nunca inferência do script. Cobertura é calculada
separadamente e não substitui precisão.

## Execução e controle

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe scripts/measure_content_classification.py --gold <gold.json> --gold-text --check-gate --candidate-rule seniority:description_years_range
```

O comando termina com código 1 se o gate falhar. `GATED_RULES` permanece vazio e as flags
de classificação permanecem desligadas até que os rótulos sejam revisados por humanos e
uma decisão de aprovação seja registrada. Esta implementação não muda allowlist, regras,
versões persistidas ou dados. Reclassificação mutável, colisões, idempotência e eventos de
reavaliação continuam exigindo validação isolada em banco `_test`; não foram executados
nesta fatia.
