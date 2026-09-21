# CARD F12-04 — Detecção de fonte pela UI da empresa

- **Status:** Backlog
- **Fase:** 12 — Escala e qualidade de fontes
- **Depende de:** F12-03 — descoberta de fontes com evidência
- **Bloqueia:** Descoberta assistida por operadores
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§19–22 e item 55 da §30

## Resultado

A tela de empresa oferece uma ação para detectar uma fonte, mostra a evidência obtida e
cria no máximo uma proposta desabilitada para a mesma descoberta.

## Contexto

A UI deve ter a mesma fronteira de segurança do script: detectar ATS ou endpoint acelera
a revisão, mas não equivale a termos aprovados, collector testado ou fonte habilitada.

## Escopo

- Adicionar ação de detectar fonte na tela de empresa.
- Exibir evidência, resultado e ausência de ATS detectável.
- Reutilizar a lógica de proposta idempotente do F12-03.
- Mostrar claramente que a proposta nasce desabilitada e aguarda revisão/homologação.

## Fora de escopo

- Revisar termos ou homologar collectors pela UI.
- Habilitar fonte automaticamente.
- Executar uma coleta a partir da proposta.
- Redesenhar a gestão completa de fontes.

## Notas de implementação

- A ação deve delegar ao mesmo serviço de descoberta do script, evitando regras
  divergentes entre terminal e interface.
- A resposta deve diferenciar proposta criada, proposta já existente e ATS não detectável.
- Não expor uma proposta como fonte executável nas métricas de cobertura.

## Critérios de aceite

- [ ] A ação mostra a evidência que sustenta o resultado.
- [ ] Ação bem-sucedida cria somente uma proposta desabilitada.
- [ ] Repetir a ação não duplica proposta.
- [ ] A UI informa quando não há ATS detectável.
- [ ] A ação nunca marca termos como revisados nem collector como homologado.
- [ ] A proposta não aparece como fonte habilitada ou executada.

## Verificação

- Teste de interface para proposta criada, proposta existente e ATS ausente.
- Teste de API/serviço confirma os campos do gate após a ação.
- Revisão manual confirma evidência visível e estado desabilitado.

## Arquivos prováveis

- `apps/web/src/routes/`
- `apps/web/src/lib/`
- `src/opportunity_radar/api/`
- `src/opportunity_radar/acquisition/`
- testes de API e interface correspondentes
