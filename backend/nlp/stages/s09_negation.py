"""Etapa 9 — Detecção de negação, incerteza e estados passados (algoritmo estilo NegEx adaptado ao português)."""
from __future__ import annotations

from dataclasses import dataclass

from .. import resources
from ..form_schema import fold
from .base import PipelineState, Stage

# Rótulos que podem ser negados ("não tenho DIABETES", "sem DOR", "não piora à NOITE")
NEGATABLE = {"PARTE_CORPO", "SINTOMA", "TIPO_DOR", "DOENCA", "MEDICAMENTO", "HABITO", "CONDICAO", "CIRURGIA",
             "ALERGENO", "TECNICA", "HORARIO"}
FORMER_TARGETS = {"HABITO", "MEDICAMENTO", "DOENCA", "SINTOMA", "CONDICAO", "TECNICA"}
UNCERTAIN_TARGETS = {"PARTE_CORPO", "SINTOMA", "TIPO_DOR", "DOENCA", "MEDICAMENTO", "HABITO", "CONDICAO", "CIRURGIA",
                     "ALERGENO", "INTENSIDADE", "FREQUENCIA", "TEMPO", "HORARIO", "MTC", "PONTO", "TECNICA"}
BIDIRECTIONAL = {"às vezes", "de vez em quando", "mais ou menos", "eventualmente", "quase", "meio que"}
SENT_END = {".", "?", "!", ";"}


@dataclass
class Trig:
    kind: str
    text: str
    words: tuple[str, ...]
    window: int
    factor: float = 1.0
    max_gap: int = 3


def load_triggers() -> list[Trig]:
    cfg = resources.get_resources()["negation_triggers"]
    default_w = int(cfg.get("window", 6))
    out: list[Trig] = []
    for kind in ("pre", "post", "pseudo", "termination", "uncertainty", "former", "former_post"):
        for t in cfg.get(kind, []):
            words = tuple(fold(w) for w in t["text"].split())
            out.append(Trig(kind, t["text"], words, int(t.get("window", default_w)), float(t.get("factor", 1.0)),
                            int(t.get("max_gap", 3))))
    out.sort(key=lambda t: -len(t.words))
    return out


def _find(norm: list[str], ts: int, te: int, triggers: list[Trig]) -> list[tuple[int, int, Trig]]:
    found: list[tuple[int, int, Trig]] = []
    for tr in triggers:
        L = len(tr.words)
        for i in range(ts, te - L + 1):
            if tuple(norm[i:i + L]) == tr.words:
                found.append((i, i + L, tr))
    # remove ocorrências contidas em outra mais longa do MESMO tipo
    keep = []
    for a in found:
        if any(b is not a and b[2].kind == a[2].kind and b[0] <= a[0] and a[1] <= b[1] and (b[1] - b[0]) > (a[1] - a[0]) for b in found):
            continue
        keep.append(a)
    return sorted(keep, key=lambda x: x[0])


class NegationStage(Stage):
    id = "negation"
    index = 9
    name = "Negação e incerteza"
    short = "Negação"
    explain = {
        "what": "Descobre, para cada entidade, se ela foi AFIRMADA, NEGADA (\"não fumo\", \"nega diabetes\", \"sem dor\"), é um estado PASSADO (\"parei de fumar há 2 anos\" → ex-tabagista) ou INCERTA (\"acho que\", \"talvez\", \"às vezes\").",
        "why": "É a etapa que evita o pior erro de um extrator ingênuo: registrar \"fumante\" porque a palavra \"fumo\" apareceu. Em saúde, \"nega gestação\" e \"gestante\" são opostos; e incerteza deve reduzir a confiança para o profissional revisar.",
        "how": "NegEx adaptado: gatilhos (não, nunca, nega, sem, nem...) abrem uma JANELA de N tokens à direita; terminadores (mas, porém, que...) e o fim da frase fecham o escopo. Pseudo-negações (\"não só\", \"sem dúvida\") são ignoradas. \"Não ... mais\" vira estado passado, não negação. Gatilhos de incerteza multiplicam a confiança por um fator. Todos os gatilhos estão em negation_triggers.json (editável no Laboratório).",
    }

    def describe_input(self, state: PipelineState):
        return {"n_entities": len(state.entities)}

    def run(self, state: PipelineState):
        doc = state.doc
        triggers = load_triggers()
        norm = [fold(t.text) if not t.is_space else "" for t in doc]
        ents = state.entities
        # intervalo de tokens de cada sentença
        ranges = []
        for s in state.sentences:
            span = doc.char_span(s["start"], s["end"], alignment_mode="expand")
            ranges.append((span.start, span.end) if span is not None else (0, 0))
        for e in ents:
            e.update({"negated": False, "uncertain": False, "former": False, "resolved": False, "tense": None,
                      "factor": 1.0, "triggers": []})
            # tempo verbal do núcleo (para hábitos/medicamentos: "fumava", "bebia")
            if e["tok_start"] is not None and e["label"] in ("HABITO", "MEDICAMENTO", "SINTOMA", "DOENCA"):
                for t in doc[e["tok_start"]:e["tok_end"]]:
                    tense = t.morph.get("Tense")
                    if tense and t.pos_ in ("VERB", "AUX"):
                        e["tense"] = "past" if tense[0] in ("Past", "Imp", "Pqp") else "present"
                        break
            if e["text"].lower().startswith(("ex-", "ex ")) or e["text"].lower() in ("ex-fumante", "ex fumante", "ex-tabagista"):
                e["former"] = True
                e["triggers"].append({"text": "prefixo ex-", "type": "former"})
        log = []
        for si, (ts, te) in enumerate(ranges):
            if te <= ts:
                continue
            sent_ents = [e for e in ents if e["sent"] == si and e["tok_start"] is not None]
            ent_tokens = {i for e in sent_ents for i in range(e["tok_start"], e["tok_end"])}
            matches = _find(norm, ts, te, triggers)
            by_kind: dict[str, list[tuple[int, int, Trig]]] = {}
            for m in matches:
                by_kind.setdefault(m[2].kind, []).append(m)
            pseudo_tokens = {i for a, b, _ in by_kind.get("pseudo", []) for i in range(a, b)}
            terms = [a for a, _, _ in by_kind.get("termination", [])]

            def scope_end(start: int, window: int) -> int:
                end = min(start + window, te)
                for i in range(start, end):
                    if doc[i].text in SENT_END:
                        return i
                for t in terms:
                    if start <= t < end:
                        end = t
                        break
                return end

            def scope_start_back(end: int, window: int) -> int:
                st = max(end - window, ts)
                for i in range(end - 1, st - 1, -1):
                    if doc[i].text in SENT_END:
                        return i + 1
                for t in sorted(terms, reverse=True):
                    if st <= t < end:
                        st = t + 1
                        break
                return st

            def record(kind, a, b, tr, sa, sb):
                log.append({"sent": si, "type": kind, "text": " ".join(doc[i].text for i in range(a, b)),
                            "tok_start": a, "tok_end": b, "scope": [sa, sb], "trigger": tr.text})

            for a, b, tr in by_kind.get("pre", []):
                if a in ent_tokens or any(i in pseudo_tokens for i in range(a, b)):
                    continue
                if tr.words == ("nao",) and (b >= te or doc[b].text in SENT_END):
                    # "anticoagulante não." — negação posposta no fim da frase: escopo para a ESQUERDA
                    sa, sb = scope_start_back(a, 3), a
                    record("negação (posposta)", a, b, tr, sa, sb)
                    for e in sent_ents:
                        if e["label"] in NEGATABLE and sa <= e["tok_start"] < sb:
                            e["negated"] = True
                            e["triggers"].append({"text": tr.text + " (posposto)", "type": "negation"})
                    continue
                sa, sb = b, scope_end(b, tr.window)
                record("negação", a, b, tr, sa, sb)
                for e in sent_ents:
                    if e["label"] in NEGATABLE and sa <= e["tok_start"] < sb:
                        # "não ... mais" → estado passado (hábito) ou resolvido (sintoma)
                        has_mais = any(norm[i] == "mais" for i in range(sa, min(e["tok_end"] + 3, te)) if i >= sa and (i < e["tok_start"] or i >= e["tok_end"]))
                        if has_mais and tr.words[0] in ("nao", "nunca", "nem"):
                            if e["label"] in ("HABITO", "MEDICAMENTO"):
                                e["former"] = True
                                e["triggers"].append({"text": f"{tr.text} … mais", "type": "former"})
                            else:
                                e["negated"] = True
                                e["resolved"] = True
                                e["triggers"].append({"text": f"{tr.text} … mais", "type": "negation"})
                        else:
                            e["negated"] = True
                            e["triggers"].append({"text": tr.text, "type": "negation"})
            for a, b, tr in by_kind.get("post", []):
                if a in ent_tokens:
                    continue
                sa, sb = scope_start_back(a, tr.window), a
                record("negação (pós)", a, b, tr, sa, sb)
                for e in sent_ents:
                    if e["label"] in NEGATABLE and sa <= e["tok_start"] < sb:
                        e["negated"] = True
                        e["triggers"].append({"text": tr.text, "type": "negation"})
            for a, b, tr in by_kind.get("former", []):
                if a in ent_tokens:
                    continue
                sa, sb = b, scope_end(b, tr.window)
                record("estado passado", a, b, tr, sa, sb)
                for e in sent_ents:
                    if e["label"] in FORMER_TARGETS and sa <= e["tok_start"] < sb:
                        e["former"] = True
                        e["triggers"].append({"text": tr.text, "type": "former"})
            for a, b, tr in by_kind.get("uncertainty", []):
                if a in ent_tokens:
                    continue
                sa, sb = b, scope_end(b, tr.window)
                if tr.text in BIDIRECTIONAL:
                    sa = scope_start_back(a, tr.window)
                record("incerteza", a, b, tr, sa, sb)
                for e in sent_ents:
                    if e["label"] in UNCERTAIN_TARGETS and (sa <= e["tok_start"] < sb or (tr.text in BIDIRECTIONAL and sa <= e["tok_start"] < sb)):
                        if not e["uncertain"] or tr.factor < e["factor"]:
                            e["factor"] = tr.factor
                        e["uncertain"] = True
                        e["triggers"].append({"text": tr.text, "type": "uncertainty", "factor": tr.factor})
        for e in ents:
            e["conf"] = round(e["conf"] * e["factor"], 3)
            e["status"] = ("passado" if e["former"] else "negado" if e["negated"] else "afirmado")
        summary = {
            "negated": sum(1 for e in ents if e["negated"]),
            "former": sum(1 for e in ents if e["former"]),
            "uncertain": sum(1 for e in ents if e["uncertain"]),
            "affirmed": sum(1 for e in ents if e["clinical"] and not e["negated"] and not e["former"]),
            "triggers_found": len(log),
        }
        return {"triggers": log, "summary": summary,
                "entities": [{"id": e["id"], "text": e["text"], "label": e["label"], "status": e["status"],
                              "negated": e["negated"], "former": e["former"], "uncertain": e["uncertain"], "conf": e["conf"],
                              "triggers": e["triggers"], "sent": e["sent"]} for e in ents if e["clinical"]],
                "config": {"triggers_loaded": {k: sum(1 for t in triggers if t.kind == k) for k in
                                                ("pre", "post", "pseudo", "termination", "uncertainty", "former")}}}
