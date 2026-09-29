# Revisão: talentpluto e Pearl Talent são agências? (2026-09-29)

Contexto: fontes Workable do F20-60 (`talentpluto`, `pearltalent`). Pesquisa somente
leitura; nada foi ativado. Método: sites das empresas, perfil YC, resultados de busca e a
API pública de listagem da Workable (`apply.workable.com/api/v3/accounts/<slug>/jobs`,
total e títulos das primeiras 10 vagas em 2026-09-29).

## talentpluto

**Veredito: intermediário (plataforma de matching/headhunter de IA), não empregador
direto para a maioria das vagas.**

- Produto: "agente de carreira" por voz que apresenta candidatos (anônimos) a empresas
  parceiras; grátis para o candidato, pago pelas empresas. YC diz que não é agência
  tradicional, mas é marketplace de duas pontas; 5 pessoas, 27 mil+ profissionais, 50+
  empresas clientes (Mercor, Warp, Rho). Fonte: https://www.ycombinator.com/companies/talentpluto
  e https://talentpluto.com/
- Página Workable: 87 vagas, todas nos EUA, quase todas presenciais/híbridas; títulos
  claramente de clientes ("Account Executive - Warp", "Founding Account Executive -
  Bluejay", "Head of Marketing", "Chief of Staff", "Founding Go-to-Market"). Um time de
  5 pessoas não tem 87 vagas próprias: a Workable é usada como painel de vagas de clientes
  (nem toda vaga nomeia o cliente). Só "Recruiter (Path to Head of Talent)" parece ser da
  própria talentpluto. Fonte: https://apply.workable.com/talentpluto/
- Outras fontes: https://www.linkedin.com/company/talentpluto-inc ,
  https://pitchbook.com/profiles/company/865559-17

**Recomendação: não ativar na stack real.** Vagas são de terceiros (empresa do anúncio
ambígua ou errada), majoritariamente EUA presencial/híbrido, sem aderência ao perfil
remoto/Brasil, e o empregador correto (ex.: Warp, Bluejay) deve ser coletado direto no seu
próprio ATS. Se quiser aproveitar, tratar como fonte de descoberta de empresas
(`companies/discovery`), não como fonte de oportunidades.

## Pearl Talent

**Veredito: agência de staffing/recrutamento remoto (empregador não é o cliente final na
maioria das vagas).**

- Site: "Remote Staffing Agency for U.S. Founders"; coloca o "top 1%" de talentos das
  Filipinas, América Latina e África do Sul em startups dos EUA/UE; 1.200+ contratações,
  200+ clientes; taxa mensal fixa. O próprio site diz que a página de vagas é só para o
  time interno da Pearl e que vagas de clientes são pela página "For Talent". Fontes:
  https://www.pearltalent.com/ , https://www.pearltalent.com/about ,
  https://www.pearltalent.com/for-talent
- Workable: 51 vagas. Mistura: vagas próprias com prefixo "Pearl Talent - ..." (VP
  Marketing, AE Healthcare, EUA) e muitas vagas de cliente sem nome, publicadas como
  "Remote ... for an Energy Operations Company", "Remote Head of Growth for Climate Tech &
  Enterprise SaaS", "Executive Assistant - B086 (SR)" (código de requisição), em
  Filipinas, México, Honduras, Rep. Dominicana. Fonte: https://apply.workable.com/pearltalent/
- Reputação de terceiros: https://www.trustpilot.com/review/pearltalent.com (não
  analisada em detalhe).

**Recomendação: não ativar como empregador.** A maioria das vagas é anônima para o
candidato (cliente oculto), o que dá `company` errada e sinal fraco. Opcional: ativar
somente com filtro que mantenha vagas com prefixo "Pearl Talent - " (time próprio) e
descarte as de cliente; sem esse filtro, não ativar. Vagas para o Brasil não apareceram na
amostra (LatAm: México, Honduras, R. Dominicana).

## Incertezas

- Amostra de apenas 10 de 87 e 10 de 51 vagas; a proporção real próprio/cliente é
  estimada.
- Páginas Workable renderizam por JS: o texto completo das vagas não foi lido, o veredito
  vem dos títulos, do campo de localização e dos sites das empresas.
- Não foi verificado se alguma vaga de Pearl/talentpluto é elegível ao Brasil nem o
  restante das vagas.
