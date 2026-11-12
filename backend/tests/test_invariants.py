"""Testes de sanidade: invariantes do pipeline em todos os transcritos e fuzz com entradas aleatórias/hostis."""
import json
import random
import sys
import time
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nlp.evaluation import DATASETS, load_gold  # noqa: E402
from nlp.form_schema import FIELD_BY_ID, field_ids_for_mode, normalize_value  # noqa: E402
from nlp.pipeline import run_pipeline  # noqa: E402

SOURCES = {"rules", "llm", "both", "manual", "calc"}


def check_invariants(res: dict, mode: str) -> None:
    text = res["text"]
    # 12 etapas, em ordem, com tempo não negativo
    assert [s["id"] for s in res["stages"]] == ["asr", "normalize", "sentences", "tokens", "stopwords", "lemma_stem", "pos_dep", "ner",
                                                 "negation", "mapping", "llm", "merge"]
    assert all(s["ms"] >= 0 for s in res["stages"])
    json.dumps(res)  # tudo serializável
    # sentenças: ordenadas, sem sobreposição, dentro do texto, e o recorte confere
    last = -1
    for s in res["sentences"]:
        assert 0 <= s["start"] < s["end"] <= len(text) and s["start"] > last
        assert text[s["start"]:s["end"]] == s["text"]
        last = s["end"] - 1
    # entidades: dentro do texto, texto confere, sem sobreposição entre as clínicas
    clin = sorted((e for e in res["entities"] if e["clinical"]), key=lambda e: e["start"])
    for e in res["entities"]:
        assert 0 <= e["start"] < e["end"] <= len(text) and text[e["start"]:e["end"]] == e["text"]
        assert 0 <= e["conf"] <= 1 and e["status"] in ("afirmado", "negado", "passado")
    for a, b in zip(clin, clin[1:]):
        assert a["end"] <= b["start"], f"entidades sobrepostas: {a['text']!r} / {b['text']!r}"
    # campos: ids válidos para o modo, valores válidos para o tipo, confiança e origem coerentes, trecho rastreável
    valid = set(field_ids_for_mode(mode)) | {"habitos.maco_ano"}
    for fid, f in res["fields"].items():
        assert fid in FIELD_BY_ID and fid in valid, fid
        assert f["source"] in SOURCES and 0 <= f["confidence"] <= 1, (fid, f)
        if fid != "habitos.maco_ano":
            assert normalize_value(fid, f["value"]) == f["value"] or f["value"] is False, (fid, f["value"])
        if f.get("evidence") and f["source"] == "rules" and not f.get("items") and fid != "habitos.maco_ano":
            ev = " ".join(f["evidence"].split())
            assert ev.strip(" .?") in text or any(part.strip(" .?") in text for part in ev.split(" | ")), (fid, ev)
    # nunca inventa: sem texto, sem campos
    if not text.strip():
        assert res["fields"] == {}
    # consistência clínica
    f = res["fields"]
    if f.get("habitos.tabagismo", {}).get("value") == "nunca":
        assert "habitos.cigarros_dia" not in f and "habitos.maco_ano" not in f
    if "queixa.eva" in f:
        assert 0 <= f["queixa.eva"]["value"] <= 10


@pytest.mark.parametrize("dataset", list(DATASETS))
def test_invariantes_em_todos_os_transcritos(dataset):
    for t in load_gold(dataset)["transcripts"]:
        utts = [{**u, "ts": i * 5.0} for i, u in enumerate(t["utterances"])]
        res = run_pipeline(utts, mode=t["mode"], include_stages=True, previous_session=t.get("previous"))
        check_invariants(res, t["mode"])


def test_pipeline_e_deterministico():
    t = load_gold("gold")["transcripts"][0]
    utts = [{**u, "ts": i * 5.0} for i, u in enumerate(t["utterances"])]
    a = run_pipeline(utts, mode="anamnese", include_stages=False)
    b = run_pipeline(utts, mode="anamnese", include_stages=False)
    assert a["fields"] == b["fields"] and a["text"] == b["text"]


def test_idempotencia_do_texto_normalizado():
    """Normalizar o texto já normalizado não deve mudar o conteúdo (estabilidade)."""
    t = load_gold("gold")["transcripts"][3]
    utts = [{**u, "ts": i} for i, u in enumerate(t["utterances"])]
    r1 = run_pipeline(utts, include_stages=False)
    r2 = run_pipeline([{"speaker": u["speaker"], "text": u["text"], "ts": u["ts"]} for u in r1["utterances"] if u["text"]], include_stages=False)
    assert r2["text"] == r1["text"]


# ---------------------------------------------------------------------------------------------- fuzz
WORDS = ("dor nota oito dez zero não nunca sem nega fumo fumei parei cigarros por dia há anos meses desde 2020 joelho direito esquerdo lombar "
         "ombro cabeça língua pálida pulso fino VB20 E36 IG4 B12 vitamina mas porém talvez acho que às vezes diabetes pressão alta losartana 50mg "
         "grávida marcapasso alergia látex e ou de do da no na com para pra tipo né aham ... ? ! , ; : - 1,5 litro meio um uma dois duas mil "
         "😀 ñ ç ã é ü 日本語 العربية \t \n <script> & ' \" % _ \\ nota11 dor12 E 36 C5 R3").split()


def rand_utts(rng: random.Random, n: int) -> list[dict]:
    return [{"speaker": rng.choice(["paciente", "profissional", "???", None]),
             "text": " ".join(rng.choice(WORDS) for _ in range(rng.randint(0, 25))), "ts": rng.choice([0, 3.5, -1, None])} for _ in range(n)]


@pytest.mark.parametrize("seed", range(40))
def test_fuzz_nao_quebra_e_mantem_invariantes(seed):
    rng = random.Random(seed)
    utts = rand_utts(rng, rng.randint(0, 12))
    for u in utts:
        u["ts"] = u["ts"] or 0
    mode = rng.choice(["anamnese", "soap"])
    res = run_pipeline(utts, mode=mode, include_stages=True)
    check_invariants(res, mode)


@pytest.mark.parametrize("texto", [
    "", " ", "\n\n\t", "...", "?!?!", "ahn... é... hum...", "😀😀😀", "​​", "a" * 5000, "dor " * 2000,
    "DOR NOTA OITO NO JOELHO DIREITO", "nao fumo e nao bebo", "Dor lombaŕ forte", unicodedata.normalize("NFD", "Não fumo, língua pálida"),
    "<b>dor</b> &amp; <script>alert(1)</script>", "'; DROP TABLE patient; --", "nota 0", "nota 10", "nota 11", "dor 12 de 10", "de 0 a 10",
    "dois mil e vinte e seis", "mil e quinhentos", "cento e cinquenta e seis", "um dia", "uma vez", "zero", "meio litro", "dois anos e meio",
    "não não fumo", "sem dor mas com enjoo", "nega dor, febre e tosse", "não.", "nunca", "sim", "não sei", "vitamina B12 e E 36", "C5 e R3 e P7",
    "VB 20, vb20, Vb-20", "mãe diabética, pai hipertenso", "alergia a nada", "grávida? não grávida",
])
def test_entradas_de_borda_nao_quebram(texto):
    res = run_pipeline([{"speaker": "paciente", "text": texto, "ts": 0}], include_stages=True)
    check_invariants(res, "anamnese")


def test_valores_numericos_invalidos_nao_viram_eva():
    for t in ("nota 11", "dor 12 de 10", "nota de 0 a 10", "nota 99"):
        res = run_pipeline([{"speaker": "paciente", "text": f"Tenho dor. {t}.", "ts": 0}], include_stages=False)
        assert "queixa.eva" not in res["fields"], t
    assert run_pipeline([{"speaker": "paciente", "text": "Dor nota 0.", "ts": 0}], include_stages=False)["fields"]["queixa.eva"]["value"] == 0
    assert run_pipeline([{"speaker": "paciente", "text": "Dor nota 10.", "ts": 0}], include_stages=False)["fields"]["queixa.eva"]["value"] == 10


def test_pontos_falsos_positivos():
    res = run_pipeline([{"speaker": "profissional", "text": "Tome vitamina B12, 2 vezes. E 36 pessoas vieram. Use VB20 e E36.", "ts": 0}], include_stages=False)
    assert res["fields"]["soap.p_pontos"]["value"] == ["VB20", "E36"]


def test_dupla_negacao_e_negacao_isolada_nao_inventam_dados():
    f = run_pipeline([{"speaker": "paciente", "text": "Não.", "ts": 0}], include_stages=False)["fields"]
    assert f == {}
    f = run_pipeline([{"speaker": "paciente", "text": "Nunca.", "ts": 0}], include_stages=False)["fields"]
    assert f == {}


def test_desempenho_transcricao_longa():
    t = load_gold("gold")["transcripts"][0]
    base = [{**u, "ts": i} for i, u in enumerate(t["utterances"])]
    utts = base * 12  # ~200 falas
    t0 = time.perf_counter()
    res = run_pipeline(utts, include_stages=False)
    dt = time.perf_counter() - t0
    assert dt < 20, f"pipeline lento demais: {dt:.1f}s para {len(utts)} falas"
    assert res["fields"]["queixa.eva"]["value"] == 8
