"""Regras de negócio: resumo do paciente, alertas, estatísticas do laboratório."""
from __future__ import annotations

import math
import re
from collections import Counter

from sqlmodel import Session, select

from nlp.form_schema import FIELD_BY_ID, fold

from .db import ConsultaSession, Patient, now


def fv(form: dict, fid: str):
    f = form.get(fid)
    return f.get("value") if isinstance(f, dict) else None


def compute_alerts(form: dict) -> list[str]:
    out = []
    for fid, f in FIELD_BY_ID.items():
        if fid.startswith("contra.") and fv(form, fid) is True:
            out.append(f["alert"])
    return out


def refresh_patient(s: Session, p: Patient) -> None:
    sessions = s.exec(select(ConsultaSession).where(ConsultaSession.patient_id == p.id, ConsultaSession.status == "saved")
                      .order_by(ConsultaSession.saved_at)).all()
    anam = next((x for x in reversed(sessions) if x.kind == "anamnese"), None)
    if anam:
        p.anamnese = anam.form
    form = p.anamnese or {}
    alerts = set(compute_alerts(form))
    for x in sessions:  # contraindicações novas em sessões SOAP também alertam
        alerts |= set(compute_alerts(x.form))
    p.alerts = sorted(alerts)
    p.main_complaint = fv(form, "queixa.descricao") or ""
    pats: list[str] = list(fv(form, "mtc.padroes") or [])
    for x in sessions:
        a = fv(x.form, "soap.a_padrao")
        if a:
            pats.append(a)
    p.mtc_patterns = list(dict.fromkeys(pats))
    pts: list[str] = []
    for x in sessions:
        pts += fv(x.form, "soap.p_pontos") or []
    p.points = list(dict.fromkeys(pts))
    p.smoking = fv(form, "habitos.tabagismo") or ""
    p.session_count = len(sessions)
    p.last_session_at = sessions[-1].saved_at if sessions else ""
    evas = [x.eva for x in sessions if x.eva is not None]
    p.last_eva = evas[-1] if evas else None
    p.search_text = fold(" ".join([p.name, p.phone, p.email, p.profession, p.main_complaint, *p.mtc_patterns, *p.points,
                                   " ".join(str(x) for x in (fv(form, "queixa.localizacao") or []))]))
    s.add(p)


def session_eva(form: dict, kind: str):
    v = fv(form, "soap.s_eva" if kind == "soap" else "queixa.eva")
    if v is None and kind == "anamnese":
        v = fv(form, "soap.s_eva")
    return int(v) if isinstance(v, (int, float)) else None


def session_summary(form: dict, kind: str) -> str:
    if kind == "soap":
        parts = [fv(form, "soap.a_evolucao"), f"EVA {session_eva(form, kind)}" if session_eva(form, kind) is not None else None,
                 ("Pontos: " + ", ".join(fv(form, "soap.p_pontos"))) if fv(form, "soap.p_pontos") else None]
    else:
        parts = [fv(form, "queixa.descricao"), f"EVA {session_eva(form, kind)}" if session_eva(form, kind) is not None else None,
                 ("Pontos: " + ", ".join(fv(form, "soap.p_pontos"))) if fv(form, "soap.p_pontos") else None]
    return " · ".join(str(x) for x in parts if x)


# ---------------------------------------------------------------- estatísticas do laboratório
def analysis_stats(result: dict) -> dict:
    stage = {s["id"]: s for s in result["stages"]}
    toks = stage["lemma_stem"]["output"]["rows"]
    stop_by_i = {t["i"]: t["is_stop"] for t in stage["stopwords"]["output"]["kept"]} if False else {}
    stop_out = stage["stopwords"]["output"]
    stop_ids = {t["i"] for t in stop_out["removed"]}
    words = [r for r in toks if r["text"].isalpha()]
    content = [r["lemma"].lower() for r in words if r["i"] not in stop_ids]
    freq = Counter(content)
    seq = [r["lemma"].lower() for r in words]
    bi = Counter(zip(seq, seq[1:]))
    tri = Counter(zip(seq, seq[1:], seq[2:]))

    def top(c, n=12, sep=" "):
        return [{"term": sep.join(k) if isinstance(k, tuple) else k, "count": v} for k, v in c.most_common(n)]
    ents = Counter(e["label"] for e in result["entities"] if e.get("clinical"))
    return {"term_freq": top(freq, 30), "bigrams": top(Counter({k: v for k, v in bi.items() if v > 1}) or bi, 12),
            "trigrams": top(Counter({k: v for k, v in tri.items() if v > 1}) or tri, 10),
            "entities_by_label": [{"label": k, "count": v} for k, v in ents.most_common()],
            "n_words": len(words), "n_unique_lemmas": len(set(content))}


def tfidf_by_session(s: Session, current_text: str | None = None, top_n: int = 12) -> dict:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from nlp.stages.s05_stopwords import build_stopwords

    stop, preserve, _ = build_stopwords()
    sess = s.exec(select(ConsultaSession).where(ConsultaSession.status == "saved")).all()
    names = {p.id: p.name for p in s.exec(select(Patient)).all()}
    docs, labels = [], []
    for x in sess:
        txt = " ".join(u["text"] for u in x.transcript if u.get("speaker") == "paciente" or True)
        docs.append(txt)
        labels.append({"session_id": x.id, "patient": names.get(x.patient_id, "?"), "kind": x.kind, "date": x.saved_at[:10]})
    if current_text:
        docs.append(current_text)
        labels.append({"session_id": None, "patient": "(análise atual)", "kind": "-", "date": ""})
    if len(docs) < 2:
        return {"documents": [], "note": "São necessárias ao menos 2 sessões salvas para o TF-IDF."}

    def tok(t):
        return [w for w in re.findall(r"[a-zà-ÿ]{3,}", t.lower()) if fold(w) not in stop or fold(w) in preserve]
    vec = TfidfVectorizer(tokenizer=tok, lowercase=True, token_pattern=None, sublinear_tf=True)
    X = vec.fit_transform(docs)
    terms = vec.get_feature_names_out()
    out = []
    for i, lab in enumerate(labels):
        row = X[i].toarray()[0]
        idx = row.argsort()[::-1][:top_n]
        out.append({**lab, "top": [{"term": terms[j], "score": round(float(row[j]), 3)} for j in idx if row[j] > 0]})
    return {"documents": out, "n_docs": len(docs), "vocab": len(terms)}
