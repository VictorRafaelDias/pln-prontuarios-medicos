"""Infraestrutura comum das etapas do pipeline."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineState:
    """Estado compartilhado entre etapas. Cada etapa lê o que as anteriores produziram."""
    utterances: list[dict]
    mode: str = "anamnese"                     # anamnese | soap
    options: dict = field(default_factory=dict)  # use_llm, llm_fields, confirmed, previous_session, ...
    # --- produzido pelas etapas
    asr: list[dict] = field(default_factory=list)
    norm: list[dict] = field(default_factory=list)       # falas normalizadas
    text: str = ""                                       # texto normalizado completo
    utt_spans: list[tuple[int, int, int]] = field(default_factory=list)  # (utt_idx, start, end) em ``text``
    sentences: list[dict] = field(default_factory=list)
    sent_starts: list[int] = field(default_factory=list)
    doc: Any = None
    tokens: list[dict] = field(default_factory=list)
    stop_flags: list[bool] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    rule_fields: dict[str, dict] = field(default_factory=dict)
    llm: dict = field(default_factory=dict)
    merged: dict[str, dict] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)

    def sentence_of(self, char_pos: int) -> dict | None:
        for s in self.sentences:
            if s["start"] <= char_pos < s["end"] or (char_pos == s["end"] and s is self.sentences[-1]):
                return s
        return None

    def utt_of(self, char_pos: int) -> int | None:
        for u, a, b in self.utt_spans:
            if a <= char_pos < b + 1:
                return u
        return None


class Stage:
    id: str = ""
    index: int = 0
    name: str = ""
    short: str = ""
    explain: dict = {"what": "", "why": "", "how": ""}

    def run(self, state: PipelineState) -> Any:  # pragma: no cover - interface
        raise NotImplementedError

    def describe_input(self, state: PipelineState) -> Any:
        """Resumo do que a etapa consome (por padrão, a saída da etapa anterior)."""
        return None

    def meta(self) -> dict:
        return {"id": self.id, "index": self.index, "name": self.name, "short": self.short, "explain": self.explain}


def timed(fn, *a, **kw):
    t0 = time.perf_counter()
    out = fn(*a, **kw)
    return out, (time.perf_counter() - t0) * 1000.0
