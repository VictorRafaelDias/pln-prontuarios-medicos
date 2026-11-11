"""Etapa 10 — Mapeamento entidade → campo do formulário (regras + similaridade TF-IDF) com pontuação de confiança."""
from __future__ import annotations

import re
from collections import defaultdict

from ..form_schema import FIELD_BY_ID, alias_for_mode, fold, normalize_value
from ..mapping_rules import Mapper
from .base import PipelineState, Stage

LIST_TYPES = {"list", "multiselect", "bodymap", "points"}

# Descritores usados na similaridade TF-IDF (campos de texto livre sobre hábitos)
FIELD_DESCRIPTORS = {
    "habitos.sono": "sono dormir dormindo dormi acordar acordo madrugada insonia travesseiro cama deitar descansar descansado horas de sono pesadelo",
    "habitos.alimentacao": "alimentacao comer comida refeicao almoco jantar cafe da manha lanche dieta doce acucar fritura verdura fruta legume carne massa pao arroz feijao refrigerante",
    "habitos.intestino": "intestino evacuar evacuacao fezes banheiro constipacao diarreia prisao de ventre gases",
    "habitos.urina": "urina urinar xixi bexiga noturia urgencia urinaria ardencia",
    "habitos.atividade_fisica": "exercicio atividade fisica academia caminhada corrida musculacao pilates yoga natacao esporte treino sedentario",
    "habitos.agua": "agua beber litros copos hidratacao sede",
    "saude.ciclo": "menstruacao ciclo menstrual tpm colica fluxo menopausa atraso regular irregular",
}


def similarity_candidates(state: PipelineState, cands: list[dict]) -> tuple[list[dict], dict]:
    """Para sentenças do paciente sem mapeamento por regra, sugere o campo textual mais parecido (TF-IDF + cosseno)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    info = {"method": "TF-IDF (unigramas+bigramas, sublinear) + similaridade do cosseno entre o lema da sentença e o descritor de cada campo",
            "threshold": 0.2, "scored": []}
    if state.mode != "anamnese":
        return [], info
    used = {c["sent"] for c in cands}
    ids = list(FIELD_DESCRIPTORS)
    vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"(?u)\b\w\w+\b")
    X = vec.fit_transform([FIELD_DESCRIPTORS[i] for i in ids])
    out = []
    by_tok_sent: dict[int, list[str]] = defaultdict(list)
    for t in state.tokens:
        s = state.sentence_of(t["start"])
        if s is not None and not t.get("is_punct") and not t.get("is_stop"):
            by_tok_sent[s["idx"]].append(fold(t.get("lemma", t["text"])))
    for s in state.sentences:
        if s["speaker"] != "paciente" or s["idx"] in used:
            continue
        words = by_tok_sent.get(s["idx"], [])
        if len(words) < 3 or "?" in s["text"]:
            continue
        ents = [e for e in state.entities if e["sent"] == s["idx"]]
        if any(e["label"] in ("INTENSIDADE", "PARTE_CORPO", "TIPO_DOR") for e in ents):
            continue
        sims = cosine_similarity(vec.transform([" ".join(words)]), X)[0]
        order = sims.argsort()[::-1]
        best, second = float(sims[order[0]]), float(sims[order[1]]) if len(order) > 1 else 0.0
        info["scored"].append({"sent": s["idx"], "text": s["text"], "best": ids[order[0]], "score": round(best, 3), "second": round(second, 3)})
        if best >= info["threshold"] and best >= 1.4 * second:
            out.append({"field": ids[order[0]], "value": s["text"].rstrip("."), "conf": round(min(0.5, 0.25 + 0.8 * best), 3),
                        "evidence": s["text"], "sent": s["idx"], "utt": s["utt"], "speaker": s["speaker"], "start": s["start"],
                        "end": s["end"], "rule": f"similaridade TF-IDF (cos={best:.2f})", "entities": [], "status": "afirmado",
                        "uncertain": False})
    return out, info


def _key(v) -> str:
    return fold(str(v))


def consolidate(cands: list[dict], mode: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in cands:
        fid = alias_for_mode(c["field"], mode)
        if fid is None:
            continue
        groups[fid].append(c)
    out: dict[str, dict] = {}
    for fid, cs in groups.items():
        f = FIELD_BY_ID[fid]
        t = f["type"]
        alts = []
        if t in LIST_TYPES:
            items: dict[str, dict] = {}
            for c in cs:
                vals = c["value"] if isinstance(c["value"], list) else [c["value"]]
                for v in vals:
                    k = _key(v)
                    if k not in items or items[k]["conf"] < c["conf"]:
                        items[k] = {"value": v, "conf": c["conf"], "evidence": c["evidence"], "rule": c["rule"], "sent": c["sent"], "utt": c["utt"]}
            values = [i["value"] for i in items.values()]
            value = normalize_value(fid, values)
            if value is None:
                continue
            keep = {_key(v) for v in (value if isinstance(value, list) else [value])}
            used = [i for k, i in items.items() if _key(i["value"]) in keep or k in keep]
            conf = sum(i["conf"] for i in used) / max(1, len(used)) if used else max(i["conf"] for i in items.values())
            first = min(used or items.values(), key=lambda i: i["utt"])
            rec = {"value": value, "confidence": round(conf, 3), "evidence": " | ".join(dict.fromkeys(i["evidence"] for i in used))[:400],
                   "rule": "; ".join(dict.fromkeys(i["rule"] for i in used))[:200], "items": used, "sent": first["sent"], "utt": first["utt"]}
        elif t == "bool":
            pos = [c for c in cs if c["value"] is True]
            neg = [c for c in cs if c["value"] is False]
            if pos:
                best = max(pos, key=lambda c: c["conf"])
                conf = best["conf"] * (0.7 if neg else 1.0)
                value = True
                alts = [{"value": False, "confidence": n["conf"], "evidence": n["evidence"]} for n in neg[:2]]
            else:
                best = max(neg, key=lambda c: c["conf"])
                conf, value = best["conf"], False
            rec = {"value": value, "confidence": round(conf, 3), "evidence": best["evidence"], "rule": best["rule"], "sent": best["sent"],
                   "utt": best["utt"], "conflict": bool(pos and neg)}
        else:
            best = max(cs, key=lambda c: (c["conf"], c["utt"]))
            value = normalize_value(fid, best["value"])
            if value is None:
                continue
            alts = []
            for c in sorted(cs, key=lambda c: -c["conf"]):
                v = normalize_value(fid, c["value"])
                if v is not None and _key(v) != _key(value) and len(alts) < 3:
                    alts.append({"value": v, "confidence": c["conf"], "evidence": c["evidence"]})
            rec = {"value": value, "confidence": round(best["conf"], 3), "evidence": best["evidence"], "rule": best["rule"],
                   "sent": best["sent"], "utt": best["utt"]}
        rec.update({"source": "rules", "alternatives": alts, "uncertain": any(c.get("uncertain") for c in cs),
                    "status": "negado" if (t == "bool" and rec["value"] is False) else "afirmado"})
        extra = next((c.get("quit_time") for c in cs if c.get("quit_time")), None)
        if extra:
            rec["note"] = f"Parou há {extra.replace('Há ', '')}"
        out[fid] = rec
    return out


class MappingStage(Stage):
    id = "mapping"
    index = 10
    name = "Mapeamento → formulário"
    short = "Mapeia"
    explain = {
        "what": "Transforma entidades em valores de campos do formulário, cada um com uma confiança e o trecho de origem: EVA ← \"nota 8\"; tabagismo ← hábito + negação/estado passado; localização ← partes do corpo no mapa corporal; contraindicações ← condições afirmadas ou negadas; pontos ← códigos VB20, E36...",
        "why": "Sozinha, uma entidade não preenche nada: é preciso saber QUEM falou (relato do paciente × ditado do profissional), se foi negada, e a qual campo pertence. Respostas curtas (\"Não.\") só fazem sentido junto da pergunta anterior.",
        "how": "1) REGRAS por campo (rótulo + atributos + negação + falante). 2) Pares pergunta→resposta curta (QA). 3) Para sentenças sem regra, SIMILARIDADE TF-IDF/cosseno entre o lema da sentença e descritores dos campos de hábitos. 4) Consolidação: escalares ficam com o candidato de maior confiança; listas fazem união; contraindicações seguem 'segurança primeiro' (se há afirmação e negação, vale a afirmação, com confiança reduzida e conflito sinalizado).",
    }

    def run(self, state: PipelineState):
        mapper = Mapper(state)
        cands = mapper.run()
        sim, sim_info = similarity_candidates(state, cands)
        cands = cands + sim
        state.candidates = cands
        fields = consolidate(cands, state.mode)
        state.rule_fields = fields
        slim = [{k: c[k] for k in ("field", "value", "conf", "evidence", "rule", "status", "speaker", "sent")} for c in cands]
        return {"fields": fields, "candidates": slim, "n_candidates": len(cands), "n_fields": len(fields),
                "similarity": sim_info, "mode": state.mode}
