# Cards da Fase 17 — Busca de vagas: cobertura e precisão

Estes cards executam a [SPEC de busca](../../37-spec-busca.md). A ordem é: medir, ganhar
precisão e só então aumentar o volume — porque cada fonte nova sem filtro de área enche a
Inbox de vagas que não servem.

| Ordem | Card | Depende de | Status |
| --- | --- | --- | --- |
| 1 | [F17-01 — relevância e relatórios](f17-01-relevancia-e-relatorios.md) | Nenhum | Em revisão — baseline pendente |
| 2 | [F17-02 — área da vaga](f17-02-area-da-vaga.md) | F17-01, F18-07 | Backlog |
| 3 | [F17-03 — busca full-text](f17-03-busca-full-text.md) | F17-01, F17-02 | Backlog |
| 4 | [F17-04 — importador propõe todo ATS](f17-04-importador-propoe-todo-ats.md) | Nenhum (habilitação em massa espera F17-02 e F17-07) | Em revisão |
| 5 | [F17-05 — fila de homologação](f17-05-fila-de-homologacao.md) | F17-04, F17-02, F17-07 | Backlog |
| 6 | [F17-06 — normalização mais precisa](f17-06-normalizacao-mais-precisa.md) | F17-01 | Backlog |
| 7 | [F17-07 — coleta completa e encerradas](f17-07-coleta-completa-e-encerradas.md) | Nenhum | Em revisão |
| 8 | [F17-08 — candidato a duplicata](f17-08-candidato-a-duplicata.md) | F17-01 (sinal vetorial após F16-09) | Backlog |
| 9 | [F17-09 — descoberta de ATS](f17-09-descoberta-de-ats.md) | F17-04 | Backlog |
| 10 | [F17-10 — coletores novos](f17-10-coletores-novos.md) | F17-09, F17-02, F17-06, F17-07 | Backlog |
| 11 | [F17-11 — palavras-chave do perfil](f17-11-palavras-chave-do-perfil.md) | F17-02, F18-07 | Backlog |
| 12 | [F17-12 — buscas salvas](f17-12-buscas-salvas.md) | F17-03 | Backlog |
| 13 | [F17-13 — relevância aprendida](f17-13-relevancia-aprendida.md) | F17-01, F16-09 | Backlog experimental; após Milestone P |

F17-01 a F17-07 fecham o Milestone P. Antecipar F17-07 em paralelo com F17-01;
numeração não impõe sequência. F16-10 e F17-13 são opcionais após esse marco.
A expansão produtiva continua na [Fase 18](../../40-roadmap-varredura-produtiva/README.md).

## Invariantes da fase

- nenhuma fonte é habilitada sem o gate: evidência confirmada por sonda, termos revisados,
  collector testado;
- evidência antes de inferência: toda classificação guarda o que a decidiu;
- classificar nunca é apagar: vaga fora do filtro continua no acervo e encontrável;
- toda vaga entra por `SourceRun` e `RawItem`, com procedência;
- nada junta duas oportunidades sem regra exata ou confirmação humana;
- toda regra nova é versionada e medida antes e depois.

## Verificação na fase

Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`. O
que depende do acervo real — baseline, precisão, descoberta sobre o catálogo — é medido na
máquina de referência e registrado no PR de cada card.
