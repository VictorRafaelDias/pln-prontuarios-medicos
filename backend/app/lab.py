"""Endpoints do Laboratório PLN."""
from __future__ import annotations

import html
import json

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlmodel import Session

from nlp import evaluation, llm as llm_mod, ner_regex, resources, spacy_loader
from nlp.form_schema import FIELD_BY_ID
from nlp.pipeline import run_pipeline
from nlp.stages import all_stages

from . import pdf as pdfmod
from . import services
from .db import ConsultaSession, LabCache, get_session

router = APIRouter()


def parse_free_text(text: str) -> list[dict]:
    out = []
    for i, line in enumerate(l for l in text.splitlines() if l.strip()):
        sp, t = "paciente", line.strip()
        for pref, who in (("profissional:", "profissional"), ("prof:", "profissional"), ("p:", "profissional"), ("paciente:", "paciente"), ("a:", "paciente")):
            if t.lower().startswith(pref):
                sp, t = who, t[len(pref):].strip()
                break
        out.append({"speaker": sp, "text": t, "ts": i * 5.0})
    return out


@router.get("/stages")
def stages_meta():
    return [s.meta() for s in all_stages()]


@router.post("/analyze")
def analyze(body: dict = Body(...), s: Session = Depends(get_session)):
    utts = body.get("utterances")
    if not utts and body.get("session_id"):
        x = s.get(ConsultaSession, body["session_id"])
        if not x:
            raise HTTPException(404, "Sessão não encontrada")
        utts = x.transcript
        body.setdefault("mode", x.kind)
    if not utts and body.get("text"):
        utts = parse_free_text(body["text"])
    if not utts:
        raise HTTPException(422, "Forneça utterances, session_id ou text.")
    res = run_pipeline(utts, mode=body.get("mode", "anamnese"), use_llm=bool(body.get("use_llm")), force_llm=bool(body.get("use_llm")),
                       confirmed={}, previous_session=body.get("previous_session"), include_stages=True,
                       count_llm_tokens=bool(body.get("count_llm_tokens", True)))
    res["stats"] = services.analysis_stats(res)
    res["llm_settings"] = {k: v for k, v in llm_mod.settings().items()}
    return res


@router.get("/tfidf")
def tfidf(current_text: str | None = None, s: Session = Depends(get_session)):
    return services.tfidf_by_session(s, current_text)


@router.post("/evaluate")
def evaluate(body: dict = Body(default={}), s: Session = Depends(get_session)):
    res = evaluation.run_evaluation(body.get("approaches"), float(body.get("min_conf", 0.0)), dataset=body.get("dataset", "gold"))
    return res


@router.get("/datasets")
def datasets():
    out = []
    for k in evaluation.DATASETS:
        g = evaluation.load_gold(k)
        out.append({"id": k, "n": len(g["transcripts"]), "description": g.get("description", "")})
    return out


@router.get("/gold")
def gold():
    g = evaluation.load_gold()
    return [{"id": t["id"], "title": t["title"], "mode": t["mode"], "n_gold_fields": len(t["gold"]), "gold": t["gold"], "utterances": t["utterances"]}
            for t in g["transcripts"]]


# ---- Dicionários
@router.get("/resources")
def res_list():
    return resources.list_resource_files()


@router.get("/resources/{name}")
def res_get(name: str):
    try:
        return resources.get_resource_file(name)
    except KeyError:
        raise HTTPException(404, "Recurso não encontrado")


@router.put("/resources/{name}")
def res_put(name: str, data: dict = Body(...)):
    try:
        resources.save_resource_file(name, data)
    except KeyError:
        raise HTTPException(404, "Recurso não encontrado")
    except ValueError as e:
        raise HTTPException(422, str(e))
    n = spacy_loader.reload_ruler()
    return {"ok": True, "ruler_patterns": n}


@router.get("/regex-rules")
def regex_rules():
    return ner_regex.rule_catalog()


# ---- Exportação
def _html_report(a: dict) -> str:
    colors = {"PARTE_CORPO": "#d9c7a3", "SINTOMA": "#f2b8a2", "TIPO_DOR": "#f0a5a5", "DOENCA": "#cdb4e0", "MEDICAMENTO": "#a8d5c2", "HABITO": "#f7d98b",
              "MTC": "#a9c8e8", "PONTO": "#8fd0d6", "TECNICA": "#b9d98f", "HORARIO": "#e3d2f0", "CONDICAO": "#f4a6b8", "INTENSIDADE": "#ffc27a",
              "FREQUENCIA": "#ffe08a", "TEMPO": "#c9e4a0", "CIRURGIA": "#d4b9a0", "FAMILIAR": "#f1c6e0", "ALERGENO": "#f6b0b0", "DOSE": "#d0d0d0"}
    text, ents = a["text"], sorted([e for e in a["entities"] if e.get("clinical")], key=lambda e: e["start"])
    out, pos = [], 0
    for e in ents:
        if e["start"] < pos:
            continue
        out.append(html.escape(text[pos:e["start"]]))
        style = f"background:{colors.get(e['label'], '#ddd')};padding:1px 3px;border-radius:3px;"
        if e.get("negated"):
            style += "text-decoration:line-through;"
        if e.get("uncertain"):
            style += "border-bottom:2px wavy #b9573a;"
        out.append(f"<mark style=\"{style}\" title=\"{html.escape(e['label'] + ' — ' + e['rule'])}\">{html.escape(text[e['start']:e['end']])}</mark>")
        pos = e["end"]
    out.append(html.escape(text[pos:]))
    rows = "".join(f"<tr><td>{s['index']}</td><td>{html.escape(s['name'])}</td><td>{s['ms']:.2f}</td><td>{html.escape(s['explain']['what'])}</td></tr>" for s in a["stages"] if "name" in s)
    frows = "".join(f"<tr><td>{html.escape(FIELD_BY_ID.get(k, {}).get('label', k))}</td><td>{html.escape(pdfmod.fmt_value(k, v['value']))}</td><td>{v['source']}</td><td>{v['confidence']:.2f}</td></tr>" for k, v in a["fields"].items())
    return f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Relatório — Laboratório PLN</title>
<style>body{{font-family:Inter,Arial,sans-serif;max-width:980px;margin:2rem auto;color:#2f3532;background:#fbf8ef;padding:0 1rem}}h1,h2{{font-family:Georgia,serif;color:#5f7f6a}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #d8d2c0;padding:5px 8px;vertical-align:top}}th{{background:#5f7f6a;color:#fff;text-align:left}}p.t{{line-height:2;background:#fff;padding:1rem;border-radius:8px}}</style>
<h1>Relatório do Laboratório PLN</h1><h2>Texto anotado</h2><p class="t">{''.join(out)}</p>
<h2>Etapas do pipeline</h2><table><tr><th>#</th><th>Etapa</th><th>ms</th><th>O que faz</th></tr>{rows}</table>
<h2>Campos extraídos</h2><table><tr><th>Campo</th><th>Valor</th><th>Origem</th><th>Confiança</th></tr>{frows}</table></html>"""


@router.post("/export/{fmt}")
def export(fmt: str, analysis: dict = Body(...)):
    if fmt == "json":
        return Response(json.dumps(analysis, ensure_ascii=False, indent=1), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="analise-pln.json"'})
    if fmt == "html":
        return Response(_html_report(analysis), media_type="text/html; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="relatorio-pln.html"'})
    if fmt == "pdf":
        return Response(pdfmod.lab_report_pdf(analysis), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="relatorio-pln.pdf"'})
    raise HTTPException(404, "Formato inválido")
