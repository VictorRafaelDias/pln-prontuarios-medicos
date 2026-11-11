"""Testes automatizados por etapa do pipeline de PLN (negação, números e NER em destaque)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nlp import llm as llm_mod  # noqa: E402
from nlp.evaluation import run_evaluation  # noqa: E402
from nlp.numbers import words_to_digits  # noqa: E402
from nlp.pipeline import run_pipeline  # noqa: E402
from nlp.stages.s12_merge import merge_fields  # noqa: E402


def run(texts, mode="anamnese", **kw):
    utts = [{"speaker": s, "text": t, "ts": i * 5.0} for i, (s, t) in enumerate(texts)]
    return run_pipeline(utts, mode=mode, include_stages=True, **kw)


def stage(res, sid):
    return next(s for s in res["stages"] if s["id"] == sid)["output"]


def fields(res):
    return {k: v["value"] for k, v in res["fields"].items()}


# ------------------------------------------------------------------ 1/2 entrada e normalização
def test_asr_rotulos_e_timestamp():
    r = run([("Profissional", "Olá"), ("P", "Bom dia")])
    out = stage(r, "asr")
    assert [u["speaker"] for u in out["utterances"]] == ["profissional", "paciente"]
    assert out["utterances"][1]["ts"] == 5.0


@pytest.mark.parametrize("raw,esperado", [
    ("dez cigarros", "10 cigarros"), ("uns três meses", "3 meses"), ("vinte e cinco anos", "25 anos"),
    ("dois mil e vinte", "2020"), ("um litro e meio de água", "1,5 litro de água"), ("meia hora", "30 minutos"),
    ("uma dor forte", "uma dor forte"), ("um maço por dia", "1 maço por dia"), ("nota oito", "nota 8"),
    ("cento e dez", "110"), ("de zero a dez", "de 0 a 10"),
])
def test_numeros_por_extenso(raw, esperado):
    assert words_to_digits(raw) == esperado


def test_normalizacao_remove_oralidade_e_expande_abreviacoes():
    r = run([("paciente", "é... tipo assim, vc sabe, né, eu tenho HAS há uns dez anos")])
    t = stage(r, "normalize")["utterances"][0]["text"]
    assert "né" not in t.lower() and "tipo" not in t.lower() and "é..." not in t
    assert "você" in t.lower() and "hipertensão arterial sistêmica" in t and "10 anos" in t


def test_normalizacao_preserva_tipo_de():
    r = run([("paciente", "qual o tipo de dor? tipo dois")])
    assert "tipo de dor" in stage(r, "normalize")["utterances"][0]["text"]


# ------------------------------------------------------------------ 3/4 sentenças e tokens
def test_sentencas_respeitam_fronteira_de_fala():
    r = run([("profissional", "Você fuma?"), ("paciente", "Não. Parei.")])
    sents = stage(r, "sentences")["sentences"]
    assert [s["speaker"] for s in sents] == ["profissional", "paciente", "paciente"]


def test_tokens_com_posicao():
    r = run([("paciente", "Dor no joelho.")])
    toks = stage(r, "tokens")["tokens"]
    assert toks[0]["text"] == "Dor" and toks[0]["start"] == 0 and toks[0]["end"] == 3
    assert stage(r, "tokens")["llm_tokens"]["available"] in (True, False)


# ------------------------------------------------------------------ 5/6/7 stopwords, lema/stem, POS
def test_stopwords_preservam_negacao_e_intensidade():
    r = run([("paciente", "Eu não fumo e tenho muito pouco apetite.")])
    out = stage(r, "stopwords")
    removed = {t["text"].lower() for t in out["removed"]}
    saved = {t["text"].lower() for t in out["preserved_hits"]}
    assert {"não", "muito", "pouco"} <= saved
    assert not ({"não", "muito", "pouco"} & removed)
    assert "eu" in removed


def test_lema_e_stem_lado_a_lado():
    r = run([("paciente", "As dores aumentaram.")])
    rows = {x["text"].lower(): x for x in stage(r, "lemma_stem")["rows"]}
    assert rows["dores"]["lemma"] == "dor"
    assert rows["dores"]["stem"] == "dor"


def test_pos_e_dependencias():
    r = run([("paciente", "Sinto dor forte no joelho direito.")])
    out = stage(r, "pos_dep")
    assert any(x["pos"] == "VERB" for x in out["rows"]) and all("dep" in x for x in out["rows"])
    assert out["sentences_svg"] and out["sentences_svg"][0]["svg"].startswith("<svg")


# ------------------------------------------------------------------ 8 NER
def ents(res):
    return [(e["label"], e["text"].lower()) for e in res["entities"]]


def test_ner_dicionario_e_regex():
    r = run([("paciente", "Tenho dor lombar há 3 meses, nota 8, e fumo 10 cigarros por dia.")])
    e = ents(r)
    assert ("SINTOMA", "dor lombar") in e
    assert any(l == "TEMPO" and "3 meses" in t for l, t in e)
    assert ("INTENSIDADE", "nota 8") in e
    assert any(l == "FREQUENCIA" and "10 cigarros por dia" in t for l, t in e)


def test_ner_pontos_de_acupuntura():
    r = run([("profissional", "Vou usar VB20, E36 e IG4. Vitamina B12 também.")])
    pts = [t for l, t in ents(r) if l == "PONTO"]
    assert pts == ["vb20", "e36", "ig4"]  # B12 de "vitamina B12" não é ponto


def test_ner_mtc_lingua_pulso_padrao():
    r = run([("profissional", "Língua pálida com saburra branca, pulso fino. Estagnação de qi do fígado.")])
    f = fields(r)
    assert f["mtc.lingua"].lower().startswith("pálida") and f["mtc.pulso"].lower() == "fino"
    assert any("estagnação de qi" in x.lower() for x in f["mtc.padroes"])


def test_ner_dicionario_reload(tmp_path):
    from nlp import resources, spacy_loader
    d = resources.get_resource_file("sintomas")
    d2 = {**d, "entries": d["entries"] + [{"canonical": "bruxismo", "variants": ["bruxismo", "ranger os dentes"], "attrs": {"tema": "musculo"}}]}
    original = resources.get_resource_file("sintomas")
    try:
        resources.save_resource_file("sintomas", d2)
        spacy_loader.reload_ruler()
        assert ("SINTOMA", "bruxismo") in ents(run([("paciente", "Tenho bruxismo.")]))
    finally:
        resources.save_resource_file("sintomas", original)
        spacy_loader.reload_ruler()


# ------------------------------------------------------------------ 9 negação / incerteza / estados
@pytest.mark.parametrize("texto,esperado", [
    ("Eu não fumo.", "nunca"), ("Nunca fumei.", "nunca"), ("Parei de fumar há 2 anos.", "ex"),
    ("Não fumo mais.", "ex"), ("Sou ex-fumante.", "ex"), ("Fumo 10 cigarros por dia.", "atual"), ("Fumava 20 cigarros por dia.", "ex"),
])
def test_tabagismo_negacao_e_estados(texto, esperado):
    assert fields(run([("paciente", texto)])).get("habitos.tabagismo") == esperado


def test_negacao_escopo_e_termino():
    r = run([("paciente", "Não tenho diabetes mas tenho pressão alta.")])
    st = {e["text"].lower(): e for e in r["entities"] if e["label"] == "DOENCA"}
    assert st["diabetes"]["negated"] and not st["pressão alta"]["negated"]
    assert fields(r)["contra.diabetes"] is False
    assert fields(r)["saude.doencas"] == ["Hipertensão"]


def test_pseudo_negacao_nao_nega():
    r = run([("paciente", "Não só tenho dor no joelho como também no ombro.")])
    dor = [e for e in r["entities"] if e["text"].lower() == "dor"]
    assert dor and not dor[0]["negated"]


def test_incerteza_reduz_confianca():
    r1 = run([("paciente", "Tenho gastrite.")])
    r2 = run([("paciente", "Acho que tenho gastrite.")])
    c1 = r1["fields"]["saude.doencas"]["confidence"]
    c2 = r2["fields"]["saude.doencas"]["confidence"]
    assert c2 < c1 and r2["fields"]["saude.doencas"]["uncertain"]


def test_negacao_posposta_e_resposta_curta_qa():
    r = run([("profissional", "Está grávida?"), ("paciente", "Não."), ("profissional", "Toma anticoagulante?"), ("paciente", "Tomo sim.")])
    f = fields(r)
    assert f["contra.gestacao"] is False and f["contra.anticoagulantes"] is True


# ------------------------------------------------------------------ 10 mapeamento
def test_mapeamento_eva_inicio_localizacao():
    r = run([("profissional", "O que sente?"), ("paciente", "Dor no joelho direito há 3 meses, nota 7, piora de manhã e melhora com calor.")])
    f = fields(r)
    assert f["queixa.eva"] == 7 and f["queixa.localizacao"] == ["joelho_d"]
    assert f["queixa.inicio"] == "Há 3 meses" and f["queixa.horario_pior"] == "manhã" and f["queixa.melhora"] == ["Calor"]


def test_mapeamento_resposta_numerica_a_pergunta_de_escala():
    r = run([("profissional", "De zero a dez, qual a intensidade da dor?"), ("paciente", "Sete.")])
    assert fields(r)["queixa.eva"] == 7


def test_mapeamento_sem_inventar():
    assert fields(run([("paciente", "Bom dia, tudo bem?")])) == {}


def test_maco_ano_calculado():
    r = run([("paciente", "Fumei vinte cigarros por dia durante dez anos.")])
    assert fields(r)["habitos.maco_ano"] == 10.0


def test_modo_soap_traduz_campos():
    r = run([("paciente", "Melhorei, nota três."), ("profissional", "Língua pálida. Vou usar E36 e BP6, vinte minutos.")], mode="soap")
    f = fields(r)
    assert f["soap.s_eva"] == 3 and f["soap.p_pontos"] == ["E36", "BP6"] and f["soap.o_lingua"].lower() == "pálida"
    assert "queixa.eva" not in f


# ------------------------------------------------------------------ 11/12 LLM (cliente falso) e fusão
class _Block:
    type = "text"

    def __init__(self, t):
        self.text = t


class _Resp:
    stop_reason = "end_turn"

    class usage:
        input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = 1000, 200, 0, 0

    def __init__(self, text):
        self.content = [_Block(text)]


class _FakeMessages:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def create(self, **kw):
        self.calls.append(kw)
        return _Resp(self.payload)


class _FakeClient:
    def __init__(self, payload):
        self.messages = _FakeMessages(payload)
        self.beta = type("B", (), {"messages": self.messages})()


def test_llm_extracao_estruturada_e_fusao(monkeypatch):
    import json
    payload = json.dumps({"campos": [
        {"campo": "queixa.eva", "valor": 8, "confianca": 0.9, "trecho": "nota oito"},
        {"campo": "habitos.sono", "valor": "Sono fragmentado", "confianca": 0.8, "trecho": "acordo várias vezes"},
        {"campo": "campo.inexistente", "valor": "x", "confianca": 1, "trecho": ""},
        {"campo": "queixa.descricao", "valor": "ignorado (confirmado)", "confianca": 1, "trecho": ""},
    ]})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "teste")
    fake = _FakeClient(payload)
    monkeypatch.setattr(llm_mod, "_client", fake)
    llm_mod._cache.clear()
    r = run([("paciente", "Dor lombar nota oito. Acordo várias vezes de noite.")], use_llm=True, confirmed={"queixa.descricao": "Dor lombar"})
    f = r["fields"]
    assert f["queixa.eva"]["source"] == "both" and f["queixa.eva"]["confidence"] > 0.95
    assert f["habitos.sono"]["source"] in ("llm", "both")
    assert "queixa.descricao" not in f and "campo.inexistente" not in f  # confirmado e inválido nunca entram
    call = fake.messages.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema" and "tool_choice" not in call
    assert r["llm"]["usage"]["input_tokens"] == 1000 and r["llm"]["cost_usd"] > 0


def test_fusao_prioridades():
    rules = {"queixa.eva": {"value": 8, "confidence": 0.95, "evidence": "", "rule": "regex:intensidade_nota", "source": "rules", "alternatives": []},
             "contra.gestacao": {"value": False, "confidence": 0.8, "evidence": "", "rule": "x", "source": "rules", "alternatives": []}}
    llm_f = {"queixa.eva": {"value": 5, "confidence": 0.9, "evidence": "", "source": "llm"},
             "contra.gestacao": {"value": True, "confidence": 0.7, "evidence": "", "source": "llm"}}
    m, _ = merge_fields(rules, llm_f, set())
    assert m["queixa.eva"]["value"] == 8 and m["queixa.eva"]["conflict"]          # P5: regra numérica explícita vence
    assert m["contra.gestacao"]["value"] is True and m["contra.gestacao"]["conflict"]  # P4: segurança primeiro
    m2, _ = merge_fields(rules, llm_f, {"queixa.eva"})
    assert "queixa.eva" not in m2                                                  # P1: confirmado nunca é sobrescrito


def test_sem_chave_pipeline_classico(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = run([("paciente", "Dor nota 5.")], use_llm=True)
    assert stage(r, "llm")["skipped"] and r["fields"]["queixa.eva"]["source"] == "rules"


# ------------------------------------------------------------------ avaliação
def test_avaliacao_gold_standard():
    ev = run_evaluation(["rules"])
    a = ev["approaches"]["rules"]
    assert ev["n_transcripts"] == 10 and a["overall"]["f1"] > 0.8 and a["fields"] and a["confusion"]
