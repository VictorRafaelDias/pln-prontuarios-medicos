"""Etapa 12 — Fusão (merge) clássico + LLM com regra de prioridade explícita."""
from __future__ import annotations

import re

from ..form_schema import FIELD_BY_ID, compute_maco_ano, fold, is_empty
from .base import PipelineState, Stage

LIST_TYPES = {"list", "multiselect", "bodymap", "points"}
STRUCTURED = {"select", "number", "scale", "bool", "bodymap", "points", "multiselect"}
_STOP = {"de", "do", "da", "dos", "das", "o", "a", "os", "as", "um", "uma", "e", "em", "no", "na", "com", "para", "por", "que"}

PRIORITY_RULES = [
    "P1 — Campo CONFIRMADO pelo profissional (origem 'Manual'): nunca é sobrescrito.",
    "P2 — Só um método extraiu o campo: vale esse valor (origem 'Regras' ou 'LLM').",
    "P3 — Os dois extraíram e CONCORDAM (mesmo valor, ou textos/listas com ≥ 50% de sobreposição): origem 'Ambos'; confiança combinada = 1 − (1−c₁)(1−c₂); estruturados/listas usam o valor das Regras (verificável) e listas fazem união; texto livre usa a redação do LLM (mais fluente).",
    "P4 — DIVERGEM em contraindicação (booleano): vale a AFIRMAÇÃO (segurança primeiro), com confiança × 0,7 e conflito sinalizado.",
    "P5 — DIVERGEM em campo estruturado (número, EVA, seleção, pontos): vale as Regras quando a regra veio de padrão numérico/regex explícito e confiança ≥ 0,85; senão vale a maior confiança.",
    "P6 — DIVERGEM em texto livre: vale a maior confiança (LLM com bônus de +0,05 por ler contexto); o outro valor fica em 'alternativas'.",
]


def _toks(s) -> set[str]:
    return {w for w in re.findall(r"\w+", fold(str(s))) if w not in _STOP and len(w) > 1}


def values_agree(ftype: str, a, b) -> bool:
    if ftype in LIST_TYPES:
        sa = {fold(str(x)) for x in (a if isinstance(a, list) else [a])}
        sb = {fold(str(x)) for x in (b if isinstance(b, list) else [b])}
        if not sa or not sb:
            return False
        inter = len(sa & sb)
        if inter == 0 and ftype == "list":  # listas de texto: compara por tokens
            ta, tb = set().union(*[_toks(x) for x in sa]), set().union(*[_toks(x) for x in sb])
            return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.5
        return inter / len(sa | sb) >= 0.5 or sa <= sb or sb <= sa
    if ftype in ("text", "textarea"):
        ta, tb = _toks(a), _toks(b)
        if not ta or not tb:
            return False
        return len(ta & tb) / len(ta | tb) >= 0.4 or ta <= tb or tb <= ta
    return fold(str(a)) == fold(str(b))


def merge_fields(rule_fields: dict, llm_fields: dict | None, confirmed_ids: set[str]) -> tuple[dict, list[dict]]:
    llm_fields = llm_fields or {}
    out: dict[str, dict] = {}
    log: list[dict] = []
    for fid in sorted(set(rule_fields) | set(llm_fields)):
        if fid in confirmed_ids or fid not in FIELD_BY_ID:
            continue
        r, l = rule_fields.get(fid), llm_fields.get(fid)
        t = FIELD_BY_ID[fid]["type"]
        if r and not l:
            out[fid] = {**r, "source": "rules"}
            log.append({"field": fid, "decision": "P2 só Regras"})
        elif l and not r:
            out[fid] = {"value": l["value"], "confidence": l["confidence"], "evidence": l.get("evidence", ""), "rule": "LLM",
                        "source": "llm", "alternatives": [], "status": "negado" if l["value"] is False else "afirmado"}
            log.append({"field": fid, "decision": "P2 só LLM"})
        else:
            if values_agree(t, r["value"], l["value"]):
                conf = round(1 - (1 - r["confidence"]) * (1 - l["confidence"]), 3)
                if t in LIST_TYPES:
                    merged_vals = list(r["value"])
                    seen = {fold(str(x)) for x in merged_vals}
                    for x in (l["value"] if isinstance(l["value"], list) else [l["value"]]):
                        if fold(str(x)) not in seen:
                            merged_vals.append(x)
                    value = merged_vals
                elif t in ("text", "textarea"):
                    value = l["value"]
                else:
                    value = r["value"]
                out[fid] = {**r, "value": value, "confidence": min(conf, 0.99), "source": "both",
                            "evidence": r.get("evidence") or l.get("evidence", ""), "alternatives": []}
                log.append({"field": fid, "decision": "P3 concordam → Ambos"})
            elif t == "bool":
                pos = r if r["value"] is True else l
                neg = l if pos is r else r
                if pos["value"] is True and neg["value"] is False:
                    out[fid] = {**r, "value": True, "confidence": round(pos["confidence"] * 0.7, 3), "source": "rules" if pos is r else "llm",
                                "conflict": True, "alternatives": [{"value": False, "confidence": neg["confidence"], "evidence": neg.get("evidence", "")}],
                                "evidence": pos.get("evidence", "")}
                    log.append({"field": fid, "decision": "P4 divergem (contraindicação) → afirmação vence"})
                else:
                    out[fid] = {**r, "source": "rules"}
            else:
                rule_hard = r["confidence"] >= 0.85 and str(r.get("rule", "")).startswith("regex") and t in ("number", "scale", "select", "points")
                l_score = l["confidence"] + (0.05 if t in ("text", "textarea") else 0.0)
                if rule_hard or r["confidence"] >= l_score:
                    win, lose, src = r, l, "rules"
                else:
                    win, lose, src = l, r, "llm"
                out[fid] = {**win, "source": src, "conflict": True,
                            "alternatives": [{"value": lose["value"], "confidence": lose["confidence"], "evidence": lose.get("evidence", ""),
                                              "source": "llm" if src == "rules" else "rules"}],
                            "evidence": win.get("evidence", "")}
                if src == "llm":
                    out[fid].setdefault("rule", "LLM")
                log.append({"field": fid, "decision": f"{'P5' if t in STRUCTURED else 'P6'} divergem → {src}"})
        out[fid].setdefault("alternatives", [])
        out[fid].setdefault("conflict", False)
    return out, log


class MergeStage(Stage):
    id = "merge"
    index = 12
    name = "Fusão (merge)"
    short = "Fusão"
    explain = {
        "what": "Combina o resultado das Regras com o do LLM em um único preenchimento, marcando a ORIGEM de cada valor: Regras, LLM, Ambos (concordam) ou Manual (confirmado pelo profissional).",
        "why": "Os dois métodos erram de formas diferentes: regras são precisas mas rígidas; o LLM é flexível mas pode alucinar. Quando concordam, a confiança sobe; quando divergem, uma regra de prioridade explícita e auditável decide — e a divergência fica visível para o profissional.",
        "how": "Seis regras de prioridade, documentadas abaixo e no README. Campos confirmados manualmente nunca são tocados. O campo calculado 'maços-ano' é derivado depois da fusão.",
    }

    def run(self, state: PipelineState):
        confirmed = state.options.get("confirmed") or {}
        llm_fields = state.llm.get("fields") if state.llm else None
        from ..form_schema import alias_for_mode  # evita ciclo na importação
        if llm_fields:
            llm_fields = {k: v for k, v in llm_fields.items() if alias_for_mode(k, state.mode) == k}
        merged, log = merge_fields(state.rule_fields, llm_fields, set(confirmed))
        # campo calculado
        vals = {k: v["value"] for k, v in merged.items()}
        vals.update({k: v for k, v in confirmed.items() if k not in vals})
        maco = compute_maco_ano(vals)
        if maco is not None and "habitos.maco_ano" not in confirmed:
            merged["habitos.maco_ano"] = {"value": maco, "confidence": 0.9, "evidence": "(cigarros/dia ÷ 20) × anos", "rule": "cálculo",
                                          "source": "calc", "alternatives": [], "conflict": False, "status": "afirmado"}
        # coerência: sem tabagismo "atual/ex", cigarros e anos não fazem sentido
        tab = (merged.get("habitos.tabagismo") or {}).get("value") or confirmed.get("habitos.tabagismo")
        if tab == "nunca":
            for k in ("habitos.cigarros_dia", "habitos.anos_fumo", "habitos.maco_ano"):
                merged.pop(k, None)
        state.merged = merged
        by_source: dict[str, int] = {}
        for v in merged.values():
            by_source[v["source"]] = by_source.get(v["source"], 0) + 1
        return {"fields": merged, "by_source": by_source, "n_fields": len(merged), "decisions": log, "priority_rules": PRIORITY_RULES,
                "skipped_confirmed": sorted(confirmed)}
