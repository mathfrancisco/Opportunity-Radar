"""Area of a job posting (`role-family-v1`), decided by deterministic rules.

Card F17-02. The collectors bring a company's whole board; without an area, every new
source adds sales, marketing and operations to the Inbox. The area is a filter, never a
matching factor: it does not enter the score.

The rules run in a fixed order and each decision keeps the evidence that made it:

1. the department the ATS declared, looked up in a table (Portuguese and English);
2. patterns in the title, the most specific pattern winning;
3. terms of the description, only to break a tie between areas the title matched equally.

A department such as "Engineering" or "Product" covers several areas, so the title may
narrow it to one of them (a "Data Engineer" in Engineering is DATA), never move it outside.
Titles that name a sales, support or engineering job depending on the team ("Solutions
Engineer", "Sales Engineer", "Developer Advocate") are decided by the department alone:
without one they are UNKNOWN, because an unclassified posting stays visible in the Inbox
and a wrong guess hides it.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

#: Version of the classification rules. Any change to them is a new version, applied
#: retroactively to the whole collection.
ROLE_FAMILY_VERSION = "role-family-v1"


class RoleFamily(StrEnum):
    SOFTWARE_ENGINEERING = "SOFTWARE_ENGINEERING"
    DATA = "DATA"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    SECURITY = "SECURITY"
    QA = "QA"
    PRODUCT = "PRODUCT"
    DESIGN = "DESIGN"
    SALES = "SALES"
    MARKETING = "MARKETING"
    OPERATIONS = "OPERATIONS"
    PEOPLE = "PEOPLE"
    FINANCE = "FINANCE"
    LEGAL = "LEGAL"
    SUPPORT = "SUPPORT"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


#: What a profile may declare as an area of interest. UNKNOWN is not a preference: the
#: Inbox always shows it next to the chosen areas, since an unclassified posting may be one.
PROFILE_ROLE_FAMILIES = tuple(item.value for item in RoleFamily if item is not RoleFamily.UNKNOWN)


@dataclass(frozen=True, slots=True)
class RoleFamilyDecision:
    """An area and what decided it: `rule`, `term` and `origin`, plus context keys."""

    role_family: RoleFamily
    evidence: dict[str, str] = field(default_factory=dict)
    version: str = ROLE_FAMILY_VERSION


@dataclass(frozen=True, slots=True)
class _Rule:
    family: RoleFamily
    specificity: int
    pattern: re.Pattern[str]
    #: Areas a title may narrow this department to. Only department rules use it.
    refinable: frozenset[RoleFamily] = frozenset()


def normalize_role_text(value: str | None) -> str:
    """Casefold, strip accents and keep only words, so "Desenvolvedor(a) Back-end Sênior"
    reads "desenvolvedor a back end senior". `+` and `#` survive for C++ and C#."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(item for item in decomposed if not unicodedata.combining(item))
    return " ".join(re.sub(r"[^a-z0-9+#]+", " ", stripped.casefold()).split())


def _rules(
    family: RoleFamily,
    specificity: int,
    fragments: Sequence[str],
    *,
    refinable: frozenset[RoleFamily] = frozenset(),
) -> tuple[_Rule, ...]:
    # A fragment matches whole words only: "sre" must not match inside "presre".
    return tuple(
        _Rule(
            family=family,
            specificity=specificity,
            pattern=re.compile(rf"(?<![^ ])(?:{fragment})(?![^ ])"),
            refinable=refinable,
        )
        for fragment in fragments
    )


_F = RoleFamily

# Title vocabulary shared by several areas.
_EN_ROLE = r"(?:engineers?|developers?|programmers?)"
_PT_ROLE = r"(?:desenvolvedor(?:a|es|as)?|engenheir[oa]s?|programador(?:a|es|as)?)"
#: "Desenvolvedor(a)" normalizes to "desenvolvedor a".
_PT_GENDER = r"(?: [ao])?"
_PT_LEAD = (
    r"(?:analista|especialista|gerente|gestor(?:a)?|coordenador(?:a)?|assistente|"
    r"supervisor(?:a)?|diretor(?:a)?|consultor(?:a)?|lider|head|executiv[oa]|representante)"
)

_TECH_AREAS = frozenset({_F.DATA, _F.INFRASTRUCTURE, _F.SECURITY, _F.QA})
_PRODUCT_ORG = frozenset(
    {_F.DESIGN, _F.SOFTWARE_ENGINEERING, _F.DATA, _F.INFRASTRUCTURE, _F.SECURITY, _F.QA}
)

#: Department names, normalized. A department decides the area when exactly one area
#: holds its most specific match; a department the table does not know decides nothing.
DEPARTMENT_RULES: tuple[_Rule, ...] = (
    *_rules(
        _F.SOFTWARE_ENGINEERING,
        1,
        (
            r"engineering",
            r"engenharia",
            r"technology",
            r"tecnologia",
            r"tech",
            r"ti",
            r"r d",
            r"research (?:and )?development",
            r"pesquisa e desenvolvimento",
            r"p d",
            r"development",
            r"desenvolvimento",
            r"software",
        ),
        refinable=_TECH_AREAS,
    ),
    *_rules(
        _F.SOFTWARE_ENGINEERING,
        2,
        (
            r"software (?:engineering|development)",
            r"(?:engenharia|desenvolvimento) de software",
            r"(?:back ?end|front ?end|full ?stack|mobile|web|ios|android)"
            r"(?: engineering| development)?",
        ),
        refinable=_TECH_AREAS,
    ),
    *_rules(
        _F.SOFTWARE_ENGINEERING,
        2,
        (
            r"product (?:and )?(?:engineering|development|technology|tech)",
            r"(?:engineering|technology|tech) (?:and )?product",
        ),
        refinable=_TECH_AREAS | {_F.PRODUCT, _F.DESIGN},
    ),
    *_rules(
        _F.DATA,
        1,
        (
            r"data",
            r"dados",
            r"analytics",
            r"business intelligence",
            r"bi",
            r"machine learning",
            r"ml",
            r"artificial intelligence",
            r"inteligencia artificial",
        ),
    ),
    *_rules(
        _F.DATA,
        2,
        (
            r"data (?:engineering|science|platform|analytics)",
            r"(?:engenharia|ciencia) de dados",
        ),
    ),
    *_rules(
        _F.INFRASTRUCTURE,
        1,
        (
            r"infrastructure",
            r"infraestrutura",
            r"infra",
            r"devops",
            r"sre",
            r"site reliability",
            r"cloud",
            r"sysadmin",
            r"it",
            r"information technology",
        ),
        refinable=frozenset({_F.SECURITY, _F.SUPPORT}),
    ),
    *_rules(
        _F.INFRASTRUCTURE,
        2,
        (
            r"it operations",
            r"platform (?:engineering|infrastructure|operations)",
            r"(?:infrastructure|cloud) (?:engineering|operations)",
        ),
        refinable=frozenset({_F.SECURITY, _F.SUPPORT}),
    ),
    *_rules(
        _F.SECURITY,
        1,
        (
            r"security",
            r"seguranca",
            r"cybersecurity",
            r"ciberseguranca",
            r"infosec",
            r"information security",
        ),
    ),
    *_rules(
        _F.SECURITY,
        2,
        (r"security (?:engineering|operations)", r"seguranca da informacao"),
    ),
    *_rules(_F.QA, 1, (r"qa", r"testing")),
    *_rules(
        _F.QA,
        2,
        (
            r"quality assurance",
            r"(?:test|quality) engineering",
            r"qualidade de software",
        ),
    ),
    *_rules(
        _F.PRODUCT,
        1,
        (r"product", r"produto", r"produtos"),
        refinable=_PRODUCT_ORG,
    ),
    *_rules(
        _F.PRODUCT,
        2,
        (r"product management", r"gestao de produtos?"),
        refinable=_PRODUCT_ORG,
    ),
    *_rules(_F.DESIGN, 1, (r"design", r"ux", r"user experience", r"ux ui", r"ui ux")),
    *_rules(_F.DESIGN, 2, (r"(?:product|ux) design", r"design (?:and )?research")),
    *_rules(
        _F.SALES,
        1,
        (r"sales", r"vendas", r"comercial", r"revenue", r"partnerships?"),
    ),
    *_rules(
        _F.SALES,
        2,
        (
            r"business development",
            r"account management",
            r"sales engineering",
            r"inside sales",
            r"(?:desenvolvimento de|novos) negocios",
        ),
    ),
    *_rules(
        _F.MARKETING,
        1,
        (
            r"marketing",
            r"communications",
            r"comunicacao",
            r"brand",
            r"public relations",
            r"relacoes publicas",
        ),
        refinable=frozenset({_F.DESIGN}),
    ),
    *_rules(
        _F.MARKETING,
        2,
        (r"(?:product|growth|performance|digital) marketing", r"marketing operations"),
        refinable=frozenset({_F.DESIGN}),
    ),
    *_rules(
        _F.OPERATIONS,
        1,
        (
            r"operations",
            r"operacoes",
            r"bizops",
            r"logistics",
            r"logistica",
            r"supply chain",
            r"procurement",
            r"compras",
            r"facilities",
            r"administrative",
            r"administrativo",
        ),
    ),
    *_rules(
        _F.OPERATIONS,
        2,
        (r"(?:business|revenue|strategy) operations", r"strategy (?:and )?operations"),
    ),
    *_rules(
        _F.PEOPLE,
        1,
        (
            r"people",
            r"hr",
            r"human resources",
            r"recursos humanos",
            r"rh",
            r"talent",
            r"recruiting",
            r"recrutamento",
            r"gente",
            r"pessoas",
        ),
    ),
    *_rules(
        _F.PEOPLE,
        2,
        (
            r"people (?:operations|ops|and culture|culture)",
            r"talent acquisition",
            r"gente e gestao",
            r"departamento pessoal",
        ),
    ),
    *_rules(
        _F.FINANCE,
        1,
        (
            r"finance",
            r"financeiro",
            r"financas",
            r"accounting",
            r"contabilidade",
            r"controladoria",
            r"tesouraria",
            r"treasury",
            r"fp a",
            r"tax",
            r"fiscal",
            r"billing",
        ),
    ),
    *_rules(
        _F.FINANCE,
        2,
        (r"(?:finance|financial) (?:operations|planning)",),
    ),
    *_rules(
        _F.LEGAL,
        1,
        (r"legal", r"juridico", r"compliance", r"regulatory", r"regulatorio"),
    ),
    *_rules(
        _F.LEGAL,
        2,
        (r"legal operations", r"legal (?:and )?compliance"),
    ),
    *_rules(
        _F.SUPPORT,
        1,
        (
            r"support",
            r"suporte",
            r"customer success",
            r"sucesso do cliente",
            r"customer experience",
            r"cx",
            r"customer service",
            r"atendimento",
            r"customer care",
            r"help ?desk",
            r"service desk",
        ),
    ),
    *_rules(
        _F.SUPPORT,
        2,
        (
            r"customer (?:support|success|experience|service|care|operations)",
            r"(?:support|technical support) operations",
            r"technical support",
        ),
    ),
)

#: Title patterns, normalized. The highest specificity among the matches wins; a tie
#: between areas at that level goes to the description, and a boundary title (UNKNOWN at
#: the top) goes to nobody.
TITLE_RULES: tuple[_Rule, ...] = (
    *_rules(
        _F.UNKNOWN,
        4,
        (
            r"solutions? (?:engineers?|engineering|architects?)",
            r"(?:pre sales|presales|sales) (?:engineers?|engineering|architects?)",
            r"developer (?:advocates?|relations|evangelists?)",
            r"dev ?rel",
            r"technical account managers?",
            r"customer engineers?",
            r"forward deployed engineers?",
            rf"(?:engenheir[oa]s?|arquitet[oa]s?){_PT_GENDER} de (?:solucoes|pre vendas|vendas)",
            r"pre vendas",
        ),
    ),
    *_rules(_F.QA, 4, (r"(?:engineers?|developers?) in test",)),
    *_rules(_F.OTHER, 4, (r"seguranca do trabalho",)),
    *_rules(
        _F.SOFTWARE_ENGINEERING,
        3,
        (
            r"(?:software|back ?end|front ?end|full ?stack|mobile|ios|android|web|application|"
            rf"embedded|game|product|growth|ui) {_EN_ROLE}",
            rf"{_PT_ROLE}{_PT_GENDER}(?: de)? (?:software|sistemas|back ?end|front ?end|"
            r"full ?stack|mobile|ios|android|aplicacoes|web)",
            r"(?:tech|technical) leads?",
            r"lider tecnic[oa]",
            rf"(?:staff|principal) {_EN_ROLE}",
            r"analista (?:de )?(?:sistemas|desenvolvimento)",
            r"analista desenvolvedor(?:a)?",
            r"software architects?",
            r"arquitet[oa] de software",
            r"(?:engenharia|desenvolvimento) de software",
        ),
    ),
    *_rules(
        _F.SOFTWARE_ENGINEERING,
        2,
        (
            r"software",
            r"back ?end",
            r"front ?end",
            r"full ?stack",
            r"ios",
            r"android",
            r"mobile",
            r"engineering",
            r"engenharia",
        ),
    ),
    *_rules(_F.SOFTWARE_ENGINEERING, 1, (_EN_ROLE, _PT_ROLE, r"devs?", r"swe", r"sde")),
    *_rules(
        _F.DATA,
        3,
        (
            r"data (?:engineers?|engineering|scientists?|science|analysts?|analytics|architects?|"
            r"developers?|modell?ers?|stewards?|specialists?|platform|operations|ops)",
            r"(?:machine learning|ml|mlops|deep learning|computer vision|nlp) "
            r"(?:engineers?|scientists?|researchers?|developers?|specialists?)",
            r"analytics engineers?",
            r"(?:business intelligence|bi) (?:analysts?|engineers?|developers?|specialists?)",
            r"(?:cientista|engenheir[oa]|analista|arquitet[oa]|especialista)"
            rf"{_PT_GENDER} de (?:dados|bi|business intelligence|machine learning|analytics)",
            r"(?:ciencia|engenharia|analise) de dados",
            r"(?:applied|research) scientists?",
        ),
    ),
    *_rules(
        _F.DATA,
        2,
        (
            r"data",
            r"dados",
            r"analytics",
            r"machine learning",
            r"business intelligence",
            r"bi",
            r"deep learning",
            r"computer vision",
            r"nlp",
            r"statisticians?",
            r"estatistic[oa]s?",
        ),
    ),
    *_rules(
        _F.INFRASTRUCTURE,
        3,
        (
            r"(?:devops|dev ops|sre|site reliability|platform|infrastructure|infra|cloud|network|"
            r"networking|linux|build|release|observability|production|reliability) "
            r"(?:engineers?|engineering|architects?|specialists?)",
            r"(?:systems?|network|linux|cloud|database) administrators?",
            r"sysadmins?",
            r"(?:engenheir[oa]|analista|especialista|arquitet[oa]|administrador(?:a)?)"
            rf"{_PT_GENDER}(?: de)? (?:infraestrutura|infra|cloud|redes|devops|sre|plataforma)",
            r"(?:it|infrastructure|cloud|network|production) operations",
            r"data ?center",
        ),
    ),
    *_rules(
        _F.INFRASTRUCTURE,
        2,
        (
            r"devops",
            r"dev ops",
            r"sre",
            r"site reliability",
            r"infrastructure",
            r"infraestrutura",
            r"infra",
            r"cloud",
        ),
    ),
    *_rules(
        _F.SECURITY,
        3,
        (
            r"(?:security|cybersecurity|cyber security|infosec|appsec|soc) (?:engineers?|"
            r"engineering|analysts?|architects?|specialists?|researchers?|consultants?|operations)",
            r"(?:penetration|pen) testers?",
            r"pentesters?",
            r"ethical hackers?",
            r"(?:analista|engenheir[oa]|especialista|arquitet[oa]|consultor(?:a)?)"
            rf"{_PT_GENDER}(?: de)? (?:seguranca|ciberseguranca|cyber ?security)",
            r"ciso",
        ),
    ),
    *_rules(
        _F.SECURITY,
        2,
        (
            r"security",
            r"seguranca",
            r"cybersecurity",
            r"cyber security",
            r"ciberseguranca",
            r"infosec",
            r"appsec",
            r"pentest(?:ing)?",
            r"red team",
            r"blue team",
        ),
    ),
    *_rules(
        _F.QA,
        3,
        (
            r"(?:qa|quality assurance|test|testing|test automation|automation test|software test|"
            r"qa automation) (?:engineers?|engineering|analysts?|specialists?|leads?|architects?)",
            r"sdets?",
            r"(?:analista|engenheir[oa]|especialista)"
            rf"{_PT_GENDER}(?: de)? (?:qa|testes|qualidade de software|automacao de testes)",
        ),
    ),
    *_rules(
        _F.QA,
        2,
        (r"qa", r"quality assurance", r"testers?", r"testes", r"test automation"),
    ),
    *_rules(
        _F.PRODUCT,
        3,
        (
            r"(?:product|produto) (?:managers?|owners?|leads?|directors?|analysts?|operations|"
            r"management|specialists?|strategists?|officers?)",
            rf"{_PT_LEAD}{_PT_GENDER}(?: de)? produtos?",
            r"(?:head|director|vp|vice president) of product(?: management)?(?! design)",
        ),
    ),
    *_rules(_F.PRODUCT, 2, (r"product", r"produto", r"produtos")),
    *_rules(
        _F.DESIGN,
        3,
        (
            r"(?:product|ux|ui|ux ui|ui ux|visual|graphic|interaction|web|mobile|brand|motion|"
            r"service|content|communication) designers?",
            r"(?:product|ux|ui|visual|interaction|service|brand) design",
            r"(?:ux|user experience|user) research(?:ers?)?",
            r"ux writers?",
            r"design (?:leads?|managers?|directors?|ops|operations)",
            r"(?:designer|design)(?: [ao])? (?:de produto|grafic[oa]|de interacao|ux|ui|visual|"
            r"de servicos?)",
            r"(?:head|director|vp) of design",
        ),
    ),
    *_rules(
        _F.DESIGN,
        2,
        (r"designers?", r"design", r"ux", r"ui", r"user experience"),
    ),
    *_rules(
        _F.SALES,
        3,
        (
            r"account (?:executives?|managers?|directors?|development)",
            r"(?:sales|vendas) (?:representatives?|reps?|managers?|directors?|executives?|leads?|"
            r"associates?|specialists?|consultants?|operations|enablement|development|analysts?)",
            r"business development(?: representatives?| reps?| managers?| executives?)?",
            r"inside sales",
            r"key accounts?",
            r"partnerships? (?:managers?|leads?|directors?)",
            rf"{_PT_LEAD}{_PT_GENDER}(?: de)? (?:vendas|contas|comercial|negocios)",
            r"vendedor(?:a|es|as)?",
            r"desenvolvimento de negocios",
            r"(?:sdr|bdr)s?",
        ),
    ),
    *_rules(_F.SALES, 2, (r"sales", r"vendas", r"comercial")),
    *_rules(
        _F.MARKETING,
        3,
        (
            r"marketing (?:managers?|specialists?|analysts?|leads?|directors?|coordinators?|"
            r"associates?|executives?|operations|interns?|strategists?)",
            r"(?:product|growth|content|performance|digital|brand|field|lifecycle|partner|events?|"
            r"email|b2b|demand generation) marketing",
            rf"{_PT_LEAD}{_PT_GENDER}(?: de)? marketing",
            r"(?:seo|sem|social media|community|content) (?:specialists?|managers?|analysts?|"
            r"strategists?|writers?|leads?|coordinators?)",
            r"growth marketers?",
            r"demand generation",
            r"copywriters?",
            r"brand (?:managers?|strategists?)",
            r"(?:public relations|pr|communications) (?:managers?|specialists?|leads?|directors?)",
        ),
    ),
    *_rules(
        _F.MARKETING,
        2,
        (
            r"marketing",
            r"seo",
            r"copywriter",
            r"social media",
            r"public relations",
            r"relacoes publicas",
        ),
    ),
    *_rules(
        _F.OPERATIONS,
        3,
        (
            r"(?:business|biz|strategy|strategy and|revenue|go to market|gtm) operations",
            r"bizops",
            rf"{_PT_LEAD}{_PT_GENDER}(?: de)?"
            r" (?:operacoes|logistica|compras|suprimentos|facilities)",
            r"(?:office|facilities|workplace) (?:managers?|coordinators?)",
            r"(?:executive|administrative) assistants?",
            r"assistente administrativ[oa]",
            r"chief of staff",
            r"(?:supply chain|logistics|procurement) (?:managers?|analysts?|specialists?|"
            r"coordinators?)",
        ),
    ),
    *_rules(
        _F.OPERATIONS,
        2,
        (
            r"operations",
            r"operacoes",
            r"logistics",
            r"logistica",
            r"procurement",
            r"supply chain",
            r"facilities",
        ),
    ),
    *_rules(
        _F.PEOPLE,
        3,
        (
            r"people (?:operations|ops|partners?|business partners?|managers?|leads?|analysts?|"
            r"generalists?|team|experience|culture|and culture)",
            r"(?:hr|human resources) (?:business partners?|managers?|generalists?|analysts?|"
            r"specialists?|coordinators?|directors?|operations)",
            r"hrbps?",
            r"(?:technical |tech )?recruiters?",
            r"recruiting (?:coordinators?|managers?|leads?|partners?)",
            r"talent (?:acquisition|partners?|sourcers?|managers?|leads?)",
            r"sourcers?",
            rf"(?:{_PT_LEAD}|business partner){_PT_GENDER}(?: de)? (?:rh|recursos humanos|gente|"
            r"pessoas|recrutamento|departamento pessoal|talentos)",
            r"recrutador(?:a|es|as)?",
            r"(?:compensation|total rewards|benefits) (?:analysts?|managers?|specialists?|"
            r"partners?)",
            r"(?:learning|learning and development|l d) (?:specialists?|managers?|partners?)",
        ),
    ),
    *_rules(
        _F.PEOPLE,
        2,
        (
            r"recruiters?",
            r"recruiting",
            r"recrutamento",
            r"recursos humanos",
            r"rh",
            r"hr",
            r"talent acquisition",
        ),
    ),
    *_rules(
        _F.FINANCE,
        3,
        (
            r"(?:financial|finance|fp a|accounting|tax|treasury|billing|credit|payroll|"
            r"revenue accounting) (?:analysts?|managers?|specialists?|controllers?|directors?|"
            r"leads?|associates?|accountants?|operations|planning)",
            r"(?:financial|finance) controllers?",
            rf"{_PT_LEAD}{_PT_GENDER}(?: de)? (?:financeiro|financeira|financas|contabil|"
            r"contabilidade|fiscal|tributario|controladoria|tesouraria|faturamento|"
            r"planejamento financeiro)",
            r"contador(?:a|es|as)?",
            r"(?:cfo|chief financial officer)",
            r"accounts (?:payable|receivable)",
            r"contas a (?:pagar|receber)",
            r"accountants?",
        ),
    ),
    *_rules(
        _F.FINANCE,
        2,
        (
            r"finance",
            r"financeiro",
            r"financeira",
            r"financas",
            r"accounting",
            r"contabilidade",
            r"contabil",
            r"fiscal",
            r"tax",
            r"treasury",
            r"tesouraria",
            r"controladoria",
            r"fp a",
            r"bookkeepers?",
        ),
    ),
    *_rules(
        _F.LEGAL,
        3,
        (
            r"(?:general|associate|senior|product|employment|commercial|corporate|privacy|legal|"
            r"deputy general|assistant general) counsel",
            r"(?:legal|compliance|privacy|regulatory|contracts?) (?:counsel|advisors?|analysts?|"
            r"managers?|specialists?|directors?|operations|officers?|leads?|associates?)",
            rf"{_PT_LEAD}{_PT_GENDER}(?: de)? (?:juridico|compliance|contratos|regulatorio|"
            r"societario)",
            r"(?:data protection|privacy) officers?",
            r"paralegals?",
        ),
    ),
    *_rules(
        _F.LEGAL,
        2,
        (
            r"legal",
            r"juridico",
            r"juridica",
            r"compliance",
            r"counsel",
            r"lawyers?",
            r"attorneys?",
            r"advogad[oa]s?",
            r"regulatory",
            r"regulatorio",
        ),
    ),
    *_rules(
        _F.SUPPORT,
        3,
        (
            r"(?:customer|technical|tech|product|it|application|client|user) support"
            r"(?: engineers?| specialists?| analysts?| representatives?| reps?| managers?|"
            r" agents?| associates?| leads?| technicians?)?",
            r"support (?:engineers?|specialists?|analysts?|agents?|representatives?|reps?|"
            r"associates?|leads?|managers?|operations|technicians?)",
            r"customer (?:success|service|experience|care|operations)(?: managers?| specialists?|"
            r" representatives?| associates?| agents?| leads?| analysts?)?",
            r"(?:help ?desk|service desk) (?:analysts?|technicians?|specialists?|agents?)",
            rf"(?:{_PT_LEAD}|tecnic[oa]|agente|atendente){_PT_GENDER}(?: de)? (?:suporte|"
            r"atendimento|sucesso do cliente|customer success|help ?desk|service desk)",
            r"atendentes?",
        ),
    ),
    *_rules(
        _F.SUPPORT,
        2,
        (
            r"support",
            r"suporte",
            r"atendimento",
            r"help ?desk",
            r"service desk",
            r"customer success",
            r"sucesso do cliente",
            r"customer service",
            r"customer experience",
            r"customer care",
        ),
    ),
    *_rules(
        _F.OTHER,
        3,
        (
            r"(?:mechanical|civil|electrical|electronics?|chemical|manufacturing|structural|"
            r"industrial|process|mechatronics|biomedical|hardware|asic|fpga|pcb|analog|rf|silicon|"
            r"design verification|field service|maintenance|quality control) (?:design )?"
            r"(?:engineers?|engineering|technicians?)",
            rf"(?:engenheir[oa]s?|engenharia|tecnic[oa]s?){_PT_GENDER}(?: de)? (?:civil|"
            r"mecanic[oa]|eletric[oa]|eletricista|eletronic[oa]|quimic[oa]|producao|industrial|"
            r"mecatronic[oa]|ambiental)",
            r"(?:registered )?nurses?",
            r"enfermeir[oa]s?",
            r"(?:physicians?|pharmacists?|dentists?)",
            r"(?:medic[oa]s?|farmaceutic[oa]s?|dentistas?)",
            r"(?:delivery|truck) drivers?",
            r"motoristas?",
            r"(?:teachers?|professor(?:a|es|as)?)",
            r"(?:cooks?|chefs?|caregivers?|warehouse associates?)",
        ),
    ),
)

#: Description vocabulary, used only between the areas a title matched equally. A
#: description mentions everything a team touches, so it never decides on its own.
DESCRIPTION_TERMS: dict[RoleFamily, tuple[_Rule, ...]] = {
    family: _rules(family, 1, terms)
    for family, terms in {
        _F.SOFTWARE_ENGINEERING: (
            r"software development",
            r"desenvolvimento de software",
            r"apis?",
            r"microservices?",
            r"microsservicos",
            r"code reviews?",
            r"web applications?",
            r"aplicacoes web",
            r"clean code",
        ),
        _F.DATA: (
            r"data pipelines?",
            r"pipelines de dados",
            r"etl",
            r"elt",
            r"data warehouses?",
            r"data lakes?",
            r"spark",
            r"airflow",
            r"dbt",
            r"machine learning",
            r"statistics",
            r"estatistica",
        ),
        _F.INFRASTRUCTURE: (
            r"kubernetes",
            r"k8s",
            r"terraform",
            r"infrastructure as code",
            r"infraestrutura como codigo",
            r"ci cd",
            r"observability",
            r"observabilidade",
            r"on call",
            r"sobreaviso",
        ),
        _F.SECURITY: (
            r"vulnerabilit(?:y|ies)",
            r"vulnerabilidades?",
            r"threats?",
            r"ameacas?",
            r"siem",
            r"incident response",
            r"resposta a incidentes",
            r"penetration testing",
            r"owasp",
            r"iso 27001",
        ),
        _F.QA: (
            r"test automation",
            r"automated tests?",
            r"testes automatizados",
            r"test cases?",
            r"casos de teste",
            r"selenium",
            r"cypress",
            r"regression tests?",
            r"testes de regressao",
        ),
        _F.PRODUCT: (
            r"roadmaps?",
            r"product discovery",
            r"product strategy",
            r"estrategia de produto",
            r"user stories",
            r"historias de usuario",
            r"okrs?",
            r"prioritization",
            r"priorizacao",
        ),
        _F.DESIGN: (
            r"figma",
            r"prototypes?",
            r"prototipos?",
            r"wireframes?",
            r"user research",
            r"pesquisa com usuarios",
            r"design systems?",
            r"usability",
            r"usabilidade",
        ),
        _F.SALES: (
            r"quotas?",
            r"prospecting",
            r"prospeccao",
            r"crm",
            r"salesforce",
            r"closing deals",
            r"sales pipeline",
            r"pipeline de vendas",
            r"negotiation",
            r"negociacao",
        ),
        _F.MARKETING: (
            r"campaigns?",
            r"campanhas?",
            r"seo",
            r"brand awareness",
            r"go to market",
            r"demand generation",
            r"content strategy",
            r"redes sociais",
            r"social media",
        ),
        _F.OPERATIONS: (
            r"process improvement",
            r"melhoria de processos",
            r"logistics",
            r"logistica",
            r"supply chain",
            r"vendors",
            r"fornecedores",
            r"operational efficiency",
            r"eficiencia operacional",
        ),
        _F.PEOPLE: (
            r"recruiting",
            r"recrutamento",
            r"hiring",
            r"onboarding",
            r"employee experience",
            r"performance reviews?",
            r"avaliacao de desempenho",
            r"headcount",
        ),
        _F.FINANCE: (
            r"financial statements?",
            r"demonstracoes financeiras",
            r"budgets?",
            r"orcamentos?",
            r"forecasts?",
            r"invoices?",
            r"notas fiscais",
            r"reconciliations?",
            r"conciliacao",
        ),
        _F.LEGAL: (
            r"contracts",
            r"contratos",
            r"lgpd",
            r"gdpr",
            r"litigation",
            r"litigio",
            r"legal advice",
        ),
        _F.SUPPORT: (
            r"tickets?",
            r"chamados?",
            r"zendesk",
            r"troubleshooting",
            r"customer issues",
            r"atendimento ao cliente",
            r"customer inquiries",
        ),
    }.items()
}


def _top_matches(rules: Sequence[_Rule], text: str) -> list[tuple[_Rule, str]]:
    """The matches at the highest specificity present in `text`."""
    matches = [
        (rule, found.group(0))
        for rule in rules
        if (found := rule.pattern.search(text)) is not None
    ]
    if not matches:
        return []
    top = max(rule.specificity for rule, _ in matches)
    return [(rule, term) for rule, term in matches if rule.specificity == top]


def _department_decision(
    departments: Sequence[str],
) -> tuple[_Rule, str, str] | None:
    """The first department (in the order the ATS gave them) that names one area.

    The order matters: collectors list the department before the team, and a team called
    "Customer Support Tools" inside Engineering is still an engineering team.
    """
    for department in departments:
        top = _top_matches(DEPARTMENT_RULES, normalize_role_text(department))
        if len({rule.family for rule, _ in top}) == 1:
            rule, term = top[0]
            return rule, term, department
    return None


def _description_winner(
    families: set[RoleFamily], description: str | None
) -> tuple[RoleFamily, str] | None:
    text = normalize_role_text(description)
    if not text:
        return None
    hits: dict[RoleFamily, list[str]] = {}
    for family in families:
        terms = [
            found.group(0)
            for rule in DESCRIPTION_TERMS.get(family, ())
            if (found := rule.pattern.search(text)) is not None
        ]
        if terms:
            hits[family] = terms
    if not hits:
        return None
    ranked = sorted(hits.items(), key=lambda item: len(item[1]), reverse=True)
    if len(ranked) > 1 and len(ranked[0][1]) == len(ranked[1][1]):
        return None
    family, terms = ranked[0]
    return family, ", ".join(sorted(terms))


def classify_role_family(
    *,
    title: str | None,
    departments: Sequence[str] = (),
    description: str | None = None,
) -> RoleFamilyDecision:
    """Classify one posting; UNKNOWN whenever the evidence does not name a single area."""
    title_top = _top_matches(TITLE_RULES, normalize_role_text(title))
    title_families = {rule.family for rule, _ in title_top}
    title_family = next(iter(title_families)) if len(title_families) == 1 else None
    title_terms = ", ".join(sorted({term for _, term in title_top}))

    department = _department_decision(departments)
    if department is not None:
        rule, term, name = department
        if title_family is not None and title_family in rule.refinable:
            return RoleFamilyDecision(
                role_family=title_family,
                evidence={
                    "rule": "department_refined_by_title",
                    "term": title_terms,
                    "origin": "title",
                    "department": name,
                    "department_family": rule.family.value,
                },
            )
        return RoleFamilyDecision(
            role_family=rule.family,
            evidence={
                "rule": "department",
                "term": term,
                "origin": "department",
                "department": name,
            },
        )

    if not title_top:
        return RoleFamilyDecision(
            role_family=RoleFamily.UNKNOWN,
            evidence={"rule": "no_match", "term": "", "origin": "none"},
        )
    if RoleFamily.UNKNOWN in title_families:
        return RoleFamilyDecision(
            role_family=RoleFamily.UNKNOWN,
            evidence={"rule": "boundary_title", "term": title_terms, "origin": "title"},
        )
    if title_family is not None:
        return RoleFamilyDecision(
            role_family=title_family,
            evidence={"rule": "title", "term": title_terms, "origin": "title"},
        )

    tied = ",".join(sorted(family.value for family in title_families))
    winner = _description_winner(title_families, description)
    if winner is not None:
        family, terms = winner
        return RoleFamilyDecision(
            role_family=family,
            evidence={
                "rule": "description_tiebreak",
                "term": terms,
                "origin": "description",
                "title_terms": title_terms,
                "tied": tied,
            },
        )
    return RoleFamilyDecision(
        role_family=RoleFamily.UNKNOWN,
        evidence={"rule": "title_tie", "term": title_terms, "origin": "title", "tied": tied},
    )


def departments_from_metadata(metadata: Mapping[str, Any]) -> tuple[str, ...]:
    """Department names an ATS declared, department before team.

    Ashby sends `department` and `team`, Greenhouse a `departments` list of objects, Lever
    `categories.department` and `categories.team`, and Remotive a board `category`. A
    manual intake may carry `department`. Anything else is not a department.
    """
    names: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            names.append(value.strip())

    add(metadata.get("department"))
    departments = metadata.get("departments")
    if isinstance(departments, (list, tuple)):
        for entry in departments:
            add(entry.get("name") if isinstance(entry, Mapping) else entry)
    categories = metadata.get("categories")
    if isinstance(categories, Mapping):
        add(categories.get("department"))
    add(metadata.get("category"))
    add(metadata.get("team"))
    if isinstance(categories, Mapping):
        add(categories.get("team"))
    return tuple(dict.fromkeys(names))


__all__ = [
    "DEPARTMENT_RULES",
    "DESCRIPTION_TERMS",
    "PROFILE_ROLE_FAMILIES",
    "ROLE_FAMILY_VERSION",
    "TITLE_RULES",
    "RoleFamily",
    "RoleFamilyDecision",
    "classify_role_family",
    "departments_from_metadata",
    "normalize_role_text",
]
