# DESIGN.md — Bateia (interface web)

Fonte de verdade da marca, dos tokens e das regras visuais de `apps/web`. A marca **Bateia**,
direção **Correnteza**, foi escolhida pelo dono em 2026-10-20, a partir do estudo em
[docs/research/2026-10-20-branding-concorrentes.md](docs/research/2026-10-20-branding-concorrentes.md).
Ela substitui a direção petróleo da [SPEC 54](docs/54-spec-redesign-completo-frontend.md) (§5);
a composição das telas da SPEC 54 continua valendo.

**Estado da migração.** Este arquivo descreve o destino. Até a fase 1 do
[plano de implementação](docs/superpowers/plans/2026-10-20-marca-bateia.md) terminar,
`apps/web/src/styles.css` ainda tem os valores da SPEC 54. Depois da fase 1 vale a regra de
sempre: os tokens vivem em `styles.css` (`@theme` e bloco escuro), o contraste está medido em
[docs/35-design-tokens.md](docs/35-design-tokens.md) e é imposto por
`apps/web/src/styles.test.ts`. Se este arquivo e o CSS divergirem, o CSS é o valor e este
arquivo é a regra: corrija o que estiver errado no mesmo commit.

O repositório, o pacote Python e os nomes técnicos continuam `opportunity-radar`. "Bateia" é o
nome do produto na interface, no título da página, no ícone e nos textos.

## 0. Marca

| Item | Definição |
| --- | --- |
| Nome | **Bateia**, sempre com inicial maiúscula no texto; `bateia` minúsculo só no wordmark. A bateia é a bacia do garimpeiro: separa o ouro do cascalho girando a água. |
| Propósito | Devolver a quem procura trabalho o controle da própria busca. |
| Promessa | Menos vagas, cada uma com o porquê. A pessoa vê o que combina, o que falta e de onde a vaga veio antes de gastar uma tarde numa candidatura. |
| Público | Profissionais de tecnologia e áreas digitais no Brasil, de pleno a sênior, buscando remoto ou híbrido. Usam três ou mais fontes, já cansaram de vaga fantasma e abrem o app todo dia por alguns minutos. Secundário: quem está empregado e só quer ficar de olho. |
| Personalidade | Criteriosa, franca, calma, do lado de quem procura. Não é coach, não é RH, não é animadora de palco. |

### Princípios de design

1. **Mostre o porquê.** Todo número tem explicação a um clique, e o motivo principal cabe na
   linha da Inbox.
2. **Calma para uso diário.** Densidade sem ruído: sem gamificação, sem cor de alarme para o
   que não é urgente, sem contagem de volume como prova de valor.
3. **Uma decisão por tela.** A Inbox decide relevância; o detalhe decide candidatura; o
   pipeline decide o próximo passo.
4. **Incerteza visível, sem alarme.** Data estimada, avaliação desatualizada e IA indisponível
   aparecem como fato, em tom neutro, com o que continua valendo.
5. **Seus dados, sua bateia.** A interface diz onde a IA roda e o que sai do computador da
   pessoa. Nenhuma empresa vê o perfil dela no produto.

### O que a marca evita

O estudo de concorrentes mostrou o que todos repetem. A Bateia não usa: azul corporativo como
cor principal; wordmark minúsculo arredondado "amigável"; hero com campo "cargo + cidade";
volume como prova ("+1 milhão de vagas"); match em porcentagem opaca ou atrás de paywall;
copy motivacional ("o emprego dos seus sonhos"); mascote ou foto de pessoas sorrindo;
onboarding que pede currículo antes de mostrar valor.

## 1. Traços a reproduzir

- Pedra de rio, água e uma pepita. Neutros frios esverdeados, um acento **verde-rio** e um
  **dourado** reservado ao que vale a pena. Não é painel administrativo nem portal de vagas.
- Fundo `canvas` de pedra clara (ou rio à noite no tema escuro); sidebar de ~15rem em tom
  próprio (`sidebar`); painéis em `surface`; elevação por borda, não por sombra.
- Sidebar em três grupos pela pergunta que respondem: **Decidir** (Visão geral, Inbox,
  Pipeline), **Pesquisar** (Empresas), **Operar** (Fontes, Homologação, Perfil, Status). Item
  atual: fundo `surface`, texto `ink` em 600 e marcador `accent` na borda esquerda.
- Rodapé da sidebar com a nota de privacidade: onde a IA roda e que nenhuma empresa vê o
  perfil. É fato do produto, não slogan; some se deixar de ser verdade.
- Título de página em Young Serif; todo o resto em Schibsted Grotesk.
- Linha da Inbox: título, empresa e local, motivo principal em uma frase (quando há), pepitas
  do match, veredito e idade da vaga. Nada de logo de empresa como elemento principal.
- Prazo e próxima ação usam `warning-ink`; nunca a cor da marca.
- Sem gradiente e sem sombra difusa. A única sombra é `shadow-overlay`.

## 2. Cor

Dois temas com os mesmos nomes de token. O claro é o padrão. O escuro vale quando o sistema
pede (`prefers-color-scheme: dark`) ou quando a pessoa escolhe (`data-theme="dark"` em
`<html>`); `data-theme="light"` força o claro. Nome pelo papel, não pelo tom.

### Neutros e acento

| Token | Claro | Escuro | Papel |
| --- | --- | --- | --- |
| `canvas` | `#ECEEEA` | `#0E1412` | fundo do app |
| `surface` | `#FAFBF8` | `#161E1B` | painel, linha, campo, item atual, texto sobre `accent` |
| `raised` | `#FAFBF8` | `#1B2521` | compatibilidade; no escuro, um degrau acima de `surface` |
| `panel` | `#F1F3EF` | `#1A2420` | cabeçalho de tabela, bloco de resumo, caixa de critério |
| `sidebar` | `#E4E8E2` | `#111816` | fundo da sidebar e da barra do menu móvel |
| `line` | `#CBD2CA` | `#2A3631` | borda estrutural silenciosa |
| `line-strong` | `#A3ADA5` | `#3E4C46` | borda de botão outlined, pílula, chip |
| `divider` | `#DCE1DA` | `#222D29` | separador de linha de tabela e lista |
| `control-line` | `#6F7B74` | `#6E7D76` | borda de campo e checkbox (>= 3:1) |
| `ink` | `#18221E` | `#E4EAE5` | texto primário |
| `ink-hover` | `#2B3732` | `#C9D2CC` | `ink` em hover, quando usado como fundo |
| `subtle` | `#3F4B45` | `#B4C0B9` | subtítulo, texto secundário, item de navegação |
| `muted` | `#55625B` | `#98A69E` | rótulo de grupo, metadado, hora |
| `neutral-ink` | `#3F4B45` | `#B4C0B9` | texto de badge neutro |
| `accent` | `#1E5B4B` | `#79C2A6` | verde-rio: ação primária, foco, item atual, link |
| `accent-hover` | `#16483B` | `#93D0B8` | ação primária em hover |
| `accent-ink` | `#1E5B4B` | `#79C2A6` | texto de link e de item atual |
| `accent-surface` | `#E2EEE8` | `#1C2E28` | seleção, contexto, hover leve |
| `brand` | `#1E5B4B` | `#79C2A6` | fundo do ícone; anéis do logo |

### Pepita (novo papel)

| Token | Claro | Escuro | Papel |
| --- | --- | --- | --- |
| `nugget` | `#A87A12` | `#E2B54D` | pepita preenchida do match, ponto do logo (>= 3:1, não é texto) |
| `nugget-ink` | `#7D5508` | `#E9C46A` | texto do veredito Alta prioridade |
| `nugget-surface` | `#F6EBCF` | `#2E2814` | fundo do veredito Alta prioridade |

O dourado só aparece em três lugares: pepitas do match, ponto do logo e veredito **Alta
prioridade**. Não é cor de botão, de link nem de decoração.

### Tons semânticos

| Estado | Superfície (claro / escuro) | Traço | Texto |
| --- | --- | --- | --- |
| Sucesso | `success-surface` `#E6F0DF` / `#1B2A17`; `-soft` `#EEF5E9` / `#17241A`; `-strong` `#D8E8CD` / `#22351D` | `success-line` `#A6C597` / `#4C6E3E` | `success-ink` `#2D5A1E` / `#A9D38F`; `-strong` `#244A17` / `#BFE0A8` |
| Atenção | `warning-surface` `#F7E9DA` / `#33231A`; `-strong` `#F1DEC8` / `#3D2A1E` | `warning-line` `#DDB58E` / `#7A5233` | `warning-ink` `#7A3E10` / `#F0B07F`; `-strong` `#6B360D` / `#F5C39C` |
| Erro | `danger-surface` `#F8E6E3` / `#351C1A`; `-strong` `#F3DAD6` / `#40221F` | `danger-line` `#DDAFA8` / `#7D3F38` | `danger-ink` `#8A2E25` / `#F2A39A` |
| Informação | `info-surface` `#E4ECEE` / `#1A2A2E` | — | `info-ink` `#2F4A52` / `#A7C8D0` |

O verde de sucesso puxa para folha (amarelado); o acento puxa para rio (azulado). Os dois não
se confundem e sucesso nunca vira marca.

Contraste medido em 2026-10-20 para todos os pares de `styles.test.ts`, nos dois temas: todos
os textos >= 4.5:1 e todos os controles >= 3:1. Menores valores: `muted` sobre `sidebar` 5.16
(claro); `nugget` sobre `canvas` 3.30 (claro).

## 3. Forma, tipografia e ritmo

| Token | Valor | Uso |
| --- | --- | --- |
| `radius-panel` | 0.75rem | painel, tabela, cartão de vaga |
| `radius-control` | 0.5rem | botão, campo, item da sidebar |
| `radius-chip` | 999px | chip, veredito e filtro: forma de seixo |
| `shadow-overlay` | `0 4px 16px rgb(14 20 18 / 0.16)` | única sombra: gaveta e menu sobrepostos |
| `font-display` | Young Serif + `Georgia, serif` | título de página, wordmark, título de estado vazio |
| `font-sans` | Schibsted Grotesk variável + `system-ui` | interface, corpo, números |
| `text-page-title` | 1.75rem / 2.25rem / 400 / -0.01em, `font-display` | título de página |
| `text-section` | 1.125rem / 1.4 / 600 | título de seção |
| `text-body` | 1rem / 1.65 | texto corrido |
| `text-body-sm`, `text-prose` | 0.875rem | célula, corpo, subtítulo |
| `text-caption` | 0.75rem / 1rem / 500 | grupo da sidebar, chip, metadado |
| `text-metric-lg`, `-metric`, `-metric-sm` | 2.25 / 1.875 / 1.5rem / 600 | números de métrica, algarismos tabulares |
| altura de controle | 2rem (`sm`), 2.25rem (padrão); 44px abaixo de `md` | alvo de toque |
| espaçamento | base de 4px; 16-24px em decisão, 8-12px em lista densa | ritmo |
| sidebar | 15rem, `p-3`, item `h-9` | largura fixa `md+` |

Young Serif tem um só peso (400) e só aparece em tamanhos a partir de 1.5rem. Rótulos não usam
caixa alta com espaçamento largo; grupo da sidebar usa `text-caption` em 600, caixa normal.

## 4. Logo e ícone

- **Símbolo:** a bateia vista de cima. Três anéis concêntricos em `brand` (raios 14, 9 e 4
  numa grade de 32, traço 2) e uma pepita em `nugget` (raio 2.8) no quadrante superior
  direito, centro em (21.5, 11). Lê como bateia e como radar; é a ponte com o nome antigo.
- **Wordmark:** `bateia` em Young Serif, minúsculo, à direita do símbolo. Na interface, wordmark
  em 1.5rem ao lado do símbolo de 28px; a regra de altura do x vale para o logo em arte, não
  para a interface. Na arte, altura do x igual a metade do símbolo. Espaço livre mínimo: a
  distância entre dois anéis.
- **Ícone do app:** quadrado com cantos de 22% em `brand`, anéis em `surface` e pepita em
  `nugget`. No tema escuro: fundo `surface`, anéis em `brand`.
- **Favicon:** SVG com o ícone do app; em 16px some o anel interno. PNG 32/180/192/512 gerados
  do mesmo SVG. O ícone de toque (180) é quadrado cheio, sem cantos transparentes; o maskable
  (512) tem os anéis dentro de 80% do centro.
- O símbolo nunca gira, nunca ganha gradiente e a pepita nunca muda de lugar.

## 5. Match explicado

- **Pepitas na Inbox:** o item da Inbox traz só o score (0 a 100), não os fatores. A régua
  tem 10 pepitas; ficam cheias `round(score / 10)` delas, seguidas do score em texto
  ("76 de 100"). Sem score, a régua não aparece e o texto diz "Sem avaliação".
- **Pepitas no detalhe:** uma por fator de `MatchFactor` com `status` diferente de
  `NOT_APPLICABLE`. Cheia (`nugget`) quando `status = KNOWN` e `rawScore >= 0.5`; vazada (borda
  `nugget`) quando `KNOWN` e `rawScore < 0.5`; tracejada (borda `muted`) quando `UNKNOWN`. Texto
  ao lado: "6 de 9 fatores atendidos, 1 sem dado".
- Estado nunca só por cor: o texto acompanha sempre a régua.
- **Veredito:** chip com o rótulo existente (`verdictLabels`). Alta prioridade usa `nugget-*`;
  Recomendada usa `accent-surface`/`accent-ink`; Revisão necessária usa `warning-*`;
  Inelegível usa `danger-*`; Observação e Baixa aderência são neutros.
- **Motivo principal:** na linha da Inbox, a frase é `analysisSummary` quando existe. Sem ela,
  a linha não inventa motivo. Um motivo determinístico vindo da API é melhoria futura fora
  deste plano.
- **Detalhe:** caixa "Por que combina" lista cada fator com sua `explanation`, ✓ para
  atendido, − para faltante e ? para sem dado; "O que impede" (filtros eliminatórios) aparece
  antes, quando houver.

## 6. Regras

1. Nenhum hexadecimal literal em `.ts/.tsx` (lint `no-restricted-syntax`); valor novo vira
   token em `styles.css`.
2. Contraste medido nos dois temas: texto >= 4.5:1 em todo par documentado; componente de
   interface (campo, checkbox, anel de foco, pepita) >= 3:1. Falha em
   `apps/web/src/styles.test.ts`.
3. Um só acento: verde-rio. Serve a orientação, item atual, links, foco e ação primária. O
   dourado é papel próprio e restrito (§2, Pepita). Cores de estado continuam semânticas e
   nunca viram marca nem decoração.
4. Foco: anel `:focus-visible` de 3px em `accent`, offset 3px, desenhado fora do elemento.
5. Estado nunca só por cor: texto no chip, `aria-current` e marcador mais peso no item atual,
   contagem em texto ao lado das pepitas.
6. Sem animação nova; `prefers-reduced-motion: reduce` neutraliza animação e transição
   globalmente.
7. A única primitiva de acessibilidade aprovada é `@radix-ui/react-dialog@1.2.0`, somente atrás
   de wrappers em `apps/web/src/components/ui/`; rotas, formulários e módulos de feature nunca
   a importam diretamente. Não adicionar outro primitive Radix sem nova medição.
8. Migração por valores, não por nomes: os tokens da SPEC 54 mantêm o nome e trocam o valor;
   token novo só quando o papel não tem nome (`nugget*`, `font-display`).
9. Tema escuro é suportado: toda tela nova é conferida nos dois temas. Cor só por token; um
   componente nunca escolhe cor por tema.
10. Textos da interface em português do Brasil, na voz da §8.

## 7. Fontes

Auto-hospedadas por pacote npm, subset latin, `font-display: swap`, referenciadas por
`@font-face` em `styles.css` e empacotadas pelo Vite. Nenhuma requisição a terceiro em tempo de
execução.

| Papel | Pacote | Licença | Observação |
| --- | --- | --- | --- |
| `font-sans` | `@fontsource-variable/schibsted-grotesk` 5.3.0 | OFL-1.1 | variável 400-900; substitui Inter |
| `font-display` | `@fontsource/young-serif` 5.3.0 | OFL-1.1 | peso único 400 |

Fallbacks: `system-ui` para `font-sans`; `Georgia, serif` para `font-display`. Remover
`@fontsource-variable/inter` quando nenhuma tela usar Inter.

## 8. Voz e textos

- PT-BR direto, frases curtas, número com unidade e hora com "h" ("às 6h", "há 2 dias").
- Diga o que aconteceu e o que continua valendo. Sem desculpa, sem exclamação, sem
  "ops".
- Admita incerteza: "Falta salário nesta vaga." / "Data estimada pela fonte."
- Código técnico (`AI_FAILED`, ids, versões) não aparece no texto principal; vai para um
  detalhe recolhido, se for útil.
- Verbo de ação nos botões, igual do começo ao fim do fluxo: "Vou me candidatar" gera
  "Candidatura registrada".

| Em vez de | Escreva |
| --- | --- |
| Oportunidade (no texto) | Vaga |
| Análise semântica | Leitura da IA |
| Análise semântica indisponível (AI_FAILED). A decisão determinística permanece completa. | A IA não leu esta vaga. O match acima continua valendo. |
| Fatores do score | Por que combina |
| Filtros eliminatórios | O que impede |
| Procedência | De onde veio |
| Encontre o emprego dos seus sonhos | Menos vagas, cada uma com o porquê. |

Exemplos de estado:

- Inbox vazia: "Nada novo desde ontem às 18h. A próxima coleta roda às 6h."
- Fonte com falha: "A Gupy não respondeu. Tentamos de novo às 14h10."
- Cabeçalho da Inbox: "6 vagas valem seu tempo, de 214 coletadas desde ontem."
