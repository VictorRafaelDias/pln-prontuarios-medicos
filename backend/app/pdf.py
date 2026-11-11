"""Geração de PDFs (reportlab): prontuário/sessão clínica e relatório do Laboratório PLN."""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from nlp.form_schema import FIELD_BY_ID, REGIONS, SECTIONS, TECNICAS_LABEL

SAGE = colors.HexColor("#5F7F6A")
TERRA = colors.HexColor("#B9573A")
INK = colors.HexColor("#2F3532")


def _safe(t) -> str:
    t = str(t).replace("→", "->").replace("≥", ">=").replace("≤", "<=").replace("−", "-").replace("×", "x").replace("÷", "/")
    t = t.encode("cp1252", "replace").decode("cp1252")
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_value(fid: str, v) -> str:
    f = FIELD_BY_ID.get(fid, {})
    if v is True:
        return "Sim"
    if v is False:
        return "Não"
    if f.get("type") == "bodymap":
        return ", ".join(REGIONS.get(x, x) for x in v)
    if f.get("type") == "multiselect":
        return ", ".join(f.get("option_labels", {}).get(x, x) for x in v)
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    if f.get("type") == "scale":
        return f"{v}/10"
    if f.get("unit") and f["type"] in ("number", "computed"):
        return f"{v} {f['unit']}"
    return str(v)


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Title"], fontName="Times-Bold", fontSize=18, textColor=SAGE, alignment=0, spaceAfter=2),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Times-Bold", fontSize=12.5, textColor=SAGE, spaceBefore=10, spaceAfter=3),
        "body": ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK),
        "small": ParagraphStyle("small", parent=ss["BodyText"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.grey),
        "alert": ParagraphStyle("alert", parent=ss["BodyText"], fontName="Helvetica-Bold", fontSize=10, textColor=TERRA, leading=13),
        "mono": ParagraphStyle("mono", parent=ss["BodyText"], fontName="Courier", fontSize=8, leading=10),
    }


def _header(story, st, clinic: dict, title: str):
    story.append(Paragraph(_safe(clinic.get("clinic_name", "")), st["h1"]))
    sub = " · ".join(x for x in (clinic.get("clinic_address"), clinic.get("clinic_phone"), "Profissional: " + str(clinic.get("professional_name", ""))) if x)
    story.append(Paragraph(_safe(sub), st["small"]))
    story.append(HRFlowable(width="100%", thickness=1.2, color=SAGE, spaceBefore=4, spaceAfter=6))
    story.append(Paragraph(_safe(title), st["h2"]))


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(2 * cm, 1.2 * cm, "Prontuário Qi — documento gerado em " + datetime.now().strftime("%d/%m/%Y %H:%M") + " · dados sensíveis (LGPD)")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
    canvas.restoreState()


def _section_table(story, st, form: dict, section_ids: list[str]):
    for sec in SECTIONS:
        if sec["id"] not in section_ids:
            continue
        rows = []
        for f in FIELD_BY_ID.values():
            if f["section"] != sec["id"]:
                continue
            fs = form.get(f["id"])
            if not isinstance(fs, dict) or fs.get("value") in (None, "", []):
                continue
            mark = "" if fs.get("confirmed", True) else " (sugestão não confirmada)"
            rows.append([Paragraph(_safe(f["label"]), st["body"]), Paragraph(_safe(fmt_value(f["id"], fs["value"]) + mark), st["body"])])
        if not rows:
            continue
        story.append(Paragraph(_safe(sec["title"]), st["h2"]))
        t = Table(rows, colWidths=[5.2 * cm, 11.8 * cm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDD8CC")),
                               ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F1E6")), ("TOPPADDING", (0, 0), (-1, -1), 3),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(t)


def clinical_pdf(clinic: dict, patient: dict, sessions: list[dict], title: str) -> bytes:
    """sessions: [{kind, date, form, transcript?}] — a anamnese vem primeiro quando existir."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=2 * cm,
                            title=title, author=str(clinic.get("professional_name", "")))
    st = _styles()
    story: list = []
    _header(story, st, clinic, title)
    info = [["Paciente", patient.get("name", ""), "Nascimento", patient.get("birth_date", "")],
            ["Telefone", patient.get("phone", ""), "Profissão", patient.get("profession", "")]]
    t = Table([[Paragraph(_safe(c), st["body"]) for c in r] for r in info], colWidths=[2.4 * cm, 6.6 * cm, 2.4 * cm, 5.6 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F1E6")), ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F5F1E6")),
                           ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CFC8B6")), ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDD8CC"))]))
    story.append(t)
    alerts = patient.get("alerts") or []
    if alerts:
        story.append(Spacer(1, 6))
        box = Table([[Paragraph("ALERTA — CONTRAINDICAÇÕES: " + _safe(", ".join(alerts)), st["alert"])]], colWidths=[17 * cm])
        box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1.2, TERRA), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FBEDE8")),
                                 ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story.append(box)
    for s in sessions:
        story.append(Spacer(1, 8))
        label = "Anamnese e primeira conduta" if s["kind"] == "anamnese" else "Sessão de evolução (SOAP)"
        story.append(Paragraph(_safe(f"{label} — {s.get('date', '')[:10]}"), st["h1"].clone("h1b", fontSize=13, textColor=TERRA)))
        secs = [x["id"] for x in SECTIONS if s["kind"] in x["modes"]]
        _section_table(story, st, s["form"], secs)
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="40%", thickness=0.6, color=INK))
    story.append(Paragraph(_safe(str(clinic.get("professional_name", ""))), st["small"]))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def lab_report_pdf(analysis: dict, clinic_name: str = "Prontuário Qi") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=2 * cm, title="Relatório Laboratório PLN")
    st = _styles()
    story: list = [Paragraph("Relatório do Laboratório PLN", st["h1"]), Paragraph(_safe(clinic_name + " — " + datetime.now().strftime("%d/%m/%Y %H:%M")), st["small"]),
                   HRFlowable(width="100%", thickness=1.2, color=SAGE, spaceBefore=4, spaceAfter=6)]
    story.append(Paragraph("Texto normalizado", st["h2"]))
    story.append(Paragraph(_safe(analysis.get("text", "")), st["body"]))
    story.append(Paragraph("Etapas do pipeline", st["h2"]))
    rows = [["#", "Etapa", "Tempo (ms)"]] + [[str(s.get("index", "")), _safe(s.get("name", s["id"])), f"{s['ms']:.2f}"] for s in analysis["stages"]]
    t = Table(rows, colWidths=[1 * cm, 11 * cm, 4 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), SAGE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CFC8B6"))]))
    story.append(t)
    story.append(Paragraph("Entidades", st["h2"]))
    rows = [["Texto", "Categoria", "Estado", "Regra", "Conf."]]
    for e in analysis["entities"]:
        if e.get("clinical"):
            rows.append([Paragraph(_safe(e["text"]), st["small"]), Paragraph(_safe(e["label"]), st["small"]), e.get("status", ""),
                         Paragraph(_safe(e["rule"][:60]), st["small"]), f"{e['conf']:.2f}"])
    t = Table(rows[:120], colWidths=[3.6 * cm, 3 * cm, 2 * cm, 6.6 * cm, 1.4 * cm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), SAGE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CFC8B6")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(t)
    story.append(Paragraph("Campos preenchidos (fusão)", st["h2"]))
    rows = [["Campo", "Valor", "Origem", "Conf."]]
    for fid, f in analysis["fields"].items():
        rows.append([Paragraph(_safe(FIELD_BY_ID.get(fid, {}).get("label", fid)), st["small"]), Paragraph(_safe(fmt_value(fid, f["value"])), st["small"]),
                     f["source"], f"{f['confidence']:.2f}"])
    t = Table(rows, colWidths=[4.6 * cm, 8.6 * cm, 2 * cm, 1.8 * cm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), SAGE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CFC8B6")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(t)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
