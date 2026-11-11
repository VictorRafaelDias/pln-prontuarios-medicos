"""Etapa 3 — Segmentação de sentenças."""
from __future__ import annotations

import re

from .base import PipelineState, Stage

_SPLIT = re.compile(r"(?<=[.!?])\s+(?=\S)")
_ABBREV = {"dr", "dra", "sr", "sra", "prof", "ex", "etc", "pág", "ref", "nº"}


class SentenceStage(Stage):
    id = "sentences"
    index = 3
    name = "Segmentação de sentenças"
    short = "Sentenças"
    explain = {
        "what": "Divide o texto em sentenças. Cada fala é uma fronteira rígida (nunca mistura falantes) e, dentro da fala, divide em ponto final, interrogação e exclamação.",
        "why": "Negação, incerteza e mapeamento de campos funcionam por sentença: o escopo de um \"não\" não pode atravessar para a frase seguinte, e cada trecho de origem exibido ao profissional é uma sentença.",
        "how": "Regra determinística (fronteira de fala + pontuação, ignorando decimais e abreviações). As fronteiras são depois impostas ao analisador de dependências do spaCy, que passa a respeitá-las.",
    }

    def run(self, state: PipelineState):
        sentences: list[dict] = []
        for utt_idx, a, b in state.utt_spans:
            seg = state.text[a:b]
            speaker = state.norm[utt_idx]["speaker"]
            pieces: list[tuple[int, int]] = []
            last = 0
            for m in _SPLIT.finditer(seg):
                lastword = re.findall(r"(\w+)\.$", seg[last:m.start() + 1])
                if lastword and lastword[0].lower() in _ABBREV:
                    continue  # "dr. silva" não encerra sentença
                pieces.append((last, m.start() + 1))
                last = m.end()
            pieces.append((last, len(seg)))
            for s, e in pieces:
                if e > s:
                    sentences.append({"idx": len(sentences), "utt": utt_idx, "speaker": speaker,
                                      "start": a + s, "end": a + e, "text": seg[s:e]})
        state.sentences = sentences
        state.sent_starts = [s["start"] for s in sentences]
        return {"sentences": sentences, "n": len(sentences)}
