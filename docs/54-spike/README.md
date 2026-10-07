# WP1 — spike de primitives da SPEC 54

## Decisão aprovada para WP3B

O produto adota somente `@radix-ui/react-dialog@1.2.0`, por meio de um wrapper
local em `apps/web/src/components/ui/`, para a gaveta de navegação móvel. Não
há menu, popover, combobox ou tabs no app que justifiquem outro primitive.

| Candidato | Delta JS gzip sobre 149,01 kB | Resultado |
| --- | ---: | --- |
| Radix Dialog 1.2.0 | +12,61 kB / **+8,54%** | aprovado; dentro do orçamento de +10% |
| Base UI | +13,35% | reprovado; Shift+Tab falhou |
| React Aria | +16,73% | fora do orçamento |
| MUI | +24,13% | fora do orçamento |

Restam aproximadamente 2,2 kB antes do limite de +10%, mas esse espaço não
autoriza adicionar outro primitive Radix sem nova medição comparável. Caso o
total futuro exceda +10%, o Dialog da gaveta deve ser carregado sob demanda.

## Limites da decisão

Esta decisão seleciona apenas o Dialog e não aprova uma distribuição shadcn,
outros primitives, rotas, estilos globais ou a SPEC 54 como um todo. A
evidência de bundle é específica à medição acima; mudanças posteriores exigem
nova validação proporcional.
