# Baseline local da SPEC 54

Data: 2026-10-07. Baseline no checkout principal; SHA medido: `b6d25ae96701398fa91e9214fe2a07985957cd19`. Esse commit avançou durante a execução; o frontend empacotado não contém o spike que existe em uma worktree separada.

## Decisão de ordem

A orientação do produto inverteu a ordem inicialmente prevista: avançar F54
localmente antes de F53. A etapa atual é preparação, baseline e spike. A migração
visual das telas aguarda aceite explícito dos protótipos Inbox, Detalhe da vaga e
Pipeline conforme SPEC §7. F53, Clerk real e operações cloud continuam pendentes;
este baseline não acessa banco operacional, Docker, Vite nem APIs externas.

## Evidência local

No checkout principal, `npm run check` terminou com exit 0: ESLint, TypeScript,
42 arquivos de teste e 292 testes passaram, e o build Vite concluiu. A saída
literal está em `checks-restored.log`; `checks.log` preserva a tentativa anterior
que falhou em `TS2688` antes da restauração das dependências.
O CI mais recente da `main` também concluiu com sucesso em [run 37628152505](https://github.com/mathfrancisco/Opportunity-Radar/actions/runs/37628152505); isto é evidência apenas do SHA atual da main, sem validar F54 cloud nem F53.

O harness usou fixtures sintéticas e servidor estático loopback para 11 caminhos
(dez rotas e wildcard) em cinco larguras (320, 360, 768, 1280 e 1440 px): 55
capturas, zero GETs API sem fixture, zero page errors, zero console errors, zero
respostas fixture não-200 e nenhum overflow horizontal. `artifacts/result.json`
preserva request paths/timestamps, textos DOM e timings. Inbox, detalhe da vaga
e Pipeline exibem a oportunidade sintética; os cinco captures de Pipeline têm
uma candidatura em andamento e zero encerradas. Overview informa uma candidatura
ativa em Entrevista e uma fonte habilitada, coerentes com as outras telas.

`component-inventory.tsv` lista os 48 exports nomeados em `src/components`,
separa o helper de teste e inclui `AnalysisPanel` fora dessa pasta.
`route-map.tsv` cobre as dez rotas e wildcard, imports, hooks, GETs, mutações e
testes focados; Company Detail inclui `useInbox` e seu polling de 15 s.

`artifacts/result.json` registra antes das capturas a identidade do build:
commit, SHA-256 do index e SHA-256 dos três arquivos servidos em `dist/assets`.
`artifacts/baseline-metrics.json` compara commit, index e conjunto completo de
assets com o `dist` atual antes de iniciar os polls e registra essa comparação
como verificada. O relatório preserva os timings sem tratá-los como CWV, e
registra Node `v24.12.0`, npm `11.6.2`, Chromium `153.0.8010.12`, Windows
`win32-x64` e bytes/gzip/SHA dos assets JS, CSS, fontes e index.

Na observação sequencial de 32 s, Inbox registrou GETs em 0,206 s, 15,219 s e
30,235 s; Detalhe em 0,164 s, 15,211 s e 30,230 s. Os timestamps UTC estão no
JSON. Isto demonstra somente o polling do browser com fixtures, sem medir CWV,
Neon ou banco.

`artifacts/frontend-e84be68.zip` contém o `dist` local após check/build; o SHA-256
e o SHA da identidade do index estão em `artifacts/frontend-e84be68.sha256`. O
arquivo ZIP está read-only. O manifesto registra o SHA de checkout efetivamente
medido (`b6d25ae`); o artefato prepara rollback local e não prova deploy ou
rollback cloud.

## Pendências e critérios AC54

| Gate | Estado | Evidência faltante |
| --- | --- | --- |
| F53 hospedagem | adiada | preview Cloudflare/OCI, URL e smoke operacional |
| Clerk | não iniciado | instância real, domínio/DNS, fluxo e autorização de API |
| testes isolados | pendente | execução documentada contra banco `_test` |
| backup/restore | não iniciado | dump, checksum e restore isolado observado |
| cutover/rollback cloud | pendente | ensaio autorizado com retorno provado |
| Neon idle | não provado | telemetria/console observado |
| aceite visual | pendente | aprovação explícita dos protótipos em 1440, 768 e 360 px |

AC54-01 e AC54-08 aguardam F53. AC54-02 aguarda aceite visual. A parte cloud de
AC54-10 aguarda preview, smoke e rollback cloud. Nenhum AC54 é declarado
concluído por esta evidência local. Veja `checkpoint.md` para estado WP0–WP7,
worktrees e preservação.

Shadcn permanece preliminar: faltam spike com versões fixadas do projeto e
verificação de wrappers/acessibilidade. Referências: https://ui.shadcn.com/docs/installation/vite
e https://ui.shadcn.com/docs/react-19.
