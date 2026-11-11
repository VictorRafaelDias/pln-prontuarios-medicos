"""Etapa 7 — POS tagging e árvore de dependências (visualização estilo displaCy)."""
from __future__ import annotations

from spacy import displacy

from .. import spacy_loader
from .base import PipelineState, Stage

MAX_SVG_SENTENCES = 40
MAX_SVG_TOKENS = 45


class PosDepStage(Stage):
    id = "pos_dep"
    index = 7
    name = "POS e dependências"
    short = "POS / Dep"
    explain = {
        "what": "Classifica cada palavra gramaticalmente (POS: substantivo, verbo, adjetivo...) e liga cada palavra à que ela modifica (árvore de dependências: sujeito, objeto, modificador...).",
        "why": "A sintaxe ajuda a decidir QUEM modifica QUEM: em \"dor forte no joelho direito\", \"forte\" qualifica \"dor\" e \"direito\" qualifica \"joelho\". Também alimenta a lateralidade, o tempo verbal (fumei × fumo) e a visualização didática.",
        "how": "Parser neural do spaCy (modelo pt_core_news_md). As fronteiras de sentença da etapa 3 são impostas antes do parser (componente sentence_boundaries). As árvores são desenhadas com o displaCy.",
    }

    def run(self, state: PipelineState):
        nlp = spacy_loader.get_nlp()
        groups = spacy_loader.pipe_groups(nlp)
        state.doc = spacy_loader.run_components(nlp, state.doc, groups["dep"])
        rows = []
        for t in state.doc:
            if t.is_space:
                continue
            rows.append({"i": t.i, "text": t.text, "pos": t.pos_, "tag": t.tag_, "dep": t.dep_, "head": t.head.i,
                         "head_text": t.head.text, "morph": str(t.morph)})
        for r, tok in zip(rows, state.tokens):
            tok["dep"], tok["head"] = r["dep"], r["head"]
        svgs = []
        opts = {"compact": True, "distance": 85, "bg": "transparent", "color": "currentColor", "font": "Inter, sans-serif",
                "arrow_stroke": 1.5, "arrow_width": 6, "word_spacing": 32}
        for s in state.doc.sents:
            if len(svgs) >= MAX_SVG_SENTENCES:
                break
            n = len([t for t in s if not t.is_space])
            if n > MAX_SVG_TOKENS or n < 2:
                svgs.append({"sent": len(svgs), "text": s.text, "svg": None, "note": "sentença longa demais para o desenho" if n > 2 else ""})
                continue
            try:
                svg = displacy.render(s.as_doc(), style="dep", options=opts, page=False, minify=True)
            except Exception as e:  # noqa: BLE001 — a visualização nunca deve derrubar o pipeline
                svg, _ = None, e
            svgs.append({"sent": len(svgs), "text": s.text, "svg": svg})
        # contagem de classes gramaticais
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["pos"]] = counts.get(r["pos"], 0) + 1
        return {"rows": rows, "pos_counts": counts, "sentences_svg": svgs, "components_run": groups["dep"],
                "n_sentences_parsed": len(list(state.doc.sents))}
