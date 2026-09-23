# CARD F15-08 — Navegação, orientação e ícones

- **Status:** Concluído em 2026-09-23
- **Fase:** 15 — Design, consistência e acesso
- **Depende de:** F15-06
- **Bloqueia:** Milestone N
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §4

## Resultado

A navegação diz onde o operador está, agrupa as sete telas pelo que elas servem, e continua
utilizável em tela estreita.

## Contexto

`PageShell` rende sete links de texto numa única linha que quebra conforme a largura. O
estado ativo é um sublinhado; em tela estreita, os links viram duas ou três fileiras de
texto solto sobre o cabeçalho, e a identidade visual do produto — um glifo `◉` e o nome —
divide espaço com eles.

As sete telas também não são do mesmo tipo. `Visão geral`, `Oportunidades` e `Candidaturas`
são o trabalho diário; `Empresas`, `Fontes` e `Perfil` são configuração e catálogo;
`Status` é diagnóstico. A navegação plana não conta isso, então a tela mais usada e a
menos usada aparecem com o mesmo peso.

Não há um único ícone na interface. Não é obrigatório que haja, mas hoje toda distinção
entre seções é tipográfica, e uma lista de sete palavras iguais é lida item a item, toda
vez.

## Escopo

- Agrupar a navegação por finalidade, com rótulo de grupo visível ou estrutura equivalente.
- Tornar o estado ativo legível sem depender de sublinhado fino: superfície, peso ou marca.
- Definir o comportamento em tela estreita — barra compacta, menu ou barra inferior — sem
  esconder a tela ativa.
- Criar um conjunto mínimo de ícones inline, um por seção, como apoio ao rótulo e nunca
  como substituto dele.
- Manter `aria-current`, o link para pular ao conteúdo e a ordem de tabulação.

## Fora de escopo

- Biblioteca de ícones de terceiros.
- Menu que esconda a navegação em tela larga.
- Renomear seções ou mudar rotas.

## Notas de implementação

Ícone acompanha o rótulo; nenhum item vira só símbolo. Um ícone sozinho obriga a decorar o
símbolo e é o caminho mais rápido para uma navegação que só o autor entende.

O glifo `◉` é a marca do produto e continua sendo. Se a barra compacta precisar de espaço,
o que cede é o texto do nome, não a marca.

## Critérios de aceite

- [x] A navegação mostra os grupos, e a seção ativa é identificável sem foco nem hover.
- [x] Em 360 px a navegação não quebra em mais de duas fileiras, nem esconde a seção ativa.
- [x] Cada item tem ícone e rótulo; nenhum item é só ícone.
- [x] `aria-current` continua na seção ativa e o link de pular ao conteúdo continua primeiro
      na ordem de tabulação.
- [x] Nenhuma rota mudou de endereço.

## Nota de execução

Três grupos com rótulo visível: **Dia a dia** (Visão geral, Oportunidades, Candidaturas),
**Catálogo** (Empresas, Fontes, Perfil) e **Diagnóstico** (Status). Cada grupo é uma lista
nomeada pelo próprio rótulo com `aria-labelledby`, então o leitor de tela ouve o grupo ao
entrar nele, e a seção ativa uma vez só, por `aria-current`.

A seção ativa virou superfície — pílula `ink` com texto `surface` e peso maior — no lugar
do sublinhado fino, e é legível sem foco nem cursor.

A navegação saiu da linha do nome e ganhou fileira própria. Em 1280 px os sete itens cabem
sem rolar. Em tela estreita a fileira não quebra: rola na horizontal dentro do próprio
contêiner, e ao abrir a página a seção ativa é trazida para dentro da vista — em 360 px a
tela de Status abre com "Status" visível, sem rolagem do documento. Foi a escolha em vez
de menu ou barra inferior porque nenhum dos dois mantém os grupos à vista, e o menu
esconderia justamente a seção ativa.

Os ícones são sete SVG inline em `components/icons.tsx`, com `aria-hidden` e traço em
`currentColor`: acompanham o rótulo, nunca o substituem, e seguem o tom do item ativo sem
token novo. A marca `◉` e o nome continuam onde estavam; com a navegação em fileira
própria, nenhum dos dois precisou ceder espaço.

Verificado em 360 px e 1280 px no navegador; `PageShell.test.tsx` cobre grupos, seção ativa
única, ícone oculto do leitor de tela e o link de pular ao conteúdo como primeiro alvo.

## Verificação

Percorrer as sete seções em 360 px, 768 px e 1280 px conferindo grupo, estado ativo e
tabulação; confirmar com leitor de tela que a seção ativa é anunciada uma vez.

## Arquivos prováveis

- `apps/web/src/components/PageShell.tsx`
- `apps/web/src/components/`
- `apps/web/src/styles.css`
