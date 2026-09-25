# CARD F20-40 — Preservação integral do perfil

- **Status:** Parcial — `794b519`; conferir o restante
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** D — Varredura produtiva
- **Depende de:** Nenhum
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-07](../../40-roadmap-varredura-produtiva/fase-18/f18-07-preservacao-do-perfil.md)

## Ajustes da Fase 20

- O commit `794b519` já preserva as famílias de cargo-alvo. Conferir cada critério abaixo contra o código e fazer só o que faltar.
- O perfil preservado alimenta o perfil mínimo enviado ao Groq (F20-15).

## Resultado

Editar uma preferência não elimina experiências, projetos, datas das skills ou outros campos do perfil ativo.

## Escopo

- Corrigir o round-trip de leitura/edição/escrita; api.ts hoje envia experiences/projects vazios e omite last_used_at.
- Copiar campos não editados da versão-base, com versão esperada. Preservar futuro target_role_families/target_titles.
- Publicação/ativação mantém controle de conflito; erro intermediário não ativa snapshot parcial. Permitir retomar versão publicada sem duplicação acidental.
- Manter histórico imutável, invalidar avaliações pela nova versão e explicar conflito na UI.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [ ] Alterar só país preserva todas as experiências/projetos e last_used_at.
- [ ] Duas edições concorrentes não perdem dados nem ativam snapshot parcial.
- [ ] Nova versão ativa gera reavaliação; antiga continua consultável.

## Verificação

- **CI:** Integração backend e contrato frontend com perfil completo; percurso no navegador em F20-47 a F20-49 (antigo F18-09).
- **Máquina de referência:** Sem dependência de GPU ou fontes externas.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`apps/web/src/features/profile/api.ts`, ProfilePage, API/profile service e testes do contrato.

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
docker compose -p f20-40 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-40 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-40 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
