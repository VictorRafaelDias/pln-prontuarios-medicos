"""API FastAPI do Prontuário Qi."""
from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, SQLModel, delete, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nlp import llm as llm_mod  # noqa: E402
from nlp import spacy_loader  # noqa: E402
from nlp.form_schema import FIELD_BY_ID, schema_payload  # noqa: E402
from nlp.pipeline import run_pipeline  # noqa: E402
from nlp.resources import get_resources  # noqa: E402

from . import pdf as pdfmod  # noqa: E402
from . import services  # noqa: E402
from .db import (AppSetting, AuditLog, ConsultaSession, LabCache, Patient, all_settings, audit, engine, get_session, init_db,  # noqa: E402
                 now)
from .lab import router as lab_router  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    spacy_loader.get_nlp()  # carrega o modelo uma vez
    with Session(engine) as s:
        if s.exec(select(Patient)).first() is None:
            from .seed import seed
            seed(s)
    yield


app = FastAPI(title="Prontuário Qi", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(lab_router, prefix="/api/lab")


def api_status(s: Session) -> dict:
    st = llm_mod.settings()
    return {"llm_enabled": st["api_key_set"], "model": st["model"] if st["api_key_set"] else None, "effort": st["effort"],
            "badge": "Híbrido (PLN + LLM)" if st["api_key_set"] else "Somente PLN clássico", "spacy": spacy_loader.model_info(),
            "settings": all_settings(s)}


@app.get("/api/status")
def status(s: Session = Depends(get_session)):
    return api_status(s)


@app.get("/api/form-schema")
def form_schema():
    return schema_payload()


@app.get("/api/points")
def points():
    res = get_resources()["points"]
    mer = res["meridianos"]
    return [{**p, "meridiano": mer.get(next((k for k in sorted(mer, key=len, reverse=True) if p["code"].startswith(k)), ""), {}).get("nome", "Extra")}
            for p in res["pontos"]]


# --------------------------------------------------------------------------- PLN
@app.post("/api/nlp/process")
def nlp_process(body: dict = Body(...)):
    utts = body.get("utterances") or []
    res = run_pipeline(utts, mode=body.get("mode", "anamnese"), use_llm=bool(body.get("use_llm")), llm_fields=body.get("llm_fields"),
                       confirmed=body.get("confirmed") or {}, previous_session=body.get("previous_session"), include_stages=False)
    res["llm_status"] = {"enabled": llm_mod.available()}
    return res


@app.get("/api/demo/transcripts")
def demo_transcripts():
    from nlp.evaluation import load_gold
    return [{"id": t["id"], "title": t["title"], "mode": t["mode"], "patient": t.get("patient"), "utterances": t["utterances"]}
            for t in load_gold()["transcripts"]]


# --------------------------------------------------------------------------- Pacientes
def patient_dict(p: Patient, full: bool = False) -> dict:
    d = p.model_dump()
    if not full:
        d.pop("anamnese", None)
        d.pop("search_text", None)
    return d


@app.get("/api/patients")
def list_patients(q: str = "", s: Session = Depends(get_session)):
    from nlp.form_schema import fold
    rows = s.exec(select(Patient).order_by(Patient.name)).all()
    if q:
        terms = fold(q).split()
        rows = [p for p in rows if all(t in p.search_text for t in terms)]
    out = []
    for p in rows:
        d = patient_dict(p)
        d["search_text"] = p.search_text
        d["localizacao"] = services.fv(p.anamnese or {}, "queixa.localizacao") or []
        out.append(d)
    return out


@app.get("/api/patients/{pid}")
def get_patient(pid: int, s: Session = Depends(get_session)):
    p = s.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Paciente não encontrado")
    sess = s.exec(select(ConsultaSession).where(ConsultaSession.patient_id == pid, ConsultaSession.status == "saved")
                  .order_by(ConsultaSession.saved_at)).all()
    return {**patient_dict(p, full=True), "sessions": [{k: v for k, v in x.model_dump().items() if k != "pipeline"} for x in sess]}


@app.put("/api/patients/{pid}")
def update_patient(pid: int, body: dict = Body(...), s: Session = Depends(get_session)):
    p = s.get(Patient, pid)
    if not p:
        raise HTTPException(404)
    for k in ("name", "birth_date", "phone", "email", "profession"):
        if k in body and body[k] != getattr(p, k):
            audit(s, "editar_dados", pid, field=k, old=getattr(p, k), new=body[k])
            setattr(p, k, body[k])
    if "anamnese" in body:
        form = dict(p.anamnese or {})
        for fid, val in body["anamnese"].items():
            if fid in FIELD_BY_ID and (form.get(fid) or {}).get("value") != val:
                audit(s, "editar_anamnese", pid, field=fid, old=(form.get(fid) or {}).get("value"), new=val)
                form[fid] = {"value": val, "source": "manual", "confidence": 1.0, "evidence": "", "confirmed": True}
        p.anamnese = form
        sess = s.exec(select(ConsultaSession).where(ConsultaSession.patient_id == pid, ConsultaSession.kind == "anamnese",
                                                    ConsultaSession.status == "saved").order_by(ConsultaSession.saved_at)).all()
        if sess:
            sess[-1].form = form
            s.add(sess[-1])
    services.refresh_patient(s, p)
    s.commit()
    s.refresh(p)
    return patient_dict(p, full=True)


@app.get("/api/patients/{pid}/audit")
def patient_audit(pid: int, s: Session = Depends(get_session)):
    return [r.model_dump() for r in s.exec(select(AuditLog).where(AuditLog.patient_id == pid).order_by(AuditLog.at.desc())).all()][:200]


# --------------------------------------------------------------------------- Sessões
@app.post("/api/sessions")
def create_session(body: dict = Body(...), s: Session = Depends(get_session)):
    kind = body.get("kind", "anamnese")
    pid = body.get("patient_id")
    pdata = body.get("patient_data") or {}
    if pid:
        p = s.get(Patient, pid)
        if not p:
            raise HTTPException(404, "Paciente não encontrado")
        pdata = {"name": p.name, "birth_date": p.birth_date, "phone": p.phone, "email": p.email, "profession": p.profession, "consent_lgpd": p.consent_lgpd}
    x = ConsultaSession(kind=kind, patient_id=pid, patient_data=pdata, status="draft")
    s.add(x)
    s.commit()
    s.refresh(x)
    return x.model_dump()


@app.get("/api/drafts")
def drafts(s: Session = Depends(get_session)):
    return [{k: v for k, v in x.model_dump().items() if k not in ("pipeline", "transcript")} for x in
            s.exec(select(ConsultaSession).where(ConsultaSession.status == "draft").order_by(ConsultaSession.updated_at.desc())).all()
            if x.transcript or x.form]


@app.get("/api/sessions/{sid}")
def get_consulta(sid: int, s: Session = Depends(get_session)):
    x = s.get(ConsultaSession, sid)
    if not x:
        raise HTTPException(404, "Sessão não encontrada")
    d = x.model_dump()
    if x.patient_id:
        last = s.exec(select(ConsultaSession).where(ConsultaSession.patient_id == x.patient_id, ConsultaSession.status == "saved",
                                                    ConsultaSession.id != sid).order_by(ConsultaSession.saved_at.desc())).first()
        if last:
            d["previous"] = {"id": last.id, "kind": last.kind, "date": last.saved_at, "eva": last.eva, "summary": last.summary,
                             "form": last.form}
        p = s.get(Patient, x.patient_id)
        d["patient_alerts"] = p.alerts if p else []
    return d


@app.put("/api/sessions/{sid}/draft")
def save_draft(sid: int, body: dict = Body(...), s: Session = Depends(get_session)):
    x = s.get(ConsultaSession, sid)
    if not x or x.status != "draft":
        raise HTTPException(404, "Rascunho não encontrado")
    for k in ("form", "transcript", "patient_data", "duration_s"):
        if k in body:
            setattr(x, k, body[k])
    x.updated_at = now()
    s.add(x)
    s.commit()
    return {"ok": True, "updated_at": x.updated_at}


@app.post("/api/sessions/{sid}/save")
def save_session(sid: int, body: dict = Body(...), s: Session = Depends(get_session)):
    x = s.get(ConsultaSession, sid)
    if not x:
        raise HTTPException(404)
    pdata = body.get("patient_data") or x.patient_data or {}
    if not str(pdata.get("name", "")).strip():
        raise HTTPException(422, "Informe o nome do paciente para salvar.")
    p = s.get(Patient, x.patient_id) if x.patient_id else None
    if not (pdata.get("consent_lgpd") or (p and p.consent_lgpd)):
        raise HTTPException(422, "É obrigatório o consentimento LGPD para dados de saúde e transcrição.")
    if p is None:
        p = Patient(name=pdata["name"].strip(), birth_date=pdata.get("birth_date", ""), phone=pdata.get("phone", ""), email=pdata.get("email", ""),
                    profession=pdata.get("profession", ""), consent_lgpd=True, consent_at=now())
        s.add(p)
        s.commit()
        s.refresh(p)
        audit(s, "criar_paciente", p.id, x.id)
    elif not p.consent_lgpd:
        p.consent_lgpd, p.consent_at = True, now()
    form = body.get("form", x.form) or {}
    for fid, f in form.items():
        if isinstance(f, dict) and f.get("value") is not None and "confirmed" not in f:
            f["confirmed"] = f.get("source") == "manual"
    transcript = body.get("transcript", x.transcript) or []
    x.patient_id, x.form, x.transcript, x.patient_data = p.id, form, transcript, pdata
    x.duration_s = body.get("duration_s", x.duration_s)
    x.status, x.saved_at = "saved", body.get("saved_at") or now()
    x.eva = services.session_eva(form, x.kind)
    x.summary = services.session_summary(form, x.kind)
    x.llm_used = any((f or {}).get("source") in ("llm", "both") for f in form.values())
    if transcript:
        try:
            res = run_pipeline(transcript, mode=x.kind, include_stages=True, confirmed={k: v["value"] for k, v in form.items() if isinstance(v, dict) and v.get("confirmed")})
            for st in res["stages"]:
                if st["id"] == "pos_dep":  # SVGs são regeneráveis; não pesam no banco
                    for g in st["output"].get("sentences_svg", []):
                        g["svg"] = None
            res.pop("fields", None)
            x.pipeline = res
        except Exception as e:  # noqa: BLE001
            x.pipeline = {"error": str(e)}
    s.add(x)
    s.flush()
    audit(s, "salvar_sessao", p.id, x.id, new={"kind": x.kind, "campos": len(form)})
    for fid, f in form.items():
        if isinstance(f, dict) and f.get("source") == "manual":
            audit(s, "campo_manual", p.id, x.id, field=fid, new=f.get("value"), source="manual")
    s.flush()
    services.refresh_patient(s, p)
    s.commit()
    return {"session_id": x.id, "patient_id": p.id}


@app.delete("/api/sessions/{sid}")
def discard_session(sid: int, s: Session = Depends(get_session)):
    x = s.get(ConsultaSession, sid)
    if not x:
        return {"ok": True}
    if x.status == "saved":
        raise HTTPException(409, "Sessões salvas não podem ser descartadas.")
    audit(s, "descartar_rascunho", x.patient_id, sid)
    s.delete(x)
    s.commit()
    return {"ok": True}


def _pdf_response(data: bytes, name: str) -> Response:
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})


@app.get("/api/sessions/{sid}/pdf")
def session_pdf(sid: int, s: Session = Depends(get_session)):
    x = s.get(ConsultaSession, sid)
    if not x:
        raise HTTPException(404)
    p = s.get(Patient, x.patient_id) if x.patient_id else None
    pdata = {**(x.patient_data or {}), **({"alerts": p.alerts} if p else {"alerts": services.compute_alerts(x.form)})}
    if p:
        pdata.update({"name": p.name, "birth_date": p.birth_date, "phone": p.phone, "profession": p.profession})
    data = pdfmod.clinical_pdf(all_settings(s), pdata, [{"kind": x.kind, "date": x.saved_at or x.updated_at, "form": x.form}],
                               "Prontuário — " + ("Anamnese" if x.kind == "anamnese" else "Sessão SOAP"))
    return _pdf_response(data, f"prontuario-sessao-{sid}.pdf")


@app.get("/api/patients/{pid}/pdf")
def patient_pdf(pid: int, s: Session = Depends(get_session)):
    p = s.get(Patient, pid)
    if not p:
        raise HTTPException(404)
    sess = s.exec(select(ConsultaSession).where(ConsultaSession.patient_id == pid, ConsultaSession.status == "saved").order_by(ConsultaSession.saved_at)).all()
    data = pdfmod.clinical_pdf(all_settings(s), patient_dict(p), [{"kind": x.kind, "date": x.saved_at, "form": x.form} for x in sess], "Prontuário completo")
    return _pdf_response(data, f"prontuario-{pid}.pdf")


@app.get("/api/sessions/{sid}/transcript.txt")
def transcript_txt(sid: int, s: Session = Depends(get_session)):
    x = s.get(ConsultaSession, sid)
    if not x:
        raise HTTPException(404)
    txt = "\n".join(f"[{int(u.get('ts', 0)) // 60:02d}:{int(u.get('ts', 0)) % 60:02d}] {u['speaker'].upper()}: {u['text']}" for u in x.transcript)
    return Response(txt, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="transcricao-{sid}.txt"'})


@app.get("/api/sessions-list")
def sessions_list(s: Session = Depends(get_session)):
    """Sessões salvas (para o Laboratório escolher a fonte do texto)."""
    names = {p.id: p.name for p in s.exec(select(Patient)).all()}
    return [{"id": x.id, "patient": names.get(x.patient_id, "?"), "kind": x.kind, "date": x.saved_at[:10], "n_utterances": len(x.transcript)}
            for x in s.exec(select(ConsultaSession).where(ConsultaSession.status == "saved").order_by(ConsultaSession.saved_at.desc())).all()]


# --------------------------------------------------------------------------- Dashboard / Configurações / Backup
@app.get("/api/dashboard")
def dashboard(s: Session = Depends(get_session)):
    today = date.today().isoformat()
    patients = s.exec(select(Patient)).all()
    saved = s.exec(select(ConsultaSession).where(ConsultaSession.status == "saved").order_by(ConsultaSession.saved_at.desc())).all()
    names = {p.id: p.name for p in patients}
    slim = lambda x: {"id": x.id, "patient_id": x.patient_id, "patient": names.get(x.patient_id, "?"), "kind": x.kind, "date": x.saved_at,
                      "summary": x.summary, "eva": x.eva}
    return {"n_patients": len(patients), "n_sessions": len(saved), "today": [slim(x) for x in saved if x.saved_at.startswith(today)],
            "recent": [slim(x) for x in saved[:6]], "drafts": drafts(s), "alerts": [{"id": p.id, "name": p.name, "alerts": p.alerts} for p in patients if p.alerts]}


@app.get("/api/settings")
def get_settings(s: Session = Depends(get_session)):
    return api_status(s)


@app.put("/api/settings")
def put_settings(body: dict = Body(...), s: Session = Depends(get_session)):
    for k in ("clinic_name", "professional_name", "speech_lang", "clinic_address", "clinic_phone"):
        if k in body:
            s.merge(AppSetting(key=k, value=body[k]))
    s.commit()
    return api_status(s)


TABLES = {"patient": Patient, "consulta": ConsultaSession, "auditlog": AuditLog, "appsetting": AppSetting}


@app.get("/api/backup")
def backup(s: Session = Depends(get_session)):
    data = {"app": "prontuario-qi", "version": 1, "exported_at": now(),
            "tables": {n: [r.model_dump() for r in s.exec(select(t)).all()] for n, t in TABLES.items()}}
    return Response(json.dumps(data, ensure_ascii=False, default=str), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="backup-prontuario-{date.today().isoformat()}.json"'})


@app.post("/api/restore")
def restore(body: dict = Body(...), s: Session = Depends(get_session)):
    if body.get("app") != "prontuario-qi":
        raise HTTPException(422, "Arquivo de backup inválido.")
    for t in TABLES.values():
        s.exec(delete(t))
    s.commit()
    for n, t in TABLES.items():
        for row in body["tables"].get(n, []):
            s.add(t(**row))
    s.commit()
    return {"ok": True, "patients": len(body["tables"].get("patient", []))}


# --------------------------------------------------------------------------- Frontend estático (build de produção)
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if f.is_file() else DIST / "index.html")
