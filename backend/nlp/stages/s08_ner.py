"""Etapa 8 — NER clínico híbrido: modelo spaCy + EntityRuler (dicionários JSON) + regex."""
from __future__ import annotations

import re

from .. import ner_regex, resources, spacy_loader
from ..form_schema import fold
from .base import PipelineState, Stage

CLINICAL_LABELS = {
    "PARTE_CORPO", "SINTOMA", "TIPO_DOR", "DOENCA", "MEDICAMENTO", "HABITO", "MTC", "PONTO", "TECNICA", "HORARIO",
    "CONDICAO", "CIRURGIA", "FAMILIAR", "ALERGENO", "INTENSIDADE", "FREQUENCIA", "TEMPO", "DOSE",
}
LABEL_TITLES = {
    "PARTE_CORPO": "Parte do corpo", "SINTOMA": "Sintoma", "TIPO_DOR": "Tipo de dor", "DOENCA": "Doença",
    "MEDICAMENTO": "Medicamento", "HABITO": "Hábito", "MTC": "Termo de MTC", "PONTO": "Ponto de acupuntura",
    "TECNICA": "Técnica", "HORARIO": "Horário", "CONDICAO": "Condição / contraindicação", "CIRURGIA": "Cirurgia",
    "FAMILIAR": "Familiar", "ALERGENO": "Alérgeno", "INTENSIDADE": "Intensidade", "FREQUENCIA": "Frequência / quantidade",
    "TEMPO": "Tempo", "DOSE": "Dose", "PER": "Pessoa (spaCy)", "LOC": "Local (spaCy)", "ORG": "Organização (spaCy)",
    "MISC": "Outro (spaCy)",
}
# camadas: quanto menor, maior a prioridade ao resolver sobreposições
_PRIORITY = {"regex": 0, "ruler": 1, "spacy": 2}


def _overlaps(a: dict, b: dict) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


def resolve_overlaps(ents: list[dict]) -> list[dict]:
    """Mantém um conjunto sem sobreposição. O NER estatístico do spaCy só preenche o que sobrar; entre regex e
    dicionário vence o trecho mais longo (em empate, regex > dicionário)."""
    order = sorted(ents, key=lambda e: (1 if e["source"] == "spacy" else 0, -(e["end"] - e["start"]), _PRIORITY[e["source"]], e["start"]))
    kept: list[dict] = []
    for e in order:
        if any(_overlaps(e, k) for k in kept):
            continue
        kept.append(e)
    return sorted(kept, key=lambda e: e["start"])


def _contextual_mtc(text: str, ents: list[dict], sentences: list[dict]) -> list[dict]:
    """Descrição de língua/pulso: frase que segue a âncora ("língua pálida com saburra branca")."""
    desc_l = {w for t in resources.descriptor_lexicon("desc_lingua") for w in t.split()}
    desc_p = {w for t in resources.descriptor_lexicon("desc_pulso") for w in t.split()}
    out = []
    for e in ents:
        cat = e.get("attrs", {}).get("categoria")
        if e["label"] != "MTC" or cat not in ("ancora_lingua", "ancora_pulso"):
            continue
        sent = next((s for s in sentences if s["start"] <= e["end"] <= s["end"] + 1), None)
        if not sent:
            continue
        seg = text[e["end"]:sent["end"]]
        cut = re.search(r"(?<!\w)(?:e\s+)?(?:o\s+|a\s+)?(?:pulsos?|l[ií]ngua)(?!\w)|[.;?!]", seg, re.I)
        phrase = seg[:cut.start()] if cut else seg
        lead = re.match(r"^(?:\s*(?:[:,\-–]|\b(?:é|está|estava|estão|são|apresenta|mostra|se apresenta)\b|\bcom\b))+\s*", phrase, re.I)
        off = lead.end() if lead else 0
        core = phrase[off:]
        off += len(core) - len(core.lstrip())
        core = core.lstrip()
        stripped = core.rstrip(" ,;:-")
        stripped = re.sub(r"\s+e$", "", stripped)
        if len(stripped.strip()) < 3:
            continue
        words = {fold(w) for w in re.findall(r"\w+", stripped)}
        lex = desc_l if cat == "ancora_lingua" else desc_p
        hit = bool(words & lex)
        if cat == "ancora_pulso" and not hit:
            continue
        if cat == "ancora_lingua" and not hit and len(words) > 6:
            continue
        start = e["end"] + off
        out.append({"start": start, "end": start + len(stripped), "label": "MTC", "canonical": stripped.strip(),
                    "source": "regex", "rule": f"regex:mtc_{'lingua' if cat == 'ancora_lingua' else 'pulso'}_descricao",
                    "conf": 0.9 if hit else 0.55,
                    "attrs": {"categoria": "lingua_desc" if cat == "ancora_lingua" else "pulso_desc", "lexicon_hit": hit}})
    return out


class NerStage(Stage):
    id = "ner"
    index = 8
    name = "NER clínico híbrido"
    short = "NER"
    explain = {
        "what": "Reconhece entidades clínicas no texto: partes do corpo, sintomas, tipos de dor, medicamentos, doenças, hábitos, termos de MTC (língua, pulso, padrões), pontos de acupuntura (VB20, E36...), além de intensidade (\"nota 8\"), frequência (\"10 cigarros por dia\") e tempo (\"há 3 meses\", \"desde 2020\").",
        "why": "O modelo estatístico do spaCy foi treinado em textos gerais (pessoas, lugares, organizações) e não conhece \"VB20\" nem \"estagnação de qi\". Por isso a abordagem é HÍBRIDA: EntityRuler com dicionários JSON editáveis (precisão e controle) + expressões regulares para valores numéricos + NER estatístico do spaCy como camada geral.",
        "how": "1) clinical_ruler (EntityRuler com padrões gerados dos dicionários, singular/plural e com/sem acento) → 2) NER estatístico do spaCy → 3) regex para números, tempo, pontos e padrões de MTC → 4) resolução de sobreposições: regex > dicionário > spaCy, preferindo o trecho mais longo. Cada entidade guarda a REGRA que a disparou.",
    }

    def run(self, state: PipelineState):
        nlp = spacy_loader.get_nlp()
        groups = spacy_loader.pipe_groups(nlp)
        doc = spacy_loader.run_components(nlp, state.doc, groups["ner"])
        state.doc = doc
        index = spacy_loader.ruler_index()
        ents: list[dict] = []
        for e in doc.ents:
            if e.ent_id_ and e.ent_id_ in index:
                info = index[e.ent_id_]
                ents.append({"start": e.start_char, "end": e.end_char, "label": info["label"], "canonical": info["canonical"],
                             "source": "ruler", "rule": f"dicionário:{info['dict']} → {info['canonical']}", "conf": 0.9,
                             "attrs": dict(info["attrs"])})
            else:
                ents.append({"start": e.start_char, "end": e.end_char, "label": e.label_, "canonical": e.text, "source": "spacy",
                             "rule": f"spaCy NER ({spacy_loader.MODEL_NAME})", "conf": 0.6, "attrs": {}})
        rx = ner_regex.regex_entities(state.text)
        ctx = _contextual_mtc(state.text, ents, state.sentences)
        final = resolve_overlaps(ents + rx + ctx)
        # enriquecimento
        out = []
        for k, e in enumerate(final):
            span = doc.char_span(e["start"], e["end"], alignment_mode="expand")
            sent = state.sentence_of(e["start"])
            tok_start, tok_end = (span.start, span.end) if span is not None else (None, None)
            lemma = " ".join(t.lemma_ for t in span) if span is not None else e["canonical"]
            rec = {"id": k, "text": state.text[e["start"]:e["end"]], "start": e["start"], "end": e["end"],
                   "tok_start": tok_start, "tok_end": tok_end, "label": e["label"],
                   "title": LABEL_TITLES.get(e["label"], e["label"]), "canonical": e["canonical"], "lemma": lemma,
                   "source": e["source"], "rule": e["rule"], "conf": e["conf"], "attrs": e["attrs"],
                   "sent": sent["idx"] if sent else None, "utt": sent["utt"] if sent else None,
                   "speaker": sent["speaker"] if sent else None, "clinical": e["label"] in CLINICAL_LABELS}
            out.append(rec)
        state.entities = out
        by_label: dict[str, int] = {}
        for e in out:
            by_label[e["label"]] = by_label.get(e["label"], 0) + 1
        by_source: dict[str, int] = {}
        for e in out:
            by_source[e["source"]] = by_source.get(e["source"], 0) + 1
        return {
            "entities": out, "by_label": by_label, "by_source": by_source,
            "ruler_patterns": len(nlp.get_pipe("clinical_ruler").patterns),
            "regex_rules": ner_regex.rule_catalog(),
            "label_titles": LABEL_TITLES,
        }
