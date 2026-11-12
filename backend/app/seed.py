"""Dados de demonstração: 5 pacientes FICTÍCIOS com anamnese e sessões SOAP (já populam o sistema na primeira execução)."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Session

from nlp.evaluation import load_gold
from nlp.pipeline import run_pipeline

from . import services
from .db import ConsultaSession, Patient, audit

PATIENTS = [
    # gold_id, nome, nascimento, telefone, e-mail, profissão
    ("G01", "Marina Albuquerque", "1974-03-14", "(11) 90000-0101", "marina.fict@example.com", "Professora", "F"),
    ("G02", "João Pedro Siqueira", "1988-09-02", "(11) 90000-0102", "joao.fict@example.com", "Analista de sistemas", "M"),
    ("G03", "Helena Tavares", "1997-06-21", "(11) 90000-0103", "helena.fict@example.com", "Designer", "F"),
    ("G04", "Carlos Eduardo Lemos", "1965-01-30", "(11) 90000-0104", "carlos.fict@example.com", "Comerciante", "M"),
    ("G05", "Beatriz Nogueira", "1982-11-08", "(11) 90000-0105", "beatriz.fict@example.com", "Advogada", "F"),
]
def d(days_ago: int, hh: int = 9, mm: int = 30) -> str:
    """Datas RELATIVAS a hoje, para o demo sempre ter histórico recente e um atendimento 'de hoje'."""
    return (datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0) - timedelta(days=days_ago)).isoformat(timespec="seconds")


ANAMNESE_DATES = {"G01": d(92), "G02": d(70, 14, 0), "G03": d(63, 10, 15), "G04": d(42, 16, 30), "G05": d(35, 11, 0)}
SOAP_GOLD = {"G06": ("G01", d(16)), "G07": ("G02", d(29, 14, 0)), "G08": ("G03", d(21, 10, 15))}
# sessões SOAP geradas: (gold_id do paciente, data, EVA, relato, pontos, técnica, minutos, evolução)
GENERATED = [
    ("G01", d(78), 7, "A dor lombar deu uma aliviada, nota 7.", ["B23", "B25", "E36"], "sistemica", 20, "Melhora relatada pelo paciente"),
    ("G01", d(57), 5, "Estou melhor, a dor está em nota 5 e acordo menos de madrugada.", ["B23", "VB30", "BP6"], "eletroacupuntura", 25, "Melhora relatada pelo paciente"),
    ("G02", d(56, 14, 0), 7, "A dor de cabeça segue em nota 7, mas só uma crise na semana.", ["VG20", "VB20", "IG4"], "auriculoterapia", 20, "Quadro estável, sem mudança relatada"),
    ("G03", d(49, 10, 15), 6, "O pescoço continua tenso, nota 6.", ["VB21", "VB20", "ID3"], "auriculoterapia", 20, "Quadro estável, sem mudança relatada"),
    ("G04", d(28, 16, 30), 6, "O joelho melhorou um pouco, nota 6.", ["E35", "E34", "VB34", "BP9"], "eletroacupuntura", 30, "Melhora relatada pelo paciente"),
    ("G04", d(0, 8, 30), 5, "Consigo subir escada com menos dor, nota 5.", ["E35", "E36", "VB34", "IG11"], "eletroacupuntura", 30, "Melhora relatada pelo paciente"),
    ("G05", d(21, 11, 0), 6, "A ansiedade segue forte, nota 6, mas dormi melhor.", ["PC6", "C7", "VG20"], "auriculoterapia", 20, "Melhora relatada pelo paciente"),
    ("G05", d(9, 11, 0), 4, "Estou mais calma, nota 4.", ["PC6", "C7", "F3", "VC17"], "sistemica", 25, "Melhora relatada pelo paciente"),
]


def _form(gold: dict) -> dict:
    return {fid: {"value": v, "source": "manual", "confidence": 1.0, "evidence": "", "confirmed": True} for fid, v in gold.items()}


def _pipeline(utts, kind):
    try:
        res = run_pipeline(utts, mode=kind, include_stages=True)
        for st in res["stages"]:
            if st["id"] == "pos_dep":
                for g in st["output"].get("sentences_svg", []):
                    g["svg"] = None
        res.pop("fields", None)
        return res
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def _add_session(s: Session, p: Patient, kind: str, date: str, utts: list[dict], form: dict) -> ConsultaSession:
    transcript = [{"speaker": u["speaker"], "text": u["text"], "ts": i * 6.0} for i, u in enumerate(utts)]
    x = ConsultaSession(patient_id=p.id, kind=kind, status="saved", started_at=date, saved_at=date, updated_at=date, duration_s=len(utts) * 25,
                        patient_data={"name": p.name}, form=form, transcript=transcript, pipeline=_pipeline(transcript, kind))
    x.eva = services.session_eva(form, kind)
    x.summary = services.session_summary(form, kind)
    s.add(x)
    s.flush()
    return x


def seed(s: Session) -> None:
    gold = {t["id"]: t for t in load_gold()["transcripts"]}
    by_gold: dict[str, Patient] = {}
    for gid, name, birth, phone, email, prof, sex in PATIENTS:
        p = Patient(name=name, birth_date=birth, phone=phone, email=email, profession=prof, sex=sex, consent_lgpd=True, consent_at=ANAMNESE_DATES[gid])
        s.add(p)
        s.flush()
        by_gold[gid] = p
        t = gold[gid]
        _add_session(s, p, "anamnese", ANAMNESE_DATES[gid], t["utterances"], _form(t["gold"]))
        audit(s, "criar_paciente", p.id, source="seed")
    for sgid, (pgid, date) in SOAP_GOLD.items():
        t = gold[sgid]
        _add_session(s, by_gold[pgid], "soap", date, t["utterances"], _form(t["gold"]))
    for pgid, date, eva, relato, pontos, tec, mins, evo in GENERATED:
        utts = [{"speaker": "paciente", "text": relato},
                {"speaker": "profissional", "text": f"Hoje vou usar {', '.join(pontos[:-1])} e {pontos[-1]}, por {mins} minutos."}]
        form = _form({"soap.s_relato": relato, "soap.s_eva": eva, "soap.a_evolucao": evo, "soap.p_pontos": pontos, "soap.p_tecnica": [tec], "soap.p_tempo": mins})
        _add_session(s, by_gold[pgid], "soap", date, utts, form)
    s.flush()
    for p in by_gold.values():
        services.refresh_patient(s, p)
    s.commit()
