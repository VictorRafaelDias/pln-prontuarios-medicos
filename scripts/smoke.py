"""Smoke test do sistema EM EXECUÇÃO (API + proxy do frontend). Somente leitura, exceto um POST de análise sem persistência.

Uso:  .venv/Scripts/python scripts/smoke.py [http://127.0.0.1:8010]
"""
from __future__ import annotations

import sys
import time

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010").rstrip("/")
c = httpx.Client(base_url=BASE, timeout=60)
falhas: list[str] = []


def check(nome: str, cond: bool, extra: str = "") -> None:
    print(("  ✓ " if cond else "  ✗ ") + nome + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        falhas.append(nome)


def get(url: str, **kw) -> httpx.Response:
    t = time.perf_counter()
    r = c.get(url, **kw)
    r.elapsed_s = time.perf_counter() - t  # type: ignore[attr-defined]
    return r


print(f"Smoke test em {BASE}")
st = get("/api/status")
check("GET /api/status 200 e modelo spaCy carregado", st.status_code == 200 and st.json()["spacy"]["ruler_patterns"] > 1000)
check("selo de modo coerente", st.json()["badge"] in ("Somente PLN clássico", "Híbrido (PLN + LLM)"))
check("a chave da API nunca aparece na resposta", "sk-ant" not in st.text and "api_key" not in st.text.lower().replace("api_key_set", ""))

sch = get("/api/form-schema").json()
check("schema com seções, campos e regiões", len(sch["sections"]) == 11 and len(sch["fields"]) >= 50 and len(sch["regions"]) >= 25)
check("catálogo de pontos", len(get("/api/points").json()) > 80)

dash = get("/api/dashboard")
check("dashboard", dash.status_code == 200 and dash.json()["n_patients"] >= 1)
pats = get("/api/patients").json()
check("lista de pacientes", len(pats) >= 1 and all("search_text" in p for p in pats))
pid = pats[0]["id"]
full = get(f"/api/patients/{pid}")
check("prontuário do paciente", full.status_code == 200 and "sessions" in full.json())
check("PDF do prontuário", get(f"/api/patients/{pid}/pdf").content[:4] == b"%PDF")
sess = full.json()["sessions"]
if sess:
    check("PDF da sessão", get(f"/api/sessions/{sess[0]['id']}/pdf").content[:4] == b"%PDF")
check("backup é JSON válido", get("/api/backup").json()["app"] == "prontuario-qi")
check("settings", get("/api/settings").status_code == 200)
check("demos", len(get("/api/demo/transcripts").json()) >= 10)
check("sessões para o laboratório", get("/api/sessions-list").status_code == 200)

lab = get("/api/lab/stages").json()
check("laboratório lista as 12 etapas", len(lab) == 12 and [s["index"] for s in lab] == list(range(1, 13)))
check("recursos editáveis", len(get("/api/lab/resources").json()) >= 14)
check("3 conjuntos de avaliação", {d["id"] for d in get("/api/lab/datasets").json()} == {"gold", "holdout", "blind"})
r = c.post("/api/lab/analyze", json={"text": "Profissional: Você fuma?\nPaciente: Nunca fumei. Dor nota 8."})
check("análise completa em < 5 s", r.status_code == 200 and len(r.json()["stages"]) == 12 and r.elapsed.total_seconds() < 5)
check("resultado correto (tabagismo=nunca, EVA=8)", r.json()["fields"]["habitos.tabagismo"]["value"] == "nunca" and r.json()["fields"]["queixa.eva"]["value"] == 8)

print("Erros esperados")
check("rota de API desconhecida → 404 em JSON (não HTML)", get("/api/rota-que-nao-existe").status_code == 404 and "json" in get("/api/rota-que-nao-existe").headers["content-type"])
check("paciente inexistente → 404", get("/api/patients/987654").status_code == 404)
for tentativa in ("/..%2f..%2f..%2fREADME.md", "/%2e%2e/%2e%2e/README.md", "/..%5c..%5cREADME.md"):
    t = get(tentativa)
    check(f"path traversal bloqueado ({tentativa})", "Arquitetura do PLN" not in t.text and "prontuario-qi" not in t.text.lower()[:200] or t.status_code in (400, 404))
check("método inválido → 405", c.delete("/api/status").status_code == 405)
check("corpo inválido → 4xx", c.post("/api/nlp/process", content="{{", headers={"Content-Type": "application/json"}).status_code in (400, 422))

if falhas:
    print(f"\n✗ {len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print("  -", f)
    sys.exit(1)
print("\n✓ smoke test OK")
