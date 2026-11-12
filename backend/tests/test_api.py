"""Testes de integração da API (FastAPI + SQLite temporário)."""
import os
import sys
import tempfile
from pathlib import Path

# banco temporário ANTES de importar o app
os.environ["PRONTUARIO_DB"] = str(Path(tempfile.mkdtemp()) / "teste.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from nlp import llm as llm_mod  # noqa: E402


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:  # dispara o lifespan: carrega spaCy e popula o seed
        yield client


def utts(*pairs):
    return [{"speaker": s, "text": t, "ts": i * 5.0} for i, (s, t) in enumerate(pairs)]


def test_status_schema_e_selo_sem_chave(c, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    st = c.get("/api/status").json()
    assert st["badge"] == "Somente PLN clássico" and st["spacy"]["model"] == "pt_core_news_md"
    sch = c.get("/api/form-schema").json()
    assert any(f["id"] == "queixa.eva" for f in sch["fields"]) and "lombar" in sch["regions"]
    assert any(p["code"] == "VB20" for p in c.get("/api/points").json())


def test_seed_populado(c):
    d = c.get("/api/dashboard").json()
    assert d["n_patients"] == 5 and d["n_sessions"] == 16
    assert any(x["alerts"] for x in d["alerts"]) and len(d["today"]) >= 1  # datas relativas: há atendimento "de hoje"


def test_busca_de_pacientes_sem_acento_e_por_ponto(c):
    assert any("Marina" in p["name"] for p in c.get("/api/patients", params={"q": "lombar"}).json())
    assert len(c.get("/api/patients", params={"q": "VB34"}).json()) >= 1
    assert c.get("/api/patients", params={"q": "inexistente-xyz"}).json() == []


def test_fluxo_anamnese_salvar_pdf_descartar(c):
    s = c.post("/api/sessions", json={"kind": "anamnese", "patient_data": {"name": "Paciente Teste", "consent_lgpd": False}}).json()
    sid = s["id"]
    assert c.put(f"/api/sessions/{sid}/draft", json={"form": {}, "transcript": [], "duration_s": 5}).json()["ok"]
    # consentimento LGPD é obrigatório
    assert c.post(f"/api/sessions/{sid}/save", json={"form": {}}).status_code == 422
    # nome é obrigatório
    assert c.post(f"/api/sessions/{sid}/save", json={"patient_data": {"name": " ", "consent_lgpd": True}}).status_code == 422
    t = utts(("profissional", "Está grávida?"), ("paciente", "Estou."), ("paciente", "Dor lombar nota seis."))
    r = c.post("/api/nlp/process", json={"utterances": t, "mode": "anamnese"}).json()
    form = {k: {**v, "confirmed": True} for k, v in r["fields"].items()}
    ok = c.post(f"/api/sessions/{sid}/save", json={"form": form, "transcript": t, "patient_data": {"name": "Paciente Teste", "consent_lgpd": True}})
    assert ok.status_code == 200
    pid = ok.json()["patient_id"]
    p = c.get(f"/api/patients/{pid}").json()
    assert "Gestação" in p["alerts"] and p["sessions"][0]["eva"] == 6 and p["main_complaint"].startswith("Dor")
    pdf = c.get(f"/api/sessions/{sid}/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert c.get(f"/api/patients/{pid}/pdf").content[:4] == b"%PDF"
    assert c.delete(f"/api/sessions/{sid}").status_code == 409  # sessão salva não se descarta
    # edição da anamnese gera histórico de alterações
    c.put(f"/api/patients/{pid}", json={"anamnese": {"queixa.eva": 3}})
    assert any(a["field"] == "queixa.eva" for a in c.get(f"/api/patients/{pid}/audit").json())
    # transcrição salva junto com o resultado do pipeline
    full = c.get(f"/api/sessions/{sid}").json()
    assert len(full["transcript"]) == 3 and full["pipeline"]["stages"]


def test_rascunho_descartar(c):
    d = c.post("/api/sessions", json={"kind": "soap", "patient_id": 1}).json()
    assert c.get(f"/api/sessions/{d['id']}").json()["previous"]["eva"] is not None  # resumo da última sessão
    assert c.delete(f"/api/sessions/{d['id']}").json()["ok"]
    assert c.get(f"/api/sessions/{d['id']}").status_code == 404


def test_campos_confirmados_nao_sao_sobrescritos(c):
    t = utts(("paciente", "Dor lombar nota seis."))
    r = c.post("/api/nlp/process", json={"utterances": t, "confirmed": {"queixa.eva": 2}}).json()
    assert "queixa.eva" not in r["fields"]


def test_backup_e_restauracao(c):
    bk = c.get("/api/backup").json()
    n = len(bk["tables"]["patient"])
    assert bk["app"] == "prontuario-qi" and n >= 5
    assert c.post("/api/restore", json={"app": "outro"}).status_code == 422
    assert c.post("/api/restore", json=bk).json()["patients"] == n
    assert c.get("/api/dashboard").json()["n_patients"] == n


def test_laboratorio_analise_exportacao_e_dicionario(c):
    body = {"text": "Profissional: Você fuma?\nPaciente: Nunca fumei. Dor nota oito no joelho direito.", "count_llm_tokens": True}
    a = c.post("/api/lab/analyze", json=body).json()
    assert len(a["stages"]) == 12 and all(s["ms"] >= 0 and "input" in s and "output" in s for s in a["stages"])
    assert a["fields"]["habitos.tabagismo"]["value"] == "nunca" and a["stats"]["term_freq"]
    assert c.post("/api/lab/export/json", json=a).status_code == 200
    html = c.post("/api/lab/export/html", json=a)
    assert html.status_code == 200 and "<mark" in html.text
    assert c.post("/api/lab/export/pdf", json=a).content[:4] == b"%PDF"
    # dicionário editado → reprocessamento imediato
    d = c.get("/api/lab/resources/sintomas").json()
    try:
        d2 = {**d, "entries": d["entries"] + [{"canonical": "bruxismo", "variants": ["bruxismo"], "attrs": {"tema": "musculo"}}]}
        assert c.put("/api/lab/resources/sintomas", json=d2).json()["ok"]
        r = c.post("/api/lab/analyze", json={"text": "Paciente: Tenho bruxismo."}).json()
        assert any(e["canonical"] == "bruxismo" for e in r["entities"])
        assert c.put("/api/lab/resources/sintomas", json={"label": "SINTOMA"}).status_code == 422  # validação
    finally:
        c.put("/api/lab/resources/sintomas", json=d)


def test_avaliacao_e_conjuntos(c):
    sets = {s["id"]: s for s in c.get("/api/lab/datasets").json()}
    assert set(sets) == {"gold", "holdout", "blind"} and sets["blind"]["n"] == 5
    ev = c.post("/api/lab/evaluate", json={"dataset": "blind", "approaches": ["rules"]}).json()
    assert ev["dataset"] == "blind" and 0.8 < ev["approaches"]["rules"]["overall"]["f1"] <= 1


def test_cors_restrito_a_origens_locais(c):
    ok = c.get("/api/status", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in c.get("/api/status", headers={"Origin": "https://site-malicioso.example"}).headers


def test_falha_do_llm_nao_derruba_o_pipeline(c, monkeypatch):
    class Boom:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kw):
                raise RuntimeError("rede indisponível")
        beta = type("B", (), {"messages": messages})()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "teste")
    monkeypatch.setattr(llm_mod, "_client", Boom())
    llm_mod._cache.clear()
    r = c.post("/api/nlp/process", json={"utterances": utts(("paciente", "Dor nota cinco.")), "use_llm": True})
    assert r.status_code == 200
    j = r.json()
    assert "rede indisponível" in j["llm"]["error"] and j["fields"]["queixa.eva"]["source"] == "rules"


def test_editar_gatilhos_de_negacao_reprocessa(c):
    """Editor de gatilhos: um gatilho novo passa a negar entidades imediatamente (sem reiniciar)."""
    original = c.get("/api/lab/resources/negation_triggers").json()
    texto = {"text": "Paciente: Livre de dor no joelho. Nota 3."}
    try:
        antes = c.post("/api/lab/analyze", json=texto).json()
        assert not any(e["negated"] for e in antes["entities"] if e["text"].lower() == "dor")
        novo = {**original, "pre": original["pre"] + [{"text": "livre de", "window": 4}]}
        assert c.put("/api/lab/resources/negation_triggers", json=novo).json()["ok"]
        depois = c.post("/api/lab/analyze", json=texto).json()
        assert any(e["negated"] for e in depois["entities"] if e["text"].lower() == "dor")
    finally:
        c.put("/api/lab/resources/negation_triggers", json=original)


def test_editar_stopwords_preservadas(c):
    original = c.get("/api/lab/resources/stopwords_custom").json()
    try:
        novo = {**original, "preserve": {**original["preserve"], "intensidade": original["preserve"]["intensidade"] + ["bem"]}}
        c.put("/api/lab/resources/stopwords_custom", json=novo)
        a = c.post("/api/lab/analyze", json={"text": "Paciente: Estou bem cansada."}).json()
        sw = next(s for s in a["stages"] if s["id"] == "stopwords")["output"]
        assert any(h["text"].lower() == "bem" for h in sw["preserved_hits"])
    finally:
        c.put("/api/lab/resources/stopwords_custom", json=original)
