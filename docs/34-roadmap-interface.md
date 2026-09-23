# Roadmap de interface — cadastro pela UI e consistência visual

## 1. Objetivo

O ciclo roda sozinho desde a Fase 13. O que ainda não roda sozinho é o **cadastro**:
adicionar uma fonte, uma empresa ou uma vaga continua exigindo `curl`, script ou acesso ao
banco. Este roadmap fecha essa lacuna e, junto com ela, a dívida visual que a interface
acumulou enquanto crescia tela a tela.

São duas frentes independentes, que se apoiam:

```text
Fase 14  cadastrar e curar pela interface   (o que falta poder fazer)
Fase 15  design, consistência e acesso      (como o que já existe se apresenta)
```

Nenhuma das duas afrouxa um gate existente. Uma fonte continua precisando de termos
revisados, collector testado e habilitação explícita; a diferença é que o operador passa a
poder registrar isso na tela em vez de no terminal.

---

## 2. Estado verificado

Auditoria contra o código em 22 de setembro de 2026.

| Capacidade | API | Interface |
| --- | --- | --- |
| Criar `SourceDefinition` | `POST /sources` | não existe |
| Homologar e habilitar fonte | `PATCH /sources/{id}` | não existe |
| Executar fonte agora | `POST /sources/{id}/runs` | `SourcesPage` |
| Entrada manual de vaga | `POST /sources/{id}/runs` com `inputs` | não existe |
| Criar ou editar empresa | não existe | não existe |
| Vincular fonte a empresa | `POST /companies/{id}/detect-source` | `CompanyDetailPage` |
| Editar perfil | `POST /profile/versions` e transições | `ProfilePage` |

Três consequências concretas:

- `SourcesPage` só sabe operar fontes que já existem — `apps/web/src/routes/SourcesPage.tsx`
  não tem um único `<form>`;
- empresa nova só entra pelo importador de pesquisa, o que torna o catálogo fechado a
  qualquer descoberta feita depois da importação;
- uma vaga avulsa que o operador encontra fora das fontes não tem caminho de entrada, ainda
  que o collector manual e o contrato `URL | TEXT | FILE` existam e sejam testados.

### 2.1 Dívida visual

A interface usa Tailwind 4 sem tema: as cores são literais hexadecimais repetidos em cada
arquivo — `#17322d`, `#6d827b`, `#dce4dc`, `#9b3e2e`, `#eef3df` aparecem dezenas de vezes.
O mapa de tom por status está duplicado entre `SourcesPage.tsx` e `OverviewPage.tsx`, e os
blocos de carregamento, vazio e erro são reescritos em cada rota com textos e classes
ligeiramente diferentes.

Isso não é estética: um estado de erro que muda de forma entre telas é um estado que o
operador precisa reaprender, e um token de cor que não existe é uma decisão de contraste
que ninguém consegue revisar.

---

## 3. Fase 14 — Cadastro e curadoria pela interface

Cards de execução: [Fase 14](34-roadmap-interface/fase-14/README.md).

### 3.1 Entregáveis

- formulário de criação de fonte com a configuração exigida por cada tipo de collector;
- controles de homologação e kill switch por fonte, com concorrência otimista;
- entrada manual de vaga por URL, texto ou arquivo, com o resultado da normalização visível;
- criação e edição de empresa, com reconciliação contra o catálogo existente;
- vínculo explícito entre empresa e fonte, a partir da proposta de descoberta.

### 3.2 Regras

- a interface não pode habilitar uma fonte externa sem evidência confirmada, data de
  revisão, termos revisados e collector testado — o gate é do domínio, não da tela;
- toda escrita concorrente usa a versão esperada que o recurso já expõe, e um conflito
  aparece como conflito, não como sobrescrita silenciosa;
- erro de validação do servidor é exibido no campo que o causou, e não como um texto solto;
- empresa criada pela tela passa pela mesma reconciliação do importador, para que um nome
  repetido vire alias e não uma segunda empresa;
- vaga manual entra pelo mesmo caminho de aquisição das demais: `SourceRun`, `RawItem`,
  normalização e procedência, sem atalho para `Opportunity`.

### 3.3 Critério de aceite

- [ ] operador cria, homologa, habilita e executa uma fonte inteira sem terminal;
- [ ] operador registra uma vaga avulsa e chega à oportunidade normalizada pela tela;
- [ ] operador cria uma empresa, corrige seus dados e vincula uma fonte a ela;
- [ ] nenhuma tela consegue burlar o gate de habilitação ou a imutabilidade da evidência;
- [ ] conflito de versão em qualquer escrita é reportado e recuperável sem perder o que foi
      digitado.

---

## 4. Fase 15 — Design, consistência e acesso

Cards de execução: [Fase 15](34-roadmap-interface/fase-15/README.md).

### 4.1 Entregáveis

- tema de design com tokens de cor, tipografia, espaçamento, raio e elevação;
- componentes compartilhados para botão, badge de status, cartão, tabela e campo;
- um único padrão para carregando, vazio, erro e conflito;
- acessibilidade verificável: rótulos, foco visível, contraste e navegação por teclado;
- comportamento responsivo definido para as tabelas densas;
- hierarquia declarada na Visão geral, navegação agrupada e carregamento sem salto.

### 4.2 Regras

- token novo só existe se substituir um literal em uso; a fase não inventa paleta;
- componente compartilhado nasce de duplicação real já presente no código;
- nenhuma mudança visual pode alterar o que uma tela afirma sobre os dados — a Fase 15 muda
  apresentação, nunca semântica;
- estado indisponível continua sendo exibido como indisponível: `null` não vira zero, e
  "sem dados" não vira "tudo certo".

### 4.3 Critério de aceite

- [ ] nenhuma cor hexadecimal literal permanece nos componentes de rota;
- [ ] status de fonte e de execução usam um único componente e um único mapa de tom;
- [ ] carregando, vazio, erro e conflito têm uma implementação compartilhada por tela;
- [ ] cada campo de formulário tem rótulo associado, erro programaticamente vinculado e
      foco visível;
- [ ] tabelas densas rolam dentro do próprio contêiner, sem rolagem horizontal da página;
- [ ] nenhum valor arbitrário de tipografia, raio ou sombra resta nas telas;
- [ ] a Visão geral responde primeiro o que exige ação hoje;
- [ ] a navegação mostra grupo e seção ativa, inclusive em tela estreita;
- [ ] carregar uma tela não desloca o conteúdo quando o dado chega.

---

## 5. Ordem recomendada

1. F15-01 e F15-02: tokens e componentes vêm antes dos formulários novos, para que a Fase 14
   não duplique mais três variações de botão e de campo.
2. F14-01 e F14-02: a fonte é o cadastro que hoje mais custa terminal.
3. F14-03: entrada manual de vaga, que depende apenas de existir uma fonte manual.
4. F14-04 e F14-05: empresa e vínculo, que exigem contrato novo de API.
5. F15-03 a F15-05: estados, acessibilidade e responsividade, aplicados ao conjunto já
   completo de telas.
6. F15-06 a F15-09: escala de forma, hierarquia da Visão geral, navegação e carregamento —
   a camada que separa uma interface consistente de uma interface acabada.

---

## 6. Milestones

## Milestone M — Operação sem terminal

```text
fonte, empresa e vaga entram e são curadas inteiramente pela interface
```

## Milestone N — Interface consistente

```text
um único sistema visual, com estados previsíveis e acessíveis em todas as telas
```

---

## 7. Recorte explícito

Não entram:

```text
tema escuro
internacionalização
autenticação e múltiplos usuários
edição de vaga normalizada por formulário livre
scraping de página protegida a partir de uma URL colada
biblioteca de componentes de terceiros
```

O radar continua local, de um operador só, e a evidência continua imutável.
