"""Conversão de números por extenso (pt-BR) para dígitos.

"dez cigarros" → "10 cigarros"; "uns três meses" → "3 meses"; "dois mil e vinte" → "2020";
"um litro e meio" → "1,5 litro"; "meia hora" → "30 minutos".
"um/uma" só viram dígito diante de unidade de medida (para não transformar o artigo em número).
"""
from __future__ import annotations

import re
import unicodedata

UNITS = {
    "zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
    "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14, "quatorze": 14,
    "quinze": 15, "dezesseis": 16, "dezasseis": 16, "dezessete": 17, "dezassete": 17, "dezoito": 18,
    "dezenove": 19, "dezanove": 19,
}
TENS = {"vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70,
        "oitenta": 80, "noventa": 90}
HUNDREDS = {"cem": 100, "cento": 100, "duzentos": 200, "duzentas": 200, "trezentos": 300, "trezentas": 300,
            "quatrocentos": 400, "quatrocentas": 400, "quinhentos": 500, "quinhentas": 500,
            "seiscentos": 600, "seiscentas": 600, "setecentos": 700, "setecentas": 700,
            "oitocentos": 800, "oitocentas": 800, "novecentos": 900, "novecentas": 900}

# Palavras que, depois de "um/uma", indicam quantidade (e não artigo).
QTY_UNITS = {
    "cigarro", "cigarros", "maço", "maços", "ano", "anos", "mês", "meses", "semana", "semanas", "dia", "dias",
    "hora", "horas", "vez", "vezes", "litro", "litros", "copo", "copos", "taça", "taças", "lata", "latas", "dose",
    "doses", "comprimido", "comprimidos", "minuto", "minutos", "ponto", "pontos", "sessão", "sessões", "garrafa",
    "garrafas", "xícara", "xícaras", "cerveja", "cervejas", "café", "cafés", "refeição", "refeições", "quilo",
    "quilos", "kg", "metro", "metros", "grau", "graus",
}

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ]+|\d+(?:[.,]\d+)?|[^\sA-Za-zÀ-ÿ\d]|\s+")


def _fold(w: str) -> str:
    w = unicodedata.normalize("NFD", w.lower())
    return "".join(c for c in w if unicodedata.category(c) != "Mn")


def _is_word(t: str) -> bool:
    return bool(re.match(r"[A-Za-zÀ-ÿ]", t))


def _kind(w: str) -> str | None:
    f = _fold(w)
    if f in UNITS:
        return "unit"
    if f in TENS:
        return "ten"
    if f in HUNDREDS:
        return "hundred"
    if f == "mil":
        return "mil"
    return None


def _value(w: str) -> int:
    f = _fold(w)
    if f in UNITS:
        return UNITS[f]
    if f in TENS:
        return TENS[f]
    return HUNDREDS.get(f, 1000)


def parse_number_run(words: list[str]) -> tuple[int, int]:
    """Consome o maior prefixo gramatical de ``words`` (o conector 'e' é uma palavra).
    Retorna (valor, nº de palavras consumidas); 0 se a primeira palavra não for número."""
    total = 0
    current = 0
    consumed = 0
    last: str | None = None
    i = 0
    while i < len(words):
        k = _kind(words[i])
        if k is None:
            break
        v = _value(words[i])
        if k == "hundred":
            if last not in (None, "mil"):
                break
            current += v
        elif k == "ten":
            if last not in (None, "mil", "hundred", "hundred_e"):
                break
            current += v
        elif k == "unit":
            if last not in (None, "mil", "hundred", "hundred_e", "ten", "ten_e"):
                break
            if last in ("ten", "ten_e") and v >= 10:
                break
            current += v
        else:  # mil
            if last == "mil":
                break
            current = (current or 1) * 1000
            total += current
            current = 0
        last = k
        consumed = i + 1
        # conector "e" entre duas partes do mesmo número ("vinte e cinco", "cento e dez", "mil e vinte")
        if i + 2 < len(words) and words[i + 1].lower() == "e":
            nk = _kind(words[i + 2])
            if nk is not None and (
                (k in ("hundred", "mil") and nk in ("ten", "unit"))
                or (k == "hundred" and nk == "ten")
                or (k == "ten" and nk == "unit")
            ):
                last = k if k == "mil" else k + "_e"
                i += 2
                continue
        i += 1
    return total + current, consumed


def words_to_digits(text: str) -> str:
    toks = _TOKEN_RE.findall(text)
    out: list[str] = []
    n = len(toks)
    i = 0
    while i < n:
        t = toks[i]
        if not _is_word(t) or _kind(t) is None:
            out.append(t)
            i += 1
            continue
        words: list[str] = []
        idxs: list[int] = []
        j = i
        while j < n and len(words) < 14:
            if toks[j].isspace():
                j += 1
            elif _is_word(toks[j]):
                words.append(toks[j])
                idxs.append(j)
                j += 1
            else:
                break
        value, consumed = parse_number_run(words)
        if consumed == 0:
            out.append(t)
            i += 1
            continue
        end_tok = idxs[consumed - 1]
        if consumed == 1 and _fold(t) in ("um", "uma"):
            k = end_tok + 1
            while k < n and toks[k].isspace():
                k += 1
            if not (k < n and toks[k].lower() in QTY_UNITS):
                out.append(t)
                i += 1
                continue
        # descarta "uns/umas" imediatamente antes do número
        k = len(out) - 1
        while k >= 0 and out[k].isspace():
            k -= 1
        if k >= 0 and _fold(out[k]) in ("uns", "umas"):
            del out[k:]
            if out and not out[-1].isspace():
                out.append(" ")
        out.append(str(value))
        i = end_tok + 1
    return _fractions(_drop_uns("".join(out)))


def _drop_uns(text: str) -> str:
    # "uns 10 cigarros" (já em dígitos) → "10 cigarros"
    return re.sub(r"\b(?:[Uu]ns|[Uu]mas)\s+(?=\d)", "", text)


def _fractions(text: str) -> str:
    text = re.sub(r"\bmeia\s+hora\b", "30 minutos", text, flags=re.I)
    text = re.sub(r"\bmeio\s+(litro|copo|maço|quilo|kg)\b", r"0,5 \1", text, flags=re.I)
    text = re.sub(r"\bmeia\s+(xícara|garrafa|dose|taça|lata)\b", r"0,5 \1", text, flags=re.I)
    text = re.sub(r"\b(\d+)\s+(horas?|anos?|meses|mês|litros?|copos?|maços?|semanas?|dias?|quilos?)\s+e\s+meia?o?\b",
                  lambda m: f"{m.group(1)},5 {m.group(2)}", text, flags=re.I)
    return text
