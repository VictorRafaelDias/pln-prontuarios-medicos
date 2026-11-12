"""Casos de borda da API: validação de entrada, escape de caracteres, perda de dados e concorrência."""
import copy
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("PRONTUARIO_DB", str(Path(tempfile.mkdtemp()) / "edge.db"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from nlp.pipeline import run_pipeline  # noqa: E402
from test_invariants import check_invariants  # noqa: E402


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


def U(*pairs):
    return [{"speaker": s, "text": t, "ts": i * 5.0} for i, (s, t) in enumerate(pairs)]


def salvar_sessao(c, nome="Paciente Borda", kind="anamnese", form=None, transcript=None, consent=True):
    s = c.post("/api/sessions", json={"kind": kind, "patient_data": {"name": nome, "consent_lgpd": consent}}).json()
    r = c.post(f"/api/sessions/{s['id']}/save", json={"form": form or {}, "transcript": transcript or [],
                                                       "patient_data": {"name": nome, "consent_lgpd": consent}})
    return s["id"], r


# ------------------------------------------------------------------ o verificador de invariantes realmente detecta corrupção
def test_verificador_de_invariantes_detecta_corrupcao():
    res = run_pipeline(U(("paciente", "Dor no joelho direito nota oito.")), include_stages=True)
    check_invariants(res, "anamnese")
    mutacoes = (
        lambda r: r["entities"][0].update(start=r["entities"][0]["start"] + 1),
        lambda r: r["fields"]["queixa.eva"].update(value=99),
        lambda r: r["fields"]["queixa.eva"].update(confidence=1.7),
        lambda r: r["fields"].update({"campo.falso": {"value": 1, "source": "rules", "confidence": 0.5}}),
        lambda r: r["stages"].pop(),
    )
    for mutate in mutacoes:
        ruim = copy.deepcopy(res)
        mutate(ruim)
        with pytest.raises(AssertionError):
            check_invariants(ruim, "anamnese")


# ------------------------------------------------------------------ ids e validação de entrada
def test_404_para_ids_inexistentes(c):
    assert c.get("/api/patients/99999").status_code == 404
    assert c.get("/api/sessions/99999").status_code == 404
    assert c.put("/api/patients/99999", json={}).status_code == 404
    assert c.get("/api/sessions/99999/pdf").status_code == 404
    assert c.get("/api/patients/99999/pdf").status_code == 404
    assert c.post("/api/sessions", json={"kind": "soap", "patient_id": 99999}).status_code == 404


def test_tipo_de_sessao_invalido_e_rejeitado(c):
    assert c.post("/api/sessions", json={"kind": "foo"}).status_code == 422


def test_modo_invalido_no_pipeline_e_rejeitado(c):
    assert c.post("/api/nlp/process", json={"utterances": U(("paciente", "Dor.")), "mode": "foo"}).status_code == 422
    assert c.post("/api/lab/analyze", json={"text": "Paciente: Dor.", "mode": "foo"}).status_code == 422


def test_entradas_vazias_ou_malformadas(c):
    assert c.post("/api/nlp/process", json={"utterances": []}).json()["fields"] == {}
    assert c.post("/api/nlp/process", json={}).status_code == 200
    assert c.post("/api/lab/analyze", json={}).status_code == 422
    assert c.post("/api/lab/analyze", json={"text": "   \n  "}).status_code == 422
    r = c.post("/api/nlp/process", content="isto não é json", headers={"Content-Type": "application/json"})
    assert r.status_code in (400, 422)
    r = c.post("/api/nlp/process", json={"utterances": [{"speaker": None, "text": None}, {"text": 123}, {"speaker": "x", "text": "Dor nota 5."}]})
    assert r.status_code == 200 and r.json()["fields"]["queixa.eva"]["value"] == 5


@pytest.mark.parametrize("q", ["%", "_", "'", '"', "\\", "日本語", "😀", "a" * 5000, "  ", "dor  lombar   ", "ÁÉÍ"])
def test_busca_com_caracteres_especiais(c, q):
    r = c.get("/api/patients", params={"q": q})
    assert r.status_code == 200 and isinstance(r.json(), list)


# ------------------------------------------------------------------ salvar: regras e sanitização
def test_salvar_exige_nome_e_consentimento(c):
    _, r = salvar_sessao(c, nome="   ")
    assert r.status_code == 422
    _, r = salvar_sessao(c, nome="Sem Consentimento", consent=False)
    assert r.status_code == 422
    assert not any(p["name"] == "Sem Consentimento" for p in c.get("/api/patients").json())


def test_salvar_descarta_campos_desconhecidos_e_valores_invalidos(c):
    form = {
        "queixa.eva": {"value": 99, "source": "manual", "confidence": 1, "confirmed": True},            # EVA > 10 → 10
        "campo.inexistente": {"value": "x", "source": "manual", "confidence": 1},                      # id desconhecido → descartado
        "habitos.tabagismo": {"value": "talvez", "source": "manual", "confidence": 1},                 # opção inválida → descartado
        "contra.gestacao": {"value": True, "source": "bogus", "confidence": 5},                        # origem/confiança inválidas → normalizadas
        "soap.p_pontos": {"value": ["vb 20", "zz99", "E36"], "source": "manual", "confidence": 1},     # pontos normalizados
        "queixa.descricao": "texto solto sem estrutura",                                                # estrutura errada → descartado
    }
    sid, r = salvar_sessao(c, nome="Paciente Sanitizado", form=form)
    assert r.status_code == 200, r.text
    f = c.get(f"/api/sessions/{sid}").json()["form"]
    assert f["queixa.eva"]["value"] == 10
    assert "campo.inexistente" not in f and "habitos.tabagismo" not in f and "queixa.descricao" not in f
    assert f["contra.gestacao"]["source"] in ("rules", "llm", "both", "manual", "calc") and 0 <= f["contra.gestacao"]["confidence"] <= 1
    assert f["soap.p_pontos"]["value"] == ["VB20", "E36"]
    p = c.get(f"/api/patients/{r.json()['patient_id']}").json()
    assert "Gestação" in p["alerts"]


def test_salvar_duas_vezes_nao_duplica_paciente(c):
    sid, r = salvar_sessao(c, nome="Paciente Duplo")
    pid = r.json()["patient_id"]
    r2 = c.post(f"/api/sessions/{sid}/save", json={"form": {}, "transcript": [], "patient_data": {"name": "Paciente Duplo", "consent_lgpd": True}})
    assert r2.status_code == 200 and r2.json()["patient_id"] == pid
    assert sum(1 for p in c.get("/api/patients").json() if p["name"] == "Paciente Duplo") == 1
    assert c.get(f"/api/patients/{pid}").json()["session_count"] == 1


def test_nome_com_marcacao_e_unicode_nao_quebra_pdf_nem_busca(c):
    nome = "Zé <b>Ação</b> & Cia 日本語 😀"
    sid, r = salvar_sessao(c, nome=nome, form={"queixa.descricao": {"value": "Dor <i>forte</i> & constante → piora ≥ 7", "source": "manual", "confidence": 1}})
    assert r.status_code == 200
    pdf = c.get(f"/api/sessions/{sid}/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert c.get(f"/api/patients/{r.json()['patient_id']}/pdf").content[:4] == b"%PDF"
    assert any(p["name"] == nome for p in c.get("/api/patients", params={"q": "cia"}).json())
    assert c.get(f"/api/sessions/{sid}/transcript.txt").status_code == 200


def test_exportacao_html_escapa_marcacao(c):
    a = c.post("/api/lab/analyze", json={"text": "Paciente: Tenho dor <b>forte</b> & nota 8 no joelho."}).json()
    html = c.post("/api/lab/export/html", json=a).text
    assert "<b>forte</b>" not in html and "&lt;b&gt;" in html


def test_atualizar_paciente_valida_nome_e_valores(c):
    _, r = salvar_sessao(c, nome="Paciente Atualizar")
    pid = r.json()["patient_id"]
    assert c.put(f"/api/patients/{pid}", json={"name": "   "}).status_code == 422
    out = c.put(f"/api/patients/{pid}", json={"anamnese": {"queixa.eva": 42, "campo.falso": 1, "habitos.tabagismo": "nunca"}}).json()
    assert out["anamnese"]["queixa.eva"]["value"] == 10 and "campo.falso" not in out["anamnese"]
    assert out["anamnese"]["habitos.tabagismo"]["value"] == "nunca"


def test_sessao_salva_nao_aceita_rascunho_nem_descarte(c):
    sid, _ = salvar_sessao(c, nome="Paciente Imutavel")
    assert c.put(f"/api/sessions/{sid}/draft", json={"form": {}}).status_code == 404
    assert c.delete(f"/api/sessions/{sid}").status_code == 409


# ------------------------------------------------------------------ backup/restauração: nunca perder dados
def test_restauracao_invalida_nao_apaga_o_banco(c):
    antes = c.get("/api/backup").json()
    n = len(antes["tables"]["patient"])
    assert n > 0
    assert c.post("/api/restore", json={"app": "prontuario-qi"}).status_code == 422                                     # sem 'tables'
    assert c.post("/api/restore", json={"app": "prontuario-qi", "tables": "x"}).status_code == 422                      # tipo errado
    ruim = {"app": "prontuario-qi", "tables": {"patient": [{"coluna_inexistente": 1}], "consulta": [], "auditlog": [], "appsetting": []}}
    assert c.post("/api/restore", json=ruim).status_code == 422                                                         # linha inválida
    depois = c.get("/api/backup").json()
    assert len(depois["tables"]["patient"]) == n and len(depois["tables"]["consulta"]) == len(antes["tables"]["consulta"])


def test_backup_ida_e_volta_preserva_tudo(c):
    antes = c.get("/api/backup").json()
    assert c.post("/api/restore", json=antes).status_code == 200
    depois = c.get("/api/backup").json()
    for t in ("patient", "consulta"):
        assert len(depois["tables"][t]) == len(antes["tables"][t])
    assert {p["id"]: p["name"] for p in depois["tables"]["patient"]} == {p["id"]: p["name"] for p in antes["tables"]["patient"]}


# ------------------------------------------------------------------ configurações do laboratório: nunca aceitar o que quebra o pipeline
@pytest.mark.parametrize("nome,corpo", [
    ("negation_triggers", {"pre": "não-é-lista"}),
    ("negation_triggers", {"pre": [{"sem_texto": 1}]}),
    ("negation_triggers", {"pre": [{"text": "não", "window": "muitos"}]}),
    ("negation_triggers", {"uncertainty": [{"text": "talvez", "factor": 7}]}),
    ("negation_triggers", ["lista"]),
    ("stopwords_custom", {"preserve": "x", "extra": []}),
    ("stopwords_custom", {"preserve": {"negacao": "não"}, "extra": []}),
    ("normalization", {"abbreviations": ["x"]}),
    ("normalization", {"filler_regex": ["(regex quebrada"]}),
    ("points", {"meridianos": {}, "pontos": "x"}),
    ("sintomas", {"label": "SINTOMA", "entries": [{"canonical": "x", "variants": "não-lista"}]}),
    ("sintomas", {"label": "SINTOMA", "entries": [{"canonical": "x", "variants": [1, 2]}]}),
    ("sintomas", {"label": "SINTOMA", "entries": "x"}),
])
def test_configuracao_invalida_e_rejeitada_e_pipeline_continua_ok(c, nome, corpo):
    r = c.put(f"/api/lab/resources/{nome}", json=corpo)
    assert r.status_code == 422, (nome, r.status_code, r.text[:200])
    ok = c.post("/api/lab/analyze", json={"text": "Paciente: Não fumo. Dor nota 7."})
    assert ok.status_code == 200 and ok.json()["fields"]["habitos.tabagismo"]["value"] == "nunca"


@pytest.mark.parametrize("nome", ["inexistente", "..", "..%2F..%2Fetc", "negation_triggers.json", "a b", "%00"])
def test_nomes_de_recurso_estranhos_dao_404(c, nome):
    assert c.get(f"/api/lab/resources/{nome}").status_code in (404, 405)
    assert c.put(f"/api/lab/resources/{nome}", json={"label": "X", "entries": []}).status_code in (404, 405, 422)


# ------------------------------------------------------------------ concorrência e tamanho
def test_requisicoes_concorrentes_ao_pipeline(c):
    def chamar(i):
        r = c.post("/api/nlp/process", json={"utterances": U(("paciente", f"Dor nota {i % 10} no joelho. Não fumo."))})
        return r.status_code, r.json()["fields"].get("queixa.eva", {}).get("value")
    with ThreadPoolExecutor(max_workers=12) as ex:
        out = list(ex.map(chamar, range(36)))
    assert all(code == 200 for code, _ in out)
    assert [v for _, v in out] == [i % 10 for i in range(36)]  # cada resposta pertence à sua própria requisição


def test_escritas_concorrentes_de_rascunho(c):
    s = c.post("/api/sessions", json={"kind": "anamnese", "patient_data": {"name": "Rascunho Concorrente"}}).json()

    def salvar(i):
        return c.put(f"/api/sessions/{s['id']}/draft", json={"form": {}, "transcript": U(("paciente", f"fala {i}")), "duration_s": i}).status_code
    with ThreadPoolExecutor(max_workers=8) as ex:
        assert set(ex.map(salvar, range(24))) == {200}
    assert c.get(f"/api/sessions/{s['id']}").json()["status"] == "draft"


def test_transcricao_muito_grande(c):
    fala = "Dor lombar nota seis há três meses, piora de manhã e melhora com calor. "
    import time
    t0 = time.perf_counter()
    r = c.post("/api/nlp/process", json={"utterances": [{"speaker": "paciente", "text": fala * 400, "ts": 0}]})
    assert r.status_code == 200 and r.json()["fields"]["queixa.eva"]["value"] == 6
    assert time.perf_counter() - t0 < 12, "texto longo travou o servidor (diff quadrático?)"
