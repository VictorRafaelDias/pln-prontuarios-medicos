"""Etapa 6 — Lematização (spaCy) × Stemming (RSLP)."""
from __future__ import annotations

from .. import nltk_utils, spacy_loader
from .base import PipelineState, Stage


class LemmaStemStage(Stage):
    id = "lemma_stem"
    index = 6
    name = "Lematização × Stemming"
    short = "Lema × Stem"
    explain = {
        "what": "Reduz cada palavra à sua forma base de duas maneiras e compara lado a lado: LEMA (spaCy: palavra de dicionário, ex.: \"dores\" → \"dor\", \"fumei\" → \"fumar\") e STEM (RSLP: radical por corte de sufixos, ex.: \"dores\" → \"dor\", \"fumando\" → \"fum\").",
        "why": "Agrupar variações da mesma palavra melhora estatísticas (frequência, TF-IDF) e a similaridade. O lema é legível e linguisticamente correto; o stem é mais agressivo e rápido, mas pode juntar palavras diferentes (\"operação\" e \"operar\") ou deixar radicais ininteligíveis.",
        "how": "O lematizador do spaCy usa regras + a classe gramatical (POS) vinda do morfologizador, por isso roda depois dele. O RSLP (Removedor de Sufixos da Língua Portuguesa) aplica uma cascata de regras de redução de plural, feminino, aumentativo, advérbio, verbo e vogal temática.",
    }

    def run(self, state: PipelineState):
        nlp = spacy_loader.get_nlp()
        groups = spacy_loader.pipe_groups(nlp)
        state.doc = spacy_loader.run_components(nlp, state.doc, groups["lemma"])
        stem, stem_name = nltk_utils.stemmer()
        rows = []
        for t in state.doc:
            if t.is_space:
                continue
            rows.append({"i": t.i, "text": t.text, "lemma": t.lemma_, "stem": stem(t.text.lower()) if t.is_alpha else t.text,
                         "pos": t.pos_, "is_stop": state.tokens[len(rows)].get("is_stop", False) if len(rows) < len(state.tokens) else False})
        for r, tok in zip(rows, state.tokens):
            tok["lemma"], tok["stem"], tok["pos"] = r["lemma"], r["stem"], r["pos"]
        diff = sum(1 for r in rows if r["lemma"].lower() != r["stem"].lower() and r["text"].isalpha())
        return {"rows": rows, "stemmer": stem_name, "components_run": groups["lemma"],
                "n_lemma_changed": sum(1 for r in rows if r["lemma"].lower() != r["text"].lower()),
                "n_lemma_ne_stem": diff}
