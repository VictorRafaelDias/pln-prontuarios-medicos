"""Verificação de integridade e consistência do banco SQLite (somente leitura).

Uso:  .venv/Scripts/python scripts/check_db.py [caminho/do/banco.db]
Sai com código 1 se encontrar qualquer inconsistência.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from nlp.form_schema import FIELD_BY_ID, field_ids_for_mode, normalize_value  # noqa: E402

db = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "backend" / "data" / "prontuario.db"
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
problems: list[str] = []


def bad(msg: str) -> None:
    problems.append(msg)


# 1) integridade física
res = con.execute("PRAGMA integrity_check").fetchone()[0]
if res != "ok":
    bad(f"PRAGMA integrity_check: {res}")

patients = {r["id"]: r for r in con.execute("SELECT * FROM patient")}
sessions = list(con.execute("SELECT * FROM consulta"))
print(f"banco: {db.name} · {len(patients)} pacientes · {len(sessions)} sessões "
      f"({sum(1 for s in sessions if s['status'] == 'saved')} salvas, {sum(1 for s in sessions if s['status'] == 'draft')} rascunhos)")

# 2) pacientes
names = [p["name"].strip().lower() for p in patients.values()]
for p in patients.values():
    if not p["name"].strip():
        bad(f"paciente {p['id']} sem nome")
    if not p["consent_lgpd"]:
        bad(f"paciente {p['id']} ({p['name']}) sem consentimento LGPD")
    if not p["consent_at"]:
        bad(f"paciente {p['id']} sem data de consentimento")

# 3) sessões
for s in sessions:
    sid = s["id"]
    if s["kind"] not in ("anamnese", "soap"):
        bad(f"sessão {sid}: kind inválido {s['kind']!r}")
    if s["status"] not in ("draft", "saved"):
        bad(f"sessão {sid}: status inválido {s['status']!r}")
    if s["status"] == "saved":
        if s["patient_id"] not in patients:
            bad(f"sessão salva {sid}: paciente {s['patient_id']} inexistente (órfã)")
        if not s["saved_at"]:
            bad(f"sessão salva {sid} sem saved_at")
    if s["eva"] is not None and not (0 <= s["eva"] <= 10):
        bad(f"sessão {sid}: EVA fora de 0–10 ({s['eva']})")
    try:
        form = json.loads(s["form"]) if s["form"] else {}
        transcript = json.loads(s["transcript"]) if s["transcript"] else []
        json.loads(s["pipeline"]) if s["pipeline"] else {}
    except json.JSONDecodeError as e:
        bad(f"sessão {sid}: JSON inválido ({e})")
        continue
    allowed = set(field_ids_for_mode(s["kind"])) if s["kind"] in ("anamnese", "soap") else set()
    for fid, f in form.items():
        if fid not in FIELD_BY_ID:
            bad(f"sessão {sid}: campo desconhecido {fid!r}")
            continue
        if fid not in allowed and fid != "habitos.maco_ano":
            bad(f"sessão {sid} ({s['kind']}): campo {fid} não pertence ao modo")
        if not isinstance(f, dict) or "value" not in f:
            bad(f"sessão {sid}: campo {fid} sem estrutura {{value, source...}}")
            continue
        if f["value"] is not False and normalize_value(fid, f["value"]) is None and f["value"] not in (None,):
            bad(f"sessão {sid}: valor inválido para {fid}: {f['value']!r}")
        if f.get("source") not in ("rules", "llm", "both", "manual", "calc"):
            bad(f"sessão {sid}: origem inválida em {fid}: {f.get('source')!r}")
        c = f.get("confidence", 1)
        if not isinstance(c, (int, float)) or not (0 <= c <= 1):
            bad(f"sessão {sid}: confiança fora de 0–1 em {fid}: {c!r}")
    for i, u in enumerate(transcript):
        if u.get("speaker") not in ("profissional", "paciente") or not isinstance(u.get("text"), str):
            bad(f"sessão {sid}: fala {i} inválida")

# 4) resumo do paciente consistente com as sessões salvas
for pid, p in patients.items():
    saved = sorted([s for s in sessions if s["patient_id"] == pid and s["status"] == "saved"], key=lambda s: s["saved_at"])
    if p["session_count"] != len(saved):
        bad(f"paciente {pid}: session_count={p['session_count']} mas há {len(saved)} sessões salvas")
    last_eva = next((s["eva"] for s in reversed(saved) if s["eva"] is not None), None)
    if p["last_eva"] != last_eva:
        bad(f"paciente {pid}: last_eva={p['last_eva']} mas a última EVA salva é {last_eva}")
    if saved and p["last_session_at"] != saved[-1]["saved_at"]:
        bad(f"paciente {pid}: last_session_at desatualizado")
    alerts = set(json.loads(p["alerts"] or "[]"))
    expected = set()
    for s in saved:
        for fid, f in json.loads(s["form"] or "{}").items():
            if fid.startswith("contra.") and isinstance(f, dict) and f.get("value") is True:
                expected.add(FIELD_BY_ID[fid]["alert"])
    if alerts != expected:
        bad(f"paciente {pid}: alertas {sorted(alerts)} ≠ esperados {sorted(expected)}")

# 5) auditoria aponta para entidades existentes
for a in con.execute("SELECT id, patient_id, session_id FROM auditlog"):
    if a["patient_id"] is not None and a["patient_id"] not in patients:
        bad(f"auditlog {a['id']}: paciente {a['patient_id']} inexistente")

if problems:
    print(f"\n✗ {len(problems)} problema(s):")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("✓ banco íntegro e consistente")
