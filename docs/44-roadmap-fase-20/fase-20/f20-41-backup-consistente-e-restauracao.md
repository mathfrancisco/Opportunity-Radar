# CARD F20-41 — Backup consistente e restauração verificável

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** D — Varredura produtiva
- **Depende de:** Nenhum
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-08](../../40-roadmap-varredura-produtiva/fase-18/f18-08-backup-consistente-e-restauracao.md)

## Ajustes da Fase 20

- Incluir no backup e na prova de restauração as tabelas novas da IA: `ai_quota_usage`, registros de chamada (F20-19) e cache (F20-16).
- O backup nunca inclui o `.env` nem a `GROQ_API_KEY`.

## Resultado

Backup durante coleta ativa restaura o mesmo estado descrito no manifesto e preserva os dados duráveis do operador.

## Escopo

- Usar snapshot transacional compartilhado/exportado entre manifesto e pg_dump, mantendo-o válido durante dump; alternativa exige janela explícita sem escritores.
- Escrever dump/manifesto atomicamente; registrar hash, tamanho, revisão e versão do formato. Gate estrito rejeita manifesto ausente/incompatível ou checksum divergente.
- Modo somente legibilidade é explícito e não reporta backup verificado. Contagens são insuficientes: conferir amostras de conteúdo/relacionamentos.
- Incluir perfil, candidaturas, marcas, buscas salvas e decisões; atualizar inventário com cada migração. Dados de avaliação fora do banco têm pacote/manifesto próprio.
- Restore em banco descartável exige extensão/imagem compatível, incluindo pgvector quando existir. Documentar retomada e reconstrução de derivados.
- Definir no runbook periodicidade, local de cópia separado, idade máxima tolerada e tempo de recuperação medido; defaults propostos 24 h e 30 min são metas a confirmar.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [ ] Escrita concorrente não causa divergência artificial de contagens.
- [ ] Sem manifesto/hash válido o gate estrito falha.
- [ ] Restauração confere dados e relações, inclusive features já instaladas.
- [ ] Procedimento de recuperação tem evidência e limitações registradas.

## Verificação

- **CI:** Backup sob escritor controlado, corrupção/ausência de manifesto, restauração de banco populado e extensão quando aplicável.
- **Máquina de referência:** Restore medido em banco descartável; execução futura somente com autorização explícita.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`scripts/backup.py`, restore_check.py, platform/backup.py, pipeline.yml e docs/30-runbook.md.

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
docker compose -p f20-41 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-41 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-41 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
