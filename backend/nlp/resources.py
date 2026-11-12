"""Carregamento (e recarga a quente) dos recursos linguísticos editáveis em JSON."""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from .form_schema import fold

NLP_DIR = Path(__file__).resolve().parent
RES_DIR = NLP_DIR / "resources"
DICT_DIR = RES_DIR / "dictionaries"
GOLD_DIR = NLP_DIR / "gold"

# Arquivos de configuração (além dos dicionários de entidades)
CONFIG_FILES = {
    "negation_triggers": RES_DIR / "negation_triggers.json",
    "stopwords_custom": RES_DIR / "stopwords_custom.json",
    "normalization": RES_DIR / "normalization.json",
    "points": RES_DIR / "points.json",
}

_lock = threading.RLock()
_cache: dict[str, Any] = {}
_version = 0


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_contextual(entry: dict) -> bool:
    return bool(entry.get("attrs", {}).get("contextual"))


def load_all() -> dict[str, Any]:
    dicts = {p.stem: _read(p) for p in sorted(DICT_DIR.glob("*.json"))}
    cfg = {name: _read(p) for name, p in CONFIG_FILES.items()}
    return {"dictionaries": dicts, **cfg}


def get_resources() -> dict[str, Any]:
    with _lock:
        if not _cache:
            _cache.update(load_all())
        return _cache


def resources_version() -> int:
    return _version


def reload_resources() -> dict[str, Any]:
    global _version
    with _lock:
        _cache.clear()
        _cache.update(load_all())
        _version += 1
        return _cache


def list_resource_files() -> list[dict]:
    out = []
    for p in sorted(DICT_DIR.glob("*.json")):
        d = _read(p)
        out.append({"name": p.stem, "kind": "dictionary", "label": d.get("label"), "entries": len(d.get("entries", [])),
                    "description": d.get("description", "")})
    for name, p in CONFIG_FILES.items():
        out.append({"name": name, "kind": "config", "label": None, "entries": None,
                    "description": _read(p).get("_doc", "")})
    return out


def get_resource_file(name: str) -> Any:
    res = get_resources()
    if name in res["dictionaries"]:
        return res["dictionaries"][name]
    if name in CONFIG_FILES:
        return res[name]
    raise KeyError(name)


def _is_str_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _num(v: Any, lo: float, hi: float) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi


def validate_resource(name: str, data: Any) -> None:
    """Valida o FORMATO de um recurso antes de gravar; um arquivo malformado quebraria o pipeline para todos. Levanta ValueError."""
    import re

    if not isinstance(data, dict):
        raise ValueError("O conteúdo deve ser um objeto JSON.")
    if name == "negation_triggers":
        if "window" in data and not _num(data["window"], 1, 30):
            raise ValueError("'window' deve ser um número entre 1 e 30.")
        for kind in ("pre", "post", "pseudo", "termination", "uncertainty", "former", "former_post"):
            rows = data.get(kind, [])
            if not isinstance(rows, list):
                raise ValueError(f"'{kind}' deve ser uma lista.")
            for r in rows:
                if not isinstance(r, dict) or not isinstance(r.get("text"), str) or not r["text"].strip():
                    raise ValueError(f"Cada gatilho de '{kind}' precisa de 'text' (texto não vazio).")
                if "window" in r and not _num(r["window"], 1, 30):
                    raise ValueError(f"'window' de '{r['text']}' deve ser um número entre 1 e 30.")
                if "factor" in r and not _num(r["factor"], 0, 1):
                    raise ValueError(f"'factor' de '{r['text']}' deve estar entre 0 e 1.")
    elif name == "stopwords_custom":
        pres = data.get("preserve", {})
        if not isinstance(pres, dict) or not all(_is_str_list(v) for v in pres.values()):
            raise ValueError("'preserve' deve ser um objeto {categoria: [palavras]}.")
        if not _is_str_list(data.get("extra", [])):
            raise ValueError("'extra' deve ser uma lista de palavras.")
    elif name == "normalization":
        for key in ("abbreviations", "case_sensitive_abbreviations"):
            v = data.get(key, {})
            if not isinstance(v, dict) or not all(isinstance(k, str) and k and isinstance(x, str) for k, x in v.items()):
                raise ValueError(f"'{key}' deve ser um objeto {{abreviação: expansão}} com textos.")
        for key in ("ellipsis_hesitations", "interjections", "affirmatives_kept_as_sim", "filler_regex", "leading_markers", "stutter_words"):
            if not _is_str_list(data.get(key, [])):
                raise ValueError(f"'{key}' deve ser uma lista de textos.")
        for rx in data.get("filler_regex", []):
            try:
                re.compile(rx)
            except re.error as e:
                raise ValueError(f"Expressão regular inválida em 'filler_regex': {rx!r} ({e})") from e
    elif name == "points":
        mer = data.get("meridianos")
        if not isinstance(mer, dict) or not all(isinstance(v, dict) and isinstance(v.get("n"), int) and isinstance(v.get("nome"), str) for v in mer.values()):
            raise ValueError("'meridianos' deve ser {código: {nome, n}}.")
        pts = data.get("pontos")
        if not isinstance(pts, list) or not all(isinstance(p, dict) and isinstance(p.get("code"), str) and isinstance(p.get("nome"), str) for p in pts):
            raise ValueError("'pontos' deve ser uma lista de {code, nome}.")
    elif (DICT_DIR / f"{name}.json").exists():
        if not isinstance(data.get("label"), str) or not data["label"].strip():
            raise ValueError("Dicionário precisa de 'label' (texto).")
        entries = data.get("entries")
        if not isinstance(entries, list):
            raise ValueError("'entries' deve ser uma lista.")
        for e in entries:
            if not isinstance(e, dict) or not isinstance(e.get("canonical"), str) or not e["canonical"].strip():
                raise ValueError("Cada entrada precisa de 'canonical' (texto não vazio).")
            if not _is_str_list(e.get("variants", [])):
                raise ValueError(f"'variants' de '{e['canonical']}' deve ser uma lista de textos.")
            if not isinstance(e.get("attrs", {}), dict):
                raise ValueError(f"'attrs' de '{e['canonical']}' deve ser um objeto.")
    else:
        raise KeyError(name)


def save_resource_file(name: str, data: Any) -> None:
    if name in CONFIG_FILES:
        path = CONFIG_FILES[name]
    elif re.fullmatch(r"[a-z0-9_]+", name) and (DICT_DIR / f"{name}.json").exists():
        path = DICT_DIR / f"{name}.json"
    else:
        raise KeyError(name)
    validate_resource(name, data)
    previous = path.read_bytes()
    path.write_bytes((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    try:
        reload_resources()
        build_ruler_patterns()  # prova de fogo: o recurso novo precisa gerar padrões sem erro
        from .stages.s09_negation import load_triggers
        load_triggers()
    except Exception as e:  # noqa: BLE001 — qualquer falha desfaz a gravação
        path.write_bytes(previous)
        reload_resources()
        raise ValueError(f"O recurso foi recusado porque quebraria o pipeline: {type(e).__name__}: {e}") from e


# ---------------------------------------------------------------------------
# Variantes morfológicas (plural e sem acento) usadas pelo EntityRuler
# ---------------------------------------------------------------------------
def _plurals(word: str) -> set[str]:
    w = word.lower()
    out = {w}
    if w.endswith("ão"):
        out |= {w[:-2] + "ões", w[:-2] + "ães", w + "s"}
    elif w.endswith(("r", "z")):
        out.add(w + "es")
    elif w.endswith("al"):
        out.add(w[:-2] + "ais")
    elif w.endswith(("m",)):
        out.add(w[:-1] + "ns")
    elif w.endswith("s"):
        pass
    elif w[-1:] in "aeiouáéíóúâêôãõ":
        out.add(w + "s")
    return out


def expand_variants(term: str) -> set[str]:
    """Gera formas de superfície: singular/plural (última palavra) e com/sem acentos."""
    words = term.strip().split()
    if not words:
        return set()
    forms: set[str] = set()
    last_forms = _plurals(words[-1]) if len(words) == 1 or len(words[-1]) > 3 else {words[-1].lower()}
    head = " ".join(w.lower() for w in words[:-1])
    for lf in last_forms:
        forms.add((head + " " + lf).strip())
    forms |= {fold(f) for f in list(forms)}
    return {f for f in forms if f}


def build_ruler_patterns() -> tuple[list[dict], dict[str, dict]]:
    """Retorna (padrões do EntityRuler, índice id→{label, canonical, attrs, dict})."""
    res = get_resources()
    patterns: list[dict] = []
    index: dict[str, dict] = {}
    seen: set[tuple[str, str]] = set()
    for dname, d in res["dictionaries"].items():
        label = d["label"]
        for e in d["entries"]:
            if _is_contextual(e) or e.get("attrs", {}).get("categoria") in ("desc_lingua", "desc_pulso"):
                continue  # descritores só valem depois da âncora ("língua ...", "pulso ...")
            eid = f"{label}|{e['canonical']}"
            index[eid] = {"label": label, "canonical": e["canonical"], "attrs": e.get("attrs", {}), "dict": dname}
            terms = {e["canonical"], *e.get("variants", [])}
            if e.get("attrs", {}).get("exact"):
                forms = {t.lower() for t in terms}
            else:
                forms = set()
                for t in terms:
                    forms |= expand_variants(t)
            for f in sorted(forms):
                key = (label, f)
                if key in seen:
                    continue
                seen.add(key)
                patterns.append({"label": label, "pattern": f, "id": eid})
    # nomes (pinyin) dos pontos de acupuntura
    for p in res["points"]["pontos"]:
        eid = f"PONTO|{p['code']}"
        index[eid] = {"label": "PONTO", "canonical": p["code"], "attrs": {"code": p["code"], "nome": p["nome"]}, "dict": "points"}
        for f in {p["nome"].lower(), fold(p["nome"])}:
            patterns.append({"label": "PONTO", "pattern": f, "id": eid})
    return patterns, index


def descriptor_lexicon(category: str) -> set[str]:
    """Palavras descritivas (língua/pulso) usadas apenas depois da âncora."""
    res = get_resources()
    out: set[str] = set()
    for e in res["dictionaries"]["mtc"]["entries"]:
        if e.get("attrs", {}).get("categoria") == category:
            for t in {e["canonical"], *e.get("variants", [])}:
                out.add(fold(t))
    return out
