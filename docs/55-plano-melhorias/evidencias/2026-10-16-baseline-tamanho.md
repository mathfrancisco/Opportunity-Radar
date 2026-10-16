# Baseline de tamanho antes da Frente E (16/10/2026)

Medição somente leitura, sem PII.

| Banco | Medido em (UTC) | `pg_database_size` | Oportunidades | Outras contagens |
| --- | --- | --- | --- | --- |
| Neon production `tiny-dust-53844381`, `neondb` | 2026-10-16 15:48 | 25 993 216 bytes (26 MB) | 100 | 225 raw items, 291 observações, 336 match_factor |
| Docker local `opportunity-radar-dev-postgres-1` | 2026-10-16 | 2 010 MB | 36 195 | 442 fontes |

Observação para a Frente A: a coleta local mais recente é de 2026-10-08 20:06 UTC
(`max(raw_item.fetched_at)`), e o `published_at` mais recente também é de 08/10.
Na data desta medição, nenhuma oportunidade local tem menos de 7 dias. Pela regra
R55-E1, a migração leva só o catálogo, a menos que o dono decida outra coisa.
