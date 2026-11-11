"""Carregamento (e recarga a quente) dos recursos linguísticos editáveis em JSON."""
from __future__ import annotations

import json
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


def save_resource_file(name: str, data: Any) -> None:
    if name in CONFIG_FILES:
        path = CONFIG_FILES[name]
    elif (DICT_DIR / f"{name}.json").exists():
        path = DICT_DIR / f"{name}.json"
        if not isinstance(data, dict) or "label" not in data or not isinstance(data.get("entries"), list):
            raise ValueError("Dicionário deve ter 'label' e uma lista 'entries'.")
        for e in data["entries"]:
            if "canonical" not in e or not isinstance(e.get("variants", []), list):
                raise ValueError("Cada entrada precisa de 'canonical' e 'variants' (lista).")
    else:
        raise KeyError(name)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    reload_resources()


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
