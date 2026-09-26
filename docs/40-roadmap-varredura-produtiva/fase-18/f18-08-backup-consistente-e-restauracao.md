# CARD F18-08 — Backup consistente e restauração verificável

- **Status:** Parcial — código e testes em [F20-41](../../../44-roadmap-fase-20/fase-20/f20-41-backup-consistente-e-restauracao.md); falta o round-trip real contra Postgres e a medição de RTO/RPO na máquina de referência
- **Fase:** 18 — Varredura produtiva
- **Depende de:** Nenhum
- **Bloqueia:** F18-09; migrações de dados da Fase 18
- **Origem:** [SPEC 39](../../39-spec-varredura-produtiva.md), §10

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

- Ampliar para serviços distribuídos, IA remota ou coleta autenticada.
- Executar testes, migrações ou coletas reais nesta revisão documental.

## Critérios de aceite

- [ ] Escrita concorrente não causa divergência artificial de contagens.
- [ ] Sem manifesto/hash válido o gate estrito falha.
- [ ] Restauração confere dados e relações, inclusive features já instaladas.
- [ ] Procedimento de recuperação tem evidência e limitações registradas.

## Verificação

- **CI:** Backup sob escritor controlado, corrupção/ausência de manifesto, restauração de banco populado e extensão quando aplicável.
- **Máquina de referência:** Restore medido em banco descartável; execução futura somente com autorização explícita.
- Conforme AGENTS.md, validação local depende de pedido explícito.

## Arquivos prováveis

`scripts/backup.py`, restore_check.py, platform/backup.py, pipeline.yml e docs/30-runbook.md.
