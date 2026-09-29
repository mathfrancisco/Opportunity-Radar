# CARD F18-07 — Preservação integral do perfil

- **Status:** Done — `794b519`; conferido em [F20-40](../../../44-roadmap-fase-20/fase-20/f20-40-preservacao-do-perfil.md)
- **Fase:** 18 — Varredura produtiva
- **Depende de:** Nenhum
- **Bloqueia:** F16-07, F17-02, F17-11, F18-09
- **Origem:** [SPEC 39](../../39-spec-varredura-produtiva.md), §10

## Resultado

Editar uma preferência não elimina experiências, projetos, datas das skills ou outros campos do perfil ativo.

## Escopo

- Corrigir o round-trip de leitura/edição/escrita; api.ts hoje envia experiences/projects vazios e omite last_used_at.
- Copiar campos não editados da versão-base, com versão esperada. Preservar futuro target_role_families/target_titles.
- Publicação/ativação mantém controle de conflito; erro intermediário não ativa snapshot parcial. Permitir retomar versão publicada sem duplicação acidental.
- Manter histórico imutável, invalidar avaliações pela nova versão e explicar conflito na UI.

## Fora de escopo

- Ampliar para serviços distribuídos, IA remota ou coleta autenticada.
- Executar testes, migrações ou coletas reais nesta revisão documental.

## Critérios de aceite

- [ ] Alterar só país preserva todas as experiências/projetos e last_used_at.
- [ ] Duas edições concorrentes não perdem dados nem ativam snapshot parcial.
- [ ] Nova versão ativa gera reavaliação; antiga continua consultável.

## Verificação

- **CI:** Integração backend e contrato frontend com perfil completo; percurso no navegador em F18-09.
- **Máquina de referência:** Sem dependência de GPU ou fontes externas.
- Conforme AGENTS.md, validação local depende de pedido explícito.

## Arquivos prováveis

`apps/web/src/features/profile/api.ts`, ProfilePage, API/profile service e testes do contrato.
