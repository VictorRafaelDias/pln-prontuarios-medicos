"""Etapa 2 — Normalização do texto oral."""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections import Counter

from .. import resources
from ..numbers import words_to_digits
from .base import PipelineState, Stage

SOFT_MARKERS = {"então", "aí", "daí", "bom", "olha", "olhe", "ó", "veja", "pois"}
QUESTION_RE = re.compile(
    r"^(?:qual|quais|quando|como|onde|quanto|quantos|quantas|por que|o que|você|voce|tem|teve|toma|usa|faz|fuma|bebe|"
    r"sente|sentiu|já|há|está|esta|costuma|consegue|dorme|alguma|algum|alguém|e o|e a|e como|e quando|e sobre|existe|"
    r"houve|tomou|fez|fumou|bebeu|sofre|gosta)\b", re.I)


def _cap_like(src: str, rep: str) -> str:
    return rep[:1].upper() + rep[1:] if src[:1].isupper() else rep


def normalize_text(raw: str, speaker: str, cfg: dict, counts: Counter) -> str:
    t = unicodedata.normalize("NFC", raw).replace(" ", " ")
    t = re.sub(r"[\x00-\x08\x0b-\x1f]", " ", t)

    aff = cfg.get("affirmatives_kept_as_sim", [])
    if aff and re.fullmatch(r"\W*(?:%s)\W*" % "|".join(map(re.escape, aff)), t, re.I):
        counts["'aham/uhum' → 'sim'"] += 1
        return "Sim."

    # 1) hesitações marcadas com reticências: "é...", "ahn..."
    alt = "|".join(sorted(map(re.escape, cfg.get("ellipsis_hesitations", [])), key=len, reverse=True))
    if alt:
        t, n = re.subn(rf"(?<!\w)(?:{alt})(?!\w)\s*(?:\.{{2,}}|…)\s*", " ", t, flags=re.I)
        counts["hesitações com reticências"] += n

    # 2) interjeições soltas
    inter = r"(?<!\w)(?:ahn+|ãhn+|hum+|hmm+|hm+|uh+m*|éh+|é{2,}|eh+|ah+|ã+h*|aham|uhum|ahã|uhã)(?!\w)[,.]?\s*"
    t, n = re.subn(inter, " ", t, flags=re.I)
    counts["interjeições"] += n

    # 3a) números por extenso → dígitos
    before = t
    t = words_to_digits(t)
    if t != before:
        counts["números por extenso → dígitos"] += len(re.findall(r"\d+(?:,\d+)?", t)) - len(re.findall(r"\d+(?:,\d+)?", before))

    # 3b) muletas ("tipo", "né", ", sabe?")
    for rx in cfg.get("filler_regex", []):
        t, n = re.subn(rx, " ", t, flags=re.I)
        counts["muletas (tipo/né/sabe)"] += n

    # 4) marcadores de discurso no início
    markers = sorted(cfg.get("leading_markers", []), key=len, reverse=True)
    for _ in range(3):
        m = None
        for mk in markers:
            if mk.lower() in SOFT_MARKERS:
                m = re.match(rf"^\s*{re.escape(mk)}(?:\s*[,.]\s*|\s+)(?=\S)", t, re.I)
            else:
                m = re.match(rf"^\s*{re.escape(mk)}\s*[,.]\s*(?=\S)", t, re.I)
            if m:
                break
        if not m:
            break
        t = t[m.end():]
        counts["marcadores de discurso"] += 1

    # 5) abreviações
    for k, v in cfg.get("abbreviations", {}).items():
        t, n = re.subn(rf"(?<!\w){re.escape(k)}(?!\w)", lambda m, v=v: _cap_like(m.group(0), v), t, flags=re.I)
        counts["abreviações expandidas"] += n
    for k, v in cfg.get("case_sensitive_abbreviations", {}).items():
        if k != v:
            t, n = re.subn(rf"(?<!\w){re.escape(k)}(?!\w)", v, t)
            counts["siglas clínicas expandidas"] += n

    # 7) gagueira / repetições de palavras funcionais
    sw = cfg.get("stutter_words", [])
    if sw:
        rx = r"(?<!\w)(" + "|".join(map(re.escape, sw)) + r")(?:\s*,?\s+\1)+(?!\w)"
        t, n = re.subn(rx, r"\1", t, flags=re.I)
        counts["repetições"] += n

    # 8) pontuação e espaços
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"\.{2,}|…", ".", t)
    t = re.sub(r"([,;:]){2,}", r"\1", t)
    t = re.sub(r",\s*([.?!])", r"\1", t)
    t = re.sub(r"([,.;:!?])(?=[^\s\d,.;:!?)\"'’])", r"\1 ", t)
    t = re.sub(r"^[\s,;.:\-–]+", "", t).strip()
    if not re.search(r"[A-Za-zÀ-ÿ0-9]", t):
        return ""
    t = re.sub(r"[,;:\-–]+$", "", t).strip()
    for i, ch in enumerate(t):
        if ch.isalpha():
            t = t[:i] + ch.upper() + t[i + 1:]
            break
    if t[-1] not in ".?!":
        t += "?" if speaker == "profissional" and QUESTION_RE.match(t) else "."
    return t


def make_diff(a: str, b: str) -> list[dict]:
    ta, tb = re.findall(r"\S+", a), re.findall(r"\S+", b)
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    ops: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        A, B = " ".join(ta[i1:i2]), " ".join(tb[j1:j2])
        if tag == "equal":
            ops.append({"op": "equal", "a": A, "b": B})
        elif tag == "delete":
            ops.append({"op": "delete", "a": A, "b": ""})
        elif tag == "insert":
            ops.append({"op": "insert", "a": "", "b": B})
        else:
            ops.append({"op": "replace", "a": A, "b": B})
    return ops


class NormalizeStage(Stage):
    id = "normalize"
    index = 2
    name = "Normalização"
    short = "Normaliza"
    explain = {
        "what": "Limpa a fala: remove hesitações e marcadores de oralidade (\"é...\", \"tipo\", \"né\", \"aham\"), padroniza espaços e pontuação, expande abreviações (\"vc\" → \"você\", \"HAS\" → \"hipertensão arterial sistêmica\") e converte números por extenso em dígitos (\"dez cigarros\" → 10, \"uns três meses\" → 3 meses).",
        "why": "A fala espontânea é cheia de ruído que quebra regras e dicionários. Números em dígitos permitem extrair intensidade (EVA), frequência e duração com expressões regulares simples e confiáveis.",
        "how": "Regex + gramática de números do português (vinte e cinco, dois mil e vinte, meio litro). \"um/uma\" só viram dígito diante de unidade de medida (um maço, uma vez), para não confundir com o artigo. O diff mostra exatamente o que mudou.",
    }

    def run(self, state: PipelineState):
        cfg = resources.get_resources()["normalization"]
        counts: Counter = Counter()
        out, parts, spans = [], [], []
        pos = 0
        for u in state.asr:
            text = normalize_text(u["text"], u["speaker"], cfg, counts)
            ops = make_diff(u["text"], text)
            rec = {"idx": u["idx"], "speaker": u["speaker"], "ts": u["ts"], "raw": u["text"], "text": text,
                   "ops": ops, "changed": text.strip() != u["text"].strip()}
            out.append(rec)
            if text:
                if parts:
                    pos += 1  # espaço separador
                spans.append((u["idx"], pos, pos + len(text)))
                parts.append(text)
                pos += len(text)
        state.norm = out
        state.text = " ".join(parts)
        state.utt_spans = spans
        return {
            "utterances": out,
            "text": state.text,
            "applied": dict(counts),
            "n_changed": sum(1 for r in out if r["changed"]),
            "chars_before": sum(len(r["raw"]) for r in out),
            "chars_after": len(state.text),
        }
