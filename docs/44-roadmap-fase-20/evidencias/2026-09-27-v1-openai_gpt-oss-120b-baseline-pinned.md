# Avaliação da análise — v1 × openai/gpt-oss-120b (baseline-pinned)

Rodada em 2026-09-27T14:36:24.802683+00:00, 50 casos, conjunto `1afa75cd3102`. Provedor groq, cadeia openai/gpt-oss-120b.

Decisão pelo conjunto reservado; `não comparável` é critério que o baseline não media e exige o gabarito, não uma melhora.

| Critério | Reservado | Ajuste | Todos | Baseline (reservado) | Comparação |
| --- | ---: | ---: | ---: | ---: | --- |
| completed_rate | 1.000 | 1.000 | 1.000 | — | — |
| fidelity | — | — | — | — | — |
| grounded | — | — | — | — | — |
| coverage | 0.000 | 0.000 | 0.000 | — | — |
| inventions | 0.000 | 0.000 | 0.000 | — | — |
| portuguese | 0.123 | 0.112 | 0.113 | — | — |
| prompt_tokens | 890 | 1046 | 1031 | — | — |
| output_tokens | 451 | 461 | 460 | — | — |
| total_ms | 1663 | 1730 | 1723 | — | — |

Rubrica humana: aderência ao veredito (0/1) e sustentação — se cada trecho citado sustenta a afirmação, com atenção a negação e requisito opcional (0/1).

| Caso | Split | Status | Fidelidade | Ancorado | Cobertura | Invenções | Opcionais | Português | Tokens (entrada/saída) | ms | Aderência | Sustentação |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | :---: |
| 01-fora_de_area-27-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.125 | 907/442 | 1647 |  |  |
| 02-fora_de_area-28-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.086 | 960/460 | 1613 |  |  |
| 03-fora_de_area-29-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.138 | 1201/545 | 1531 |  |  |
| 04-fora_de_area-30-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.100 | 907/437 | 1453 |  |  |
| 06-fora_de_area-31-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.056 | 1023/481 | 1828 |  |  |
| 08-fora_de_area-32-review_required | reserved | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.238 | 800/504 | 1446 |  |  |
| 09-fullstack-07-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.103 | 1140/466 | 1385 |  |  |
| 10-fullstack-18-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.077 | 1210/480 | 1412 |  |  |
| 11-fullstack-37-review_required | reserved | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.060 | 864/419 | 1801 |  |  |
| 12-ai-11-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.098 | 1087/450 | 1494 |  |  |
| 13-fora_de_area-01-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.145 | 967/445 | 1342 |  |  |
| 14-fora_de_area-02-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.100 | 960/429 | 1903 |  |  |
| 15-fora_de_area-05-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.070 | 965/420 | 1372 |  |  |
| 16-fora_de_area-06-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.139 | 961/484 | 3613 |  |  |
| 32-ineligible-ineligible-01 | reserved | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.085 | 966/438 | 1890 |  |  |
| 33-ineligible-ineligible-02 | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.068 | 810/462 | 1512 |  |  |
| 34-ineligible-ineligible-03 | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.116 | 1027/478 | 1436 |  |  |
| 35-ineligible-ineligible-04 | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.105 | 1090/420 | 1435 |  |  |
| 36-ineligible-ineligible-05 | reserved | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.145 | 912/440 | 1469 |  |  |
| 37-ineligible-ineligible-06 | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.129 | 910/492 | 1511 |  |  |
| 38-ineligible-ineligible-07 | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.131 | 911/553 | 1966 |  |  |
| 39-ineligible-ineligible-08 | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.173 | 912/528 | 2333 |  |  |
| 40-ineligible-ineligible-09 | reserved | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.085 | 910/454 | 1710 |  |  |
| 41-ineligible-ineligible-10 | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.123 | 912/628 | 2362 |  |  |
| 42-java-01-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.078 | 1085/409 | 1309 |  |  |
| 43-java-02-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.103 | 1326/419 | 1548 |  |  |
| 44-java-03-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.064 | 1123/476 | 1726 |  |  |
| 45-java-04-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.118 | 1126/453 | 1705 |  |  |
| 46-java-05-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.107 | 1193/393 | 1202 |  |  |
| 47-java-06-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.065 | 1555/455 | 1821 |  |  |
| 48-java-07-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.058 | 1006/451 | 1580 |  |  |
| 49-java-08-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.195 | 974/388 | 1644 |  |  |
| 50-java-09-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.143 | 965/455 | 2580 |  |  |
| 51-java-10-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.127 | 1244/506 | 2107 |  |  |
| 52-fullstack-01-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.121 | 783/441 | 1883 |  |  |
| 53-fullstack-02-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.180 | 1165/444 | 1357 |  |  |
| 54-fullstack-03-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.119 | 1246/615 | 1745 |  |  |
| 55-fullstack-04-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.100 | 1250/454 | 2384 |  |  |
| 56-fullstack-05-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.150 | 1045/557 | 3070 |  |  |
| 57-fullstack-06-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.156 | 1105/377 | 1179 |  |  |
| 58-fullstack-07-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.143 | 958/416 | 1733 |  |  |
| 59-ai-01-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.127 | 1075/486 | 1580 |  |  |
| 60-ai-02-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.078 | 839/392 | 1214 |  |  |
| 61-ai-03-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.085 | 835/404 | 1999 |  |  |
| 62-ai-04-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.056 | 840/384 | 1283 |  |  |
| 63-ai-05-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.105 | 782/437 | 1809 |  |  |
| 64-ai-06-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.100 | 1354/495 | 1544 |  |  |
| 65-ai-07-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.122 | 1088/414 | 1220 |  |  |
| 66-ai-08-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.118 | 1138/466 | 1917 |  |  |
| 67-ai-09-review_required | tuning | AI_COMPLETED | — | — | 0.000 | 0 | 0 | 0.162 | 1129/462 | 1551 |  |  |
