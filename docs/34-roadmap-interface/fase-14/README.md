# Cards da Fase 14 — cadastro e curadoria pela interface

Estes cards tiram do terminal o que hoje só existe lá: criar uma fonte, homologá-la,
registrar uma vaga avulsa, cadastrar uma empresa e vinculá-la a uma fonte.

A ordem preserva a dependência real de contrato: fonte e vaga usam API que já existe;
empresa e vínculo exigem endpoints novos.

| Ordem | Card | Depende de | Status |
| --- | --- | --- | --- |
| 1 | [F14-01 — cadastro de fonte](f14-01-cadastro-de-fonte.md) | Fase 13 | Concluído |
| 2 | [F14-02 — homologação e kill switch](f14-02-homologacao-de-fonte.md) | F14-01 | Concluído |
| 3 | [F14-03 — entrada manual de vaga](f14-03-entrada-manual-de-vaga.md) | F14-01 | Concluído |
| 4 | [F14-04 — cadastro de empresa](f14-04-cadastro-de-empresa.md) | Fase 13 | Concluído |
| 5 | [F14-05 — vínculo entre empresa e fonte](f14-05-vinculo-empresa-fonte.md) | F14-04 | Concluído |
| 6 | [F14-06 — teste ao vivo do collector](f14-06-teste-ao-vivo-do-collector.md) | F14-02 | Backlog |
| 7 | [F14-07 — correção do ATS alcança a proposta](f14-07-correcao-alcanca-a-proposta.md) | F14-05 | Backlog |

F14-04 pode seguir em paralelo com F14-01. F14-02, F14-03 e F14-05 entregaram o cadastro
pela tela.

F14-06 e F14-07 saíram da execução dos cinco primeiros. F14-06 é o que falta para o
Milestone M: sem ele, a evidência de uma fonte externa nova só é confirmada pelo terminal.
F14-07 fecha o limite registrado em F14-05 — corrigir o ATS depois de propor não chegava à
fonte proposta.

## Invariantes da fase

- a tela nunca habilita uma fonte externa sem evidência confirmada, data de revisão, termos
  revisados e collector testado;
- toda escrita concorrente envia a versão esperada e trata o conflito como conflito;
- vaga manual entra por `SourceRun` e `RawItem`, com procedência, e nunca direto em
  `Opportunity`;
- empresa criada pela tela passa pela mesma reconciliação do importador de pesquisa.
