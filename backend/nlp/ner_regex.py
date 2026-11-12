"""Camada de regex do NER clínico: intensidade, frequência, tempo, doses, pontos de acupuntura e padrões de MTC.

Cada regra devolve entidades com ``start``/``end`` (caracteres no texto normalizado), ``label``, ``attrs``
e o nome da regra (exibido no Laboratório ao passar o mouse sobre a entidade).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from . import resources
from .form_schema import fold

FLAGS = re.I | re.U
MONTHS = "janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
TIME_UNITS = r"dias?|semanas?|meses|m[eê]s|anos?|horas?"

QUAL_INTENSITY = {
    "leve": 2, "fraca": 2, "suportável": 3, "suportavel": 3, "moderada": 5, "forte": 7, "intensa": 8, "severa": 8,
    "aguda": 8, "insuportável": 10, "insuportavel": 10, "terrível": 9, "terrivel": 9, "horrível": 9, "horrivel": 9,
    "lancinante": 9,
}


def _f(s: str | None) -> float | None:
    return float(s.replace(",", ".")) if s else None


def _unit(u: str) -> str:
    u = fold(u)
    if u.startswith("mes"):
        return "meses"
    for base, canon in (("ano", "anos"), ("semana", "semanas"), ("dia", "dias"), ("hora", "horas"), ("minuto", "minutos"),
                        ("cigarro", "cigarros"), ("maco", "maços"), ("copo", "copos"), ("lata", "latas"), ("dose", "doses"),
                        ("taca", "taças"), ("cerveja", "cervejas"), ("garrafa", "garrafas"), ("cafe", "cafés"),
                        ("litro", "litros"), ("vez", "vezes"), ("sess", "sessões"), ("comprimido", "comprimidos"),
                        ("refei", "refeições"), ("xicara", "xícaras")):
        if u.startswith(base):
            return canon
    return u


@dataclass
class Rule:
    name: str
    label: str
    pattern: re.Pattern
    build: Callable[[re.Match], dict | None]
    span_group: str | None = None
    conf: float = 0.95


RULES: list[Rule] = []


def rule(name: str, label: str, pattern: str, span_group: str | None = None, conf: float = 0.95):
    rx = re.compile(pattern, FLAGS)

    def deco(fn):
        RULES.append(Rule(name, label, rx, fn, span_group, conf))
        return fn
    return deco


# ---------------------------------------------------------------- Intensidade
@rule("intensidade_nota", "INTENSIDADE",
      r"(?<!\w)(?:nota|eva|intensidade|n[ií]vel|escala)\s*(?:de\s+)?(?P<v>\d{1,2})(?:\s*(?:/|de)\s*10)?(?!\d)(?!\s*(?:a|at[eé]|-)\s*\d)")
def _int_nota(m):
    v = int(m.group("v"))
    return {"value": v, "kind": "numeric"} if 0 <= v <= 10 else None


@rule("intensidade_x_de_10", "INTENSIDADE", r"(?<![\d/.,])(?P<v>\d{1,2})\s*(?:/|de|em)\s*10(?!\d)")
def _int_de10(m):
    v = int(m.group("v"))
    return {"value": v, "kind": "numeric"} if 0 <= v <= 10 else None


@rule("intensidade_dor_numero", "INTENSIDADE",
      r"(?<!\w)dor(?:es)?\s+(?:de\s+)?(?:nota\s+)?(?P<span>(?P<v>\d{1,2}))(?!\d)(?!\s*(?:dias|anos|meses|semanas|vezes|horas|minutos|%|mg|kg|a\s*\d))",
      span_group="span")
def _int_dor_n(m):
    v = int(m.group("v"))
    return {"value": v, "kind": "numeric"} if 0 <= v <= 10 else None


@rule("intensidade_qualitativa", "INTENSIDADE",
      r"(?<!\w)dor(?:es)?\s+(?P<span>(?:muito\s+|bem\s+|bastante\s+|extremamente\s+)?(?P<q>leve|fraca|suport[aá]vel|moderada|forte|intensa|severa|insuport[aá]vel|terr[ií]vel|horr[ií]vel|lancinante|aguda))(?!\w)",
      span_group="span", conf=0.6)
def _int_qual(m):
    q = m.group("q").lower()
    base = QUAL_INTENSITY.get(q, QUAL_INTENSITY.get(fold(q), 5))
    if re.match(r"(?:muito|bastante|extremamente)", m.group("span"), re.I):
        base = min(10, base + 1)
    return {"value": base, "kind": "qualitative", "word": q}


# ---------------------------------------------------------------- Frequência / quantidade
_FREQ_UNITS = r"cigarros?|ma[cç]os?|copos?|latas?|doses?|ta[cç]as?|cervejas?|garrafas?|caf[eé]s?|litros?|vezes|vez|x|sess[oõ]es|comprimidos?|horas?|refei[cç][oõ]es|x[ií]caras?"


@rule("frequencia_qtd_periodo", "FREQUENCIA",
      rf"(?<![\w,.])(?P<qty>\d+(?:[.,]\d+)?)\s*(?P<u>{_FREQ_UNITS})(?:\s+de\s+(?P<obj>[a-zçãõáéíóúâêô]+))?\s*(?:por|ao|no|na|a|de)\s+(?P<per>dia|semana|m[eê]s|ano|noite)(?!\w)")
def _freq(m):
    u = m.group("u").lower()
    u = "vezes" if u in ("x", "vez", "vezes") else _unit(u)
    obj = (m.group("obj") or "").lower()
    return {"qty": _f(m.group("qty")), "unit": u, "obj": obj, "per": fold(m.group("per")).replace("mes", "mês"),
            "kind": "qty_per"}


@rule("quantidade_litros", "FREQUENCIA",
      r"(?<![\w,.])(?P<qty>\d+(?:[.,]\d+)?)\s*(?P<u>litros?|l)(?:\s+de\s+(?P<obj>[a-zçãõáéíóúâêô]+))?(?!\w)", conf=0.85)
def _litros(m):
    return {"qty": _f(m.group("qty")), "unit": "litros", "obj": (m.group("obj") or "").lower(), "per": "", "kind": "qty"}


@rule("quantidade_copos", "FREQUENCIA",
      r"(?<![\w,.])(?P<qty>\d+)\s*(?P<u>copos?)\s+de\s+(?P<obj>[a-zçãõáéíóúâêô]+)(?!\w)", conf=0.8)
def _copos(m):
    return {"qty": _f(m.group("qty")), "unit": "copos", "obj": m.group("obj").lower(), "per": "", "kind": "qty"}


@rule("frequencia_qualitativa", "FREQUENCIA",
      r"(?<!\w)(?P<f>todos\s+os\s+dias|todo\s+dia|diariamente|toda\s+(?:semana|noite|manh[ãa])|semanalmente|todo\s+m[eê]s|"
      r"(?:nos\s+|aos\s+)?(?:finais?|fins?)\s+de\s+semana|raramente|ocasionalmente|socialmente|frequentemente)(?!\w)", conf=0.8)
def _freq_q(m):
    return {"word": fold(m.group("f")), "kind": "qual"}


@rule("dose", "DOSE", r"(?<![\w,.])(?P<qty>\d+(?:[.,]\d+)?)\s*(?P<u>miligramas?|mg|mcg|microgramas?|mililitros?|ml|ui|gotas|gramas?|g)(?!\w)", conf=0.9)
def _dose(m):
    u = m.group("u").lower()
    u = {"miligrama": "mg", "miligramas": "mg", "micrograma": "mcg", "microgramas": "mcg", "mililitro": "ml", "mililitros": "ml",
         "grama": "g", "gramas": "g"}.get(u, u)
    return {"qty": _f(m.group("qty")), "unit": u}


# ---------------------------------------------------------------- Tempo
@rule("tempo_ha", "TEMPO",
      rf"(?<!\w)(?:h[aá]|faz|fazem|fazia|tem|havia)\s+(?:(?P<q>mais\s+ou\s+menos|mais\s+de|cerca\s+de|quase|aproximadamente|uns|umas)\s+)?(?P<n>\d+(?:[.,]\d+)?)\s*(?P<u>{TIME_UNITS})(?!\w)")
def _t_ha(m):
    return {"kind": "ago", "qty": _f(m.group("n")), "unit": _unit(m.group("u")), "approx": (m.group("q") or "").lower() or None}


@rule("tempo_atras", "TEMPO", rf"(?<!\w)(?P<n>\d+(?:[.,]\d+)?)\s*(?P<u>{TIME_UNITS})\s+atr[aá]s(?!\w)")
def _t_atras(m):
    return {"kind": "ago", "qty": _f(m.group("n")), "unit": _unit(m.group("u")), "approx": None}


@rule("tempo_desde_ano", "TEMPO", r"(?<!\w)desde\s+(?:o\s+ano\s+de\s+)?(?P<y>(?:19|20)\d{2})(?!\d)")
def _t_desde_ano(m):
    return {"kind": "since", "year": int(m.group("y")), "unit": "anos"}


@rule("tempo_em_ano", "TEMPO", r"(?<!\w)em\s+(?P<y>(?:19|20)\d{2})(?!\d)", conf=0.8)
def _t_em_ano(m):
    return {"kind": "year", "year": int(m.group("y"))}


@rule("tempo_desde_mes", "TEMPO", rf"(?<!\w)desde\s+(?P<m>{MONTHS})(?:\s+de\s+(?P<y>(?:19|20)\d{{2}}))?(?!\w)")
def _t_desde_mes(m):
    return {"kind": "since", "month": m.group("m").lower(), "year": int(m.group("y")) if m.group("y") else None}


@rule("tempo_desde_fase", "TEMPO",
      r"(?<!\w)desde\s+(?:que\s+(?:eu\s+)?(?:era|fui|tinha)\s+)?(?:a\s+|o\s+)?(?P<p>crian[cç]a|inf[aâ]ncia|adolesc[eê]ncia|pequen[oa]|jovem|sempre|nascimento|parto|gravidez|cirurgia|acidente|queda|ontem|hoje|semana\s+passada|m[eê]s\s+passado|ano\s+passado)(?!\w)")
def _t_desde_fase(m):
    return {"kind": "since", "phrase": re.sub(r"\s+", " ", m.group("p").lower())}


@rule("tempo_duracao", "TEMPO",
      rf"(?<!\w)(?:por|durante)\s+(?:(?P<q>mais\s+ou\s+menos|mais\s+de|cerca\s+de|uns|umas|quase|aproximadamente)\s+)?(?P<n>\d+(?:[.,]\d+)?)\s*(?P<u>{TIME_UNITS})(?!\w)")
def _t_dur(m):
    return {"kind": "duration", "qty": _f(m.group("n")), "unit": _unit(m.group("u")), "approx": (m.group("q") or "").lower() or None}


@rule("tempo_futuro", "TEMPO",
      r"(?<!\w)(?:daqui\s+a|em|dentro\s+de|retorno\s+em|volte\s+em|volta\s+em)\s+(?P<n>\d+)\s*(?P<u>dias?|semanas?|meses|m[eê]s)(?!\w)", conf=0.85)
def _t_fut(m):
    return {"kind": "future", "qty": _f(m.group("n")), "unit": _unit(m.group("u"))}


@rule("tempo_futuro_frase", "TEMPO",
      r"(?<!\w)(?:semana\s+que\s+vem|pr[oó]xima\s+semana|pr[oó]xima\s+sess[aã]o|pr[oó]ximo\s+m[eê]s|amanh[ãa])(?!\w)", conf=0.85)
def _t_fut_f(m):
    return {"kind": "future", "phrase": re.sub(r"\s+", " ", m.group(0).lower())}


@rule("tempo_minutos", "TEMPO", r"(?<![\w,.])(?P<n>\d+)\s*(?P<u>minutos?|min)(?!\w)", conf=0.9)
def _t_min(m):
    return {"kind": "minutes", "qty": _f(m.group("n")), "unit": "minutos"}


@rule("tempo_bare", "TEMPO", r"(?<![\w,.])(?P<n>\d+(?:[.,]\d+)?)\s*(?P<u>anos?|meses|m[eê]s|semanas?|dias?)(?!\w)(?!\s*atr[aá]s)", conf=0.6)
def _t_bare(m):
    return {"kind": "bare", "qty": _f(m.group("n")), "unit": _unit(m.group("u")), "approx": None}


# ---------------------------------------------------------------- Pontos de acupuntura
_POINT_RX = re.compile(r"(?<![\w-])(?P<pfx>VB|IG|BP|PC|VC|VG|TA|ID|CS|E|F|R|B|P|C)\s?-?\s?(?P<n>\d{1,2})(?!\w)", re.U)
_BAD_BEFORE = re.compile(r"(?:vitamina|hepatite|tipo|grupo|fator|classe|complexo|ctrl|cn|capítulo|capitulo|ômega|omega|sala|andar)\s*$", re.I)
_BAD_AFTER = re.compile(r"\s*(?:%|mg|mcg|kg|ml|anos?|dias?|horas?|minutos?|meses|m[eê]s|semanas?|vezes|cigarros?|litros?|copos?|de\s+10|/)", re.I)


def point_entities(text: str) -> list[dict]:
    res = resources.get_resources()["points"]["meridianos"]
    mer_alias = {"CS": "PC"}
    out = []
    for m in _POINT_RX.finditer(text):
        pfx, n = m.group("pfx"), int(m.group("n"))
        raw_pfx = text[m.start("pfx"):m.end("pfx")]
        key = mer_alias.get(pfx.upper(), pfx.upper())
        if key not in res or not (1 <= n <= res[key]["n"]):
            continue
        before = text[max(0, m.start() - 14):m.start()]
        if _BAD_BEFORE.search(before) or _BAD_AFTER.match(text[m.end():m.end() + 12]):
            continue
        has_ponto_cue = bool(re.search(r"pontos?\s*(?:de\s*)?$", before, re.I))
        gap = text[m.end("pfx"):m.start("n")]
        if len(pfx) == 1 and not (has_ponto_cue or (raw_pfx.isupper() and gap == "")):
            continue  # "E 36"/"e36" sem a palavra "ponto" é ambíguo (conjunção "e"); "E36" colado é aceito
        code = f"{key}{n}"
        out.append({"start": m.start(), "end": m.end(), "label": "PONTO", "canonical": code, "source": "regex",
                    "rule": "regex:ponto_acupuntura", "conf": 0.95,
                    "attrs": {"code": code, "meridiano": res[key]["nome"]}})
    return out


# ---------------------------------------------------------------- Padrões de MTC
_ORG = r"f[ií]gado|ba[cç]o|rins?|cora[cç][aã]o|pulm[aã]o|est[oô]mago|bexiga|ves[ií]cula(?:\s+biliar)?|intestino\s+(?:grosso|delgado)"
_PATTERN_RX = [
    re.compile(rf"(?<!\w)(?:defici[eê]ncia|estagna[cç][aã]o|estase|excesso|ascens[aã]o|invas[aã]o|ac[uú]mulo|obstru[cç][aã]o|vazio|calor|fogo|frio|vento|umidade|fleuma)\s+(?:de|do|da|dos|das|no|na)\s+(?:qi|yin|yang|xue|sangue|jing|shen|{_ORG}|umidade|fleuma|calor|frio|vento)(?:\s+(?:do|da|de)\s+(?:{_ORG}|qi|yang|yin))?(?!\w)", FLAGS),
    re.compile(r"(?<!\w)(?:umidade-calor|calor-umidade|vento-frio|vento-calor|frio-umidade|fleuma-umidade|s[ií]ndrome\s+bi|obstru[cç][aã]o\s+bi)(?!\w)", FLAGS),
    re.compile(r"(?<!\w)desarmonia\s+entre\s+(?:o\s+)?\w+\s+e\s+(?:o\s+)?\w+(?!\w)", FLAGS),
]


def pattern_entities(text: str) -> list[dict]:
    out = []
    for rx in _PATTERN_RX:
        for m in rx.finditer(text):
            out.append({"start": m.start(), "end": m.end(), "label": "MTC", "canonical": m.group(0)[:1].upper() + m.group(0)[1:],
                        "source": "regex", "rule": "regex:padrao_mtc", "conf": 0.85, "attrs": {"categoria": "padrao"}})
    return out


# ---------------------------------------------------------------- Execução
def regex_entities(text: str) -> list[dict]:
    out: list[dict] = []
    for r in RULES:
        for m in r.pattern.finditer(text):
            attrs = r.build(m)
            if attrs is None:
                continue
            gs = r.span_group
            s, e = (m.start(gs), m.end(gs)) if gs and m.group(gs) is not None else (m.start(), m.end())
            out.append({"start": s, "end": e, "label": r.label, "canonical": text[s:e], "source": "regex",
                        "rule": f"regex:{r.name}", "conf": r.conf, "attrs": attrs})
    out += point_entities(text)
    out += pattern_entities(text)
    return out


def rule_catalog() -> list[dict]:
    cat = [{"name": r.name, "label": r.label, "pattern": r.pattern.pattern} for r in RULES]
    cat.append({"name": "ponto_acupuntura", "label": "PONTO", "pattern": _POINT_RX.pattern + " (validado pelo catálogo de meridianos)"})
    cat.append({"name": "padrao_mtc", "label": "MTC", "pattern": "; ".join(r.pattern for r in _PATTERN_RX)[:300]})
    return cat
