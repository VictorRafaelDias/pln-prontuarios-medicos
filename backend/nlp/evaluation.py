"""Avaliação contra o gold standard: precisão, recall e F1 por campo e geral (Regras × LLM × Híbrido), matriz de confusão e erros."""
from __future__ import annotations

import json
import re
from collections import defaultdict

from . import llm as llm_mod
from .form_schema import FIELD_BY_ID, fold, is_empty, normalize_value
from .pipeline import run_pipeline
from .resources import GOLD_DIR
from .stages.s12_merge import merge_fields

LIST_TYPES = {"list", "multiselect", "bodymap", "points"}
_STOP = {"de", "do", "da", "dos", "das", "o", "a", "os", "as", "um", "uma", "e", "em", "no", "na", "nos", "nas", "com", "para", "por", "que", "ao", "eu"}


def load_gold() -> dict:
    return json.loads((GOLD_DIR / "gold_standard.json").read_text(encoding="utf-8"))


def _toks(s) -> set[str]:
    return {w for w in re.findall(r"\w+", fold(str(s))) if w not in _STOP and len(w) > 1}


def item_match(ftype: str, a, b) -> bool:
    if ftype in ("text", "textarea", "list"):
        ta, tb = _toks(a), _toks(b)
        if not ta or not tb:
            return fold(str(a)) == fold(str(b))
        return len(ta & tb) / len(ta | tb) >= 0.4 or ta <= tb or tb <= ta
    if ftype in ("number", "scale"):
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return False
    return fold(str(a)) == fold(str(b))


def score_transcript(gold: dict, pred: dict[str, dict], min_conf: float = 0.0) -> tuple[dict, list[dict]]:
    """Retorna ({campo: (tp, fp, fn)}, erros)."""
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    errors: list[dict] = []
    pv = {k: v for k, v in pred.items() if v["confidence"] >= min_conf and k != "habitos.maco_ano"}
    for fid in set(gold) | set(pv):
        f = FIELD_BY_ID.get(fid)
        if f is None:
            continue
        t = f["type"]
        g = gold.get(fid)
        p = pv.get(fid, {}).get("value") if fid in pv else None
        if t in LIST_TYPES:
            gl = g if isinstance(g, list) else ([] if g is None else [g])
            pl = p if isinstance(p, list) else ([] if p is None else [p])
            used = set()
            for gi in gl:
                hit = next((j for j, pi in enumerate(pl) if j not in used and item_match(t if t != "multiselect" else "select", gi, pi)), None)
                if hit is None:
                    counts[fid][2] += 1
                    errors.append({"field": fid, "kind": "falso negativo", "gold": gi, "pred": None})
                else:
                    used.add(hit)
                    counts[fid][0] += 1
            for j, pi in enumerate(pl):
                if j not in used:
                    counts[fid][1] += 1
                    errors.append({"field": fid, "kind": "falso positivo", "gold": None, "pred": pi, "evidence": pv[fid].get("evidence", "")[:160]})
        else:
            if g is None and p is None:
                continue
            if g is not None and p is None:
                counts[fid][2] += 1
                errors.append({"field": fid, "kind": "falso negativo", "gold": g, "pred": None})
            elif g is None:
                counts[fid][1] += 1
                errors.append({"field": fid, "kind": "falso positivo", "gold": None, "pred": p, "evidence": pv[fid].get("evidence", "")[:160]})
            elif item_match(t, g, p):
                counts[fid][0] += 1
            else:
                counts[fid][1] += 1
                counts[fid][2] += 1
                errors.append({"field": fid, "kind": "valor errado", "gold": g, "pred": p, "evidence": pv[fid].get("evidence", "")[:160]})
    return counts, errors


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 3), "recall": round(r, 3), "f1": round(f1, 3)}


def confusion(fid: str, gold_items: list[tuple]) -> dict:
    """Matriz de confusão para um campo categórico: linhas = gold, colunas = previsto ('∅' = vazio)."""
    from sklearn.metrics import confusion_matrix
    labels = sorted({str(g) for g, _ in gold_items} | {str(p) for _, p in gold_items})
    y_true = [str(g) for g, _ in gold_items]
    y_pred = [str(p) for _, p in gold_items]
    m = confusion_matrix(y_true, y_pred, labels=labels)
    return {"field": fid, "labels": labels, "matrix": m.tolist()}


def run_evaluation(approaches: list[str] | None = None, min_conf: float = 0.0, use_llm_cache: bool = True) -> dict:
    approaches = approaches or ["rules", "llm", "hybrid"]
    gold = load_gold()
    llm_ok = llm_mod.available()
    totals: dict[str, dict[str, list[int]]] = {a: defaultdict(lambda: [0, 0, 0]) for a in approaches}
    errors: dict[str, list[dict]] = {a: [] for a in approaches}
    per_tr: dict[str, dict] = {}
    cat_pairs: dict[str, list[tuple]] = defaultdict(list)
    presence = {a: [0, 0, 0, 0] for a in approaches}  # tp, fp, fn, tn por presença de campo
    llm_cost = 0.0
    llm_ms = 0.0
    rules_ms = 0.0
    from .form_schema import field_ids_for_mode
    for tr in gold["transcripts"]:
        mode = tr["mode"]
        utts = [{**u, "ts": i * 6.0} for i, u in enumerate(tr["utterances"])]
        base = run_pipeline(utts, mode=mode, include_stages=False, previous_session=tr.get("previous"))
        rules_ms += base["timing"]["total_ms"]
        rule_fields = base["rule_fields"]
        llm_fields = None
        if llm_ok and ("llm" in approaches or "hybrid" in approaches):
            res = llm_mod.extract([{"speaker": u["speaker"], "text": u["text"], "ts": u["ts"]} for u in base["utterances"] if u["text"]],
                                  mode, {}, tr.get("previous"), use_cache=use_llm_cache)
            llm_fields = res["fields"]
            llm_cost += res.get("cost_usd") or 0
            llm_ms += res.get("latency_ms") or 0
        preds = {}
        if "rules" in approaches:
            preds["rules"] = rule_fields
        if llm_fields is not None and "llm" in approaches:
            preds["llm"] = llm_fields
        if llm_fields is not None and "hybrid" in approaches:
            preds["hybrid"], _ = merge_fields(rule_fields, llm_fields, set())
        per_tr[tr["id"]] = {}
        valid_ids = set(field_ids_for_mode(mode))
        for a, pf in preds.items():
            counts, errs = score_transcript(tr["gold"], pf, min_conf)
            for fid, (tp, fp, fn) in counts.items():
                for k, v in enumerate((tp, fp, fn)):
                    totals[a][fid][k] += v
            for e in errs:
                e.update({"transcript": tr["id"], "title": tr["title"]})
                errors[a].append(e)
            c = [sum(v[0] for v in counts.values()), sum(v[1] for v in counts.values()), sum(v[2] for v in counts.values())]
            per_tr[tr["id"]][a] = prf(*c)
            for fid in valid_ids:
                has_g = fid in tr["gold"]
                has_p = fid in pf and pf[fid]["confidence"] >= min_conf and fid != "habitos.maco_ano"
                presence[a][0 if has_g and has_p else 1 if has_p else 2 if has_g else 3] += 1
            for fid in ("habitos.tabagismo", "habitos.etilismo", "queixa.horario_pior"):
                if fid in tr["gold"] or fid in pf:
                    cat_pairs[f"{a}|{fid}"].append((tr["gold"].get(fid, "∅"), pf.get(fid, {}).get("value", "∅")))
    out: dict = {"approaches": {}, "llm_available": llm_ok, "n_transcripts": len(gold["transcripts"]), "min_conf": min_conf,
                 "timing": {"rules_ms_total": round(rules_ms, 1), "llm_ms_total": round(llm_ms, 1)}, "llm_cost_usd": round(llm_cost, 5),
                 "per_transcript": per_tr}
    for a in approaches:
        if a != "rules" and not llm_ok:
            out["approaches"][a] = {"available": False, "reason": "Sem ANTHROPIC_API_KEY"}
            continue
        fields = {fid: prf(*c) for fid, c in sorted(totals[a].items())}
        tp, fp, fn = (sum(c[i] for c in totals[a].values()) for i in range(3))
        tn_pres = presence[a]
        out["approaches"][a] = {
            "available": True, "overall": prf(tp, fp, fn),
            "macro_f1": round(sum(v["f1"] for v in fields.values()) / max(1, len(fields)), 3),
            "fields": fields, "errors": errors[a],
            "presence_matrix": {"tp": tn_pres[0], "fp": tn_pres[1], "fn": tn_pres[2], "tn": tn_pres[3]},
            "confusion": [confusion(k.split("|")[1], v) for k, v in cat_pairs.items() if k.startswith(a + "|")],
        }
    return out
