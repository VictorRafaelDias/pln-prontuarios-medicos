"""Regras determinísticas entidade → campo do formulário (etapa 10).

Cada regra devolve *candidatos* {campo, valor, confiança, trecho, regra}. A consolidação (um valor por campo)
é feita em ``s10_mapping``. Só falas do PACIENTE são tratadas como relato; falas do PROFISSIONAL contam para
campos que o profissional dita (língua, pulso, padrões, princípio, pontos, técnica, orientações) e como CONTEXTO
de perguntas (\"Você fuma?\" + \"Não\").
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any

from .form_schema import FIELD_BY_ID, REGIONS, fold

HABIT_THEMES = {"sono", "intestino", "urina", "estresse"}
PAIN_THEMES = {"dor", "musculo"}
SECOND_CUE = re.compile(r"\b(tamb[eé]m|al[eé]m disso|outra queixa|outra coisa|outro problema|secund[aá]ri|e mais)\b", re.I)
POS_START = re.compile(r"^\W*(sim|claro|tenho|tomo|uso|fa[cç]o|fumo|bebo|estou|sou|morro de medo|muito|bastante|demais|isso|exato|exatamente|com certeza|correto|positivo)\b", re.I)
NEG_START = re.compile(r"^\W*(n[aã]o|nunca|jamais|nenhum|nenhuma|negativo)\b", re.I)
PARTIAL_START = re.compile(r"^\W*(?:[àa]s vezes|um pouco|mais ou menos|socialmente|de vez em quando|raramente|eventualmente|ocasionalmente)\b", re.I)
SCALE_Q = re.compile(r"\b(nota|de 0 a 10|0 a 10|escala|intensidade|eva|quanto d[oó]i|quanto est[aá])\b", re.I)
TIME_Q = re.compile(r"\b(desde quando|quanto tempo|h[aá] quanto|quando (?:come[cç]ou|iniciou|surgiu|apareceu)|h[aá] quanto tempo)\b", re.I)
PAIN_Q = re.compile(r"\b(d[oó]i|dor|doendo|incomoda)\b", re.I)
SOCIAL_RX = re.compile(r"socialmente|ocasionalmente|de vez em quando|eventualmente|fins? de semana|finais de semana|festa|raramente|[àa]s vezes", re.I)
HEAVY_RX = re.compile(r"todo dia|todos os dias|diariamente|toda noite|v[aá]rias vezes|muito", re.I)
PRESENT_RX = re.compile(r"\b(ainda|hoje|atualmente|agora|continuo|continua)\b", re.I)
CAP_ART = {"cabeça": "na", "pescoço": "no", "garganta": "na", "ombro": "no", "braço": "no", "cotovelo": "no", "antebraço": "no",
           "mão": "na", "tórax": "no", "costas": "nas", "lombar": "na região", "abdômen": "no", "quadril": "no", "glúteo": "no",
           "coxa": "na", "joelho": "no", "perna": "na", "pé": "no"}
FEM = {"cabeça", "mão", "coxa", "perna", "garganta"}
PLURAL = {"mão": "mãos", "quadril": "quadris", "pé": "pés", "braço": "braços", "ombro": "ombros", "joelho": "joelhos", "cotovelo": "cotovelos"}
SYMPTOM_NAME = {"lombalgia": "Dor lombar", "cervicalgia": "Dor cervical", "ciatalgia": "Dor ciática (ciatalgia)",
                "dor de cabeça": "Dor de cabeça", "enxaqueca": "Enxaqueca"}

IMPROVE_RX = re.compile(r"\b(melhor(?:a|ou|ei|ando|ia|as|es)|alivi(?:ou|ei|ando)|diminu(?:iu|i)|menos dor|passou|sumiu|amenizou|"
                        r"evoluiu bem|bem melhor|me sinto melhor|estou melhor)\b", re.I)
WORSEN_RX = re.compile(r"\b(pior(?:ou|ei|ando|a)?|aumentou|mais dor|voltou|intensificou|agravou)\b", re.I)
STABLE_RX = re.compile(r"\b(igual|na mesma|sem mudan[cç]a|continua igual|est[aá]vel|n[aã]o mudou)\b", re.I)


def affirmed(e: dict) -> bool:
    return not e.get("negated") and not e.get("former")


def cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def num_text(x: float | int) -> str:
    return str(int(x)) if float(x) == int(x) else str(x).replace(".", ",")


class Mapper:
    def __init__(self, state):
        self.state = state
        self.mode = state.mode
        self.text = state.text
        self.doc = state.doc
        self.sents: list[dict] = state.sentences
        self.ents: list[dict] = state.entities
        self.by_sent: dict[int, list[dict]] = defaultdict(list)
        for e in self.ents:
            if e["sent"] is not None:
                self.by_sent[e["sent"]].append(e)
        self.cands: list[dict] = []
        self.qa: dict[int, dict] = {}
        self._build_qa()
        self.prev = state.options.get("previous_session") or {}

    # ------------------------------------------------------------------ util
    def add(self, field: str, value: Any, conf: float, sent_idx: int | None, rule: str, ents: list[dict] = (),
            status: str = "afirmado", **extra):
        if field not in FIELD_BY_ID or value in (None, "", []):
            return
        s = self.sents[sent_idx] if sent_idx is not None else None
        factor = min([e.get("factor", 1.0) for e in ents] or [1.0])
        self.cands.append({
            "field": field, "value": value, "conf": round(min(conf * factor, 0.99), 3),
            "evidence": s["text"] if s else "", "sent": sent_idx, "utt": s["utt"] if s else -1,
            "speaker": s["speaker"] if s else None, "start": s["start"] if s else None, "end": s["end"] if s else None,
            "rule": rule, "entities": [e["id"] for e in ents], "status": status,
            "uncertain": factor < 1.0, **extra,
        })

    def patient_sents(self):
        return [s for s in self.sents if s["speaker"] == "paciente"]

    def prof_sents(self):
        return [s for s in self.sents if s["speaker"] == "profissional"]

    def ents_of(self, si: int, labels=None, only_affirmed=False):
        out = self.by_sent.get(si, [])
        if labels:
            out = [e for e in out if e["label"] in labels]
        if only_affirmed:
            out = [e for e in out if affirmed(e)]
        return out

    def _build_qa(self):
        """Liga cada fala curta do paciente à pergunta imediatamente anterior do profissional."""
        for i, s in enumerate(self.sents):
            if s["speaker"] != "paciente" or (i > 0 and self.sents[i - 1]["utt"] == s["utt"]):
                continue
            j = i - 1
            if j < 0 or self.sents[j]["speaker"] != "profissional":
                continue
            q_utt = self.sents[j]["utt"]
            q_sents = [k for k, x in enumerate(self.sents) if x["utt"] == q_utt]
            self.qa[i] = {"q_sents": q_sents, "q_text": " ".join(self.sents[k]["text"] for k in q_sents),
                          "q_ents": [e for k in q_sents for e in self.by_sent.get(k, [])]}

    def qa_for(self, si: int):
        """Contexto pergunta→resposta da FALA inteira (a resposta pode ter várias sentenças)."""
        first = next((x["idx"] for x in self.sents if x["utt"] == self.sents[si]["utt"]), si)
        return self.qa.get(first)

    def answer_polarity(self, si: int) -> str | None:
        """'neg' | 'pos' | 'partial' para respostas curtas; None se a fala não parece uma resposta curta."""
        s = self.sents[si]
        utt_sents = [x for x in self.sents if x["utt"] == s["utt"]]
        words = len(re.findall(r"\w+", " ".join(x["text"] for x in utt_sents)))
        if words > 9 or si not in self.qa:
            return None
        t = s["text"]
        if PARTIAL_START.match(t):
            return "partial"
        if NEG_START.match(t):
            return "neg"
        if POS_START.match(t):
            return "pos"
        return None

    def laterality(self, e: dict) -> str | None:
        if e["tok_start"] is None:
            return None
        toks = [fold(t.text) for t in self.doc[max(0, e["tok_start"] - 2):e["tok_end"] + 4]]
        if e["text"].lower().endswith("s") and e["text"].lower() not in ("costas", "pés") and len(e["text"]) > 4:
            return "both"
        after = toks[e["tok_start"] - max(0, e["tok_start"] - 2) + (e["tok_end"] - e["tok_start"]):]
        before = toks[:e["tok_start"] - max(0, e["tok_start"] - 2)]
        d = {"direito", "direita"}
        es = {"esquerdo", "esquerda"}
        for window in (after[:3], before[-1:]):
            if set(window) & {"ambos", "ambas", "bilateral", "2", "lados"}:
                return "both"
            if set(window) & d and set(window) & es:
                return "both"
            if set(window) & d:
                return "d"
            if set(window) & es:
                return "e"
        return None

    ACTION_BEFORE = re.compile(r"(?:\bquando|\bao|\bpara|\bpra|\bse)\s+(?:eu\s+)?\w+\s+(?:o|a|os|as|meu|minha)?\s*$", re.I)

    def is_action_object(self, e: dict) -> bool:
        """'quando levanto o braço': o braço é o objeto de um movimento, não o local da dor."""
        s = self.sents[e["sent"]]
        before = self.text[s["start"]:e["start"]]
        return bool(self.ACTION_BEFORE.search(before)) and not re.search(r"d[oó]i|dor", before[-25:], re.I)

    def regions(self, e: dict) -> tuple[list[str], float, str]:
        """Ids de região do corpo para uma entidade (PARTE_CORPO ou SINTOMA com região). Retorna (ids, fator de confiança, descrição)."""
        attrs = e.get("attrs", {})
        base = attrs.get("regiao") or []
        if isinstance(base, str):
            base = [base]
        ids: list[str] = []
        factor = 1.0
        desc = e["canonical"]
        if attrs.get("lateral") and e["label"] == "PARTE_CORPO":
            lat = self.laterality(e)
            for b in base:
                if lat == "d":
                    ids.append(f"{b}_d")
                elif lat == "e":
                    ids.append(f"{b}_e")
                elif lat == "both":
                    ids += [f"{b}_d", f"{b}_e"]
                else:
                    ids += [f"{b}_d", f"{b}_e"]
                    factor = 0.6  # lateralidade não informada
            fem = e["canonical"] in FEM
            side = {"d": "direita" if fem else "direito", "e": "esquerda" if fem else "esquerdo", "both": "bilateral"}.get(lat or "", "")
            desc = f"{e['canonical']} {side}".strip()
            if lat == "both":
                desc = PLURAL.get(e["canonical"], e["canonical"] + "s")
        else:
            ids = [b for b in base if b in REGIONS]
        if attrs.get("generic"):
            factor *= 0.7
        return [i for i in ids if i in REGIONS], factor, desc

    def part_phrase(self, parts: list[tuple[str, str]]) -> str:
        """[(canonical, descrição com lateralidade)] → 'no joelho direito e na região lombar'."""
        out = []
        for canon, desc in parts:
            art = CAP_ART.get(canon, "em")
            if desc == PLURAL.get(canon, canon + "s"):
                art = {"no": "nos", "na": "nas"}.get(art, art)
            out.append(f"{art} {desc}" if canon != "lombar" else "na região lombar")
        if not out:
            return ""
        return out[0] if len(out) == 1 else ", ".join(out[:-1]) + " e " + out[-1]

    # ------------------------------------------------------------------ execução
    def run(self) -> list[dict]:
        self.r_intensidade()
        self.r_queixa()
        self.r_tipo_horario()
        self.r_piora_melhora()
        self.r_habitos()
        self.r_saude()
        self.r_contra()
        self.r_mtc()
        self.r_plano_soap()
        return self.cands

    # ------------------------------------------------------------------ EVA / estresse
    def _intensity_subject(self, e: dict) -> str:
        si = e["sent"]
        near = [x for x in self.by_sent.get(si, []) if x["label"] == "SINTOMA"]
        for x in near:
            if x["attrs"].get("tema") in ("estresse", "emocional") and abs(x["start"] - e["start"]) < 60:
                return "estresse"
        if re.search(r"estress|ansiedad", self.sents[si]["text"], re.I) and not any(x["attrs"].get("tema") == "dor" for x in near):
            return "estresse"
        qa = self.qa.get(si)
        if qa and re.search(r"estress|ansiedad", qa["q_text"], re.I) and not PAIN_Q.search(qa["q_text"]):
            return "estresse"
        return "dor"

    def r_intensidade(self):
        eva_field = "queixa.eva"
        for e in self.ents:
            if e["label"] != "INTENSIDADE" or e["sent"] is None:
                continue
            s = self.sents[e["sent"]]
            if s["speaker"] != "paciente" and s["speaker"] != "profissional":
                continue
            if s["speaker"] == "profissional" and "?" in s["text"]:
                continue  # pergunta, não resposta
            a = e["attrs"]
            subj = self._intensity_subject(e)
            if subj == "estresse":
                if a.get("kind") == "numeric":
                    self.add("habitos.estresse", a["value"], 0.9 * e["conf"] / 0.95, e["sent"], f"{e['rule']} + assunto estresse", [e])
                continue
            conf = (0.95 if a.get("kind") == "numeric" else 0.45) * (e["conf"] / (0.95 if a.get("kind") == "numeric" else 0.6))
            self.add(eva_field, a["value"], conf, e["sent"], e["rule"], [e])
        # resposta numérica solta a uma pergunta de escala: "Sete."
        for si, qa in self.qa.items():
            s = self.sents[si]
            m = re.fullmatch(r"\W*(?P<h>mais ou menos|uns|umas|cerca de|aproximadamente|acho que)?\s*(?:nota\s+)?(?P<v>\d{1,2})(?:\s+de\s+10)?(?:\s*,?\s*(?:talvez|ou)\s+\d{1,2})?\W*", s["text"], re.I)
            if m and SCALE_Q.search(qa["q_text"]) and 0 <= int(m.group("v")) <= 10:
                stress = bool(re.search(r"estress|ansiedad", qa["q_text"], re.I)) and not PAIN_Q.search(qa["q_text"])
                self.add("habitos.estresse" if stress else eva_field, int(m.group("v")), 0.7 if m.group("h") else 0.85, si,
                         "resposta numérica a pergunta de escala (QA)")

    # ------------------------------------------------------------------ queixa principal
    def _is_pain(self, e: dict) -> bool:
        return (e["label"] == "SINTOMA" and e["attrs"].get("tema") in PAIN_THEMES) or e["label"] == "TIPO_DOR"

    def _pain_ctx(self, si: int) -> bool:
        if any(self._is_pain(e) and affirmed(e) for e in self.by_sent.get(si, [])):
            return True
        # "É o joelho direito. Dói demais para subir escada.": a parte do corpo e a dor ficam em frases vizinhas da MESMA fala
        utt = self.sents[si]["utt"]
        for nb in (si - 1, si + 1):
            if 0 <= nb < len(self.sents) and self.sents[nb]["utt"] == utt and self.sents[nb]["speaker"] == "paciente"                     and any(self._is_pain(e) and affirmed(e) for e in self.by_sent.get(nb, [])):
                return True
        qa = self.qa.get(si)
        return bool(qa and PAIN_Q.search(qa["q_text"]) and any(e["label"] == "PARTE_CORPO" for e in self.by_sent.get(si, [])))

    def _after_cue(self, e: dict) -> bool:
        s = self.sents[e["sent"]]
        for m in SECOND_CUE.finditer(s["text"]):
            if s["start"] + m.start() < e["start"]:
                return True
        return False

    def r_queixa(self):
        psents = self.patient_sents()
        main_si = None
        for s in psents:
            if any(e["label"] == "SINTOMA" and e["attrs"].get("tema") in PAIN_THEMES and affirmed(e) for e in self.by_sent.get(s["idx"], [])) \
                    and any(e["label"] == "PARTE_CORPO" or e["attrs"].get("regiao") for e in self.by_sent.get(s["idx"], []) if e["label"] in ("PARTE_CORPO", "SINTOMA")):
                main_si = s["idx"]
                break
        if main_si is None:
            for s in psents:
                if any(e["label"] == "SINTOMA" and affirmed(e) and e["attrs"].get("tema") not in HABIT_THEMES for e in self.by_sent.get(s["idx"], [])):
                    main_si = s["idx"]
                    break
        self.main_si = main_si
        loc_ids: dict[str, tuple[float, int, list[dict]]] = {}
        secondary: list[tuple[str, float, int, dict]] = []
        parts_main: list[tuple[str, str]] = []
        main_syms: list[dict] = []
        for s in psents:
            si = s["idx"]
            ents = self.by_sent.get(si, [])
            pain = self._pain_ctx(si)
            for e in ents:
                if not affirmed(e) or e["tok_start"] is None:
                    continue
                is_secondary = (si != main_si and bool(SECOND_CUE.search(s["text"]))) or (si == main_si and self._after_cue(e))
                if e["label"] == "SINTOMA" and e["attrs"].get("tema") not in HABIT_THEMES:
                    regs, f, desc = self.regions(e) if e["attrs"].get("regiao") else ([], 1.0, "")
                    name = SYMPTOM_NAME.get(e["canonical"], cap(e["canonical"]))
                    if is_secondary or (si != main_si and not self._is_pain(e)) or (si == main_si and not self._is_pain(e) and main_syms):
                        label = name
                        if e["canonical"] == "dor":
                            near = [p for p in ents if p["label"] == "PARTE_CORPO" and affirmed(p) and abs(p["start"] - e["start"]) < 40]
                            if near:
                                _, _, d = self.regions(near[0])
                                label = f"Dor {self.part_phrase([(near[0]['canonical'], d)])}"
                        secondary.append((label, 0.8 * e["conf"] / 0.9, si, e))
                    elif si == main_si or self._is_pain(e):
                        if si == main_si and not main_syms:
                            main_syms.append(e)
                        for r in regs:
                            if r not in loc_ids or loc_ids[r][0] < 0.85 * f:
                                loc_ids[r] = (0.9 * f * e["conf"] / 0.9, si, [e])
                elif e["label"] == "PARTE_CORPO" and pain:
                    if self.is_action_object(e):
                        continue
                    if is_secondary:
                        _, _, d = self.regions(e)
                        secondary.append((f"Dor {self.part_phrase([(e['canonical'], d)])}", 0.7, si, e))
                        continue
                    regs, f, desc = self.regions(e)
                    # só entra na localização se estiver no contexto da dor principal
                    for r in regs:
                        if r not in loc_ids or loc_ids[r][0] < 0.85 * f:
                            loc_ids[r] = (0.88 * f * (e["conf"] / 0.9), si, [e])
                    if si == main_si or not parts_main:
                        parts_main.append((e["canonical"], desc))
        if loc_ids:
            first_si = min(v[1] for v in loc_ids.values())
            for r, (conf, si, ents) in loc_ids.items():
                self.add("queixa.localizacao", [r], conf, si, "PARTE_CORPO/SINTOMA com região → mapa corporal", ents)
        # descrição (anamnese) / relato (SOAP)
        if main_si is not None and self.mode == "anamnese":
            ents = self.by_sent.get(main_si, [])
            sym = main_syms[0] if main_syms else next((e for e in ents if e["label"] == "SINTOMA"), None)
            if sym is not None:
                name = SYMPTOM_NAME.get(sym["canonical"], cap(sym["canonical"]))
                value = name
                if sym["canonical"] == "dor" and parts_main:
                    uniq = list(dict.fromkeys(parts_main))[:3]
                    value = f"Dor {self.part_phrase(uniq)}"
                tipos = [e for e in ents if e["label"] == "TIPO_DOR" and affirmed(e)]
                if tipos and self._is_pain(sym):
                    value += " (" + ", ".join(dict.fromkeys(t["canonical"] for t in tipos)) + ")"
                self.add("queixa.descricao", value, 0.8 * sym["conf"] / 0.9, main_si, "sintoma principal + partes do corpo", [sym])
        if self.mode == "soap":
            picks = []
            for s in psents:
                ents = self.by_sent.get(s["idx"], [])
                if any(e["label"] in ("SINTOMA", "TIPO_DOR", "INTENSIDADE") and affirmed(e) for e in ents) or IMPROVE_RX.search(s["text"]) or WORSEN_RX.search(s["text"]):
                    picks.append(s)
            if picks:
                txt = " ".join(p["text"] for p in picks[:3])
                self.add("queixa.descricao", txt[:400], 0.75, picks[0]["idx"], "falas do paciente com sintomas (relato)")
        # início
        self._inicio(main_si)
        # secundárias
        seen = set()
        for label, conf, si, e in secondary:
            k = fold(label)
            if k in seen:
                continue
            seen.add(k)
            self.add("secundarias.lista", [label], min(conf, 0.85), si, "sintoma secundário (não principal)", [e])

    def _inicio(self, main_si):
        for s in self.sents:
            for e in self.by_sent.get(s["idx"], []):
                if e["label"] != "TEMPO":
                    continue
                a = e["attrs"]
                if a.get("kind") in ("minutes", "future"):
                    continue
                if s["speaker"] != "paciente":
                    continue
                qa = self.qa.get(s["idx"])
                ents = self.by_sent.get(s["idx"], [])
                has_symptom = any(x["label"] == "SINTOMA" and affirmed(x) and x["attrs"].get("tema") not in HABIT_THEMES for x in ents)
                has_other = any(x["label"] in ("HABITO", "MEDICAMENTO", "CIRURGIA", "DOENCA", "CONDICAO") for x in ents)
                asked = bool(qa and TIME_Q.search(qa["q_text"]))
                began = bool(re.search(r"\b(come[cç]ou|iniciou|surgiu|apareceu|aparece|come[cç]o|tem|sinto)\b", s["text"], re.I))
                prev_same_utt = s["idx"] > 0 and self.sents[s["idx"] - 1]["utt"] == s["utt"] and (s["idx"] - 1) == main_si
                other_topic = any(x["label"] in ("HABITO", "SINTOMA", "MEDICAMENTO", "DOENCA", "CIRURGIA", "CONDICAO") for x in ents)
                time_only = prev_same_utt and a.get("kind") in ("ago", "since", "duration") and not other_topic
                if (has_symptom and not (has_other and not asked)) or asked or time_only or ((main_si == s["idx"] or prev_same_utt) and began):
                    if a.get("kind") == "bare" and not (asked or has_symptom):
                        continue
                    text = self.time_text(e)
                    if text:
                        self.add("queixa.inicio", text, 0.85 if a.get("kind") != "bare" else 0.6, s["idx"], e["rule"], [e])

    @staticmethod
    def time_text(e: dict) -> str:
        a = e["attrs"]
        k = a.get("kind")
        if k in ("ago", "duration", "bare"):
            q = a.get("approx")
            txt = f"{num_text(a['qty'])} {a['unit']}"
            if a["qty"] == 1:
                txt = txt.replace("anos", "ano").replace("meses", "mês").replace("semanas", "semana").replace("dias", "dia").replace("horas", "hora")
            return (f"Há {q + ' ' if q and q not in ('uns', 'umas') else ''}{txt}").replace("Há mais de", "Há mais de")
        if k == "since":
            if a.get("year"):
                return f"Desde {a.get('month') + ' de ' if a.get('month') else ''}{a['year']}"
            if a.get("month"):
                return f"Desde {a['month']}"
            return f"Desde {a.get('phrase', '')}"
        if k == "year":
            return f"Em {a['year']}"
        return ""

    # ------------------------------------------------------------------ tipo de dor, horário
    def r_tipo_horario(self):
        for s in self.patient_sents():
            for e in self.by_sent.get(s["idx"], []):
                if e["label"] == "TIPO_DOR" and affirmed(e) and e["attrs"].get("opcao"):
                    self.add("queixa.tipo_dor", [e["attrs"]["opcao"]], 0.85 * e["conf"] / 0.9, s["idx"], e["rule"], [e])
                if e["label"] == "HORARIO" and affirmed(e) and e["attrs"].get("opcao"):
                    t = s["text"]
                    worse = re.search(r"\b(pior|piora|pioram|piorando|mais forte|mais intens|mais dor|incomoda mais|atrapalha)\b", t, re.I)
                    better = re.search(r"\b(melhor|melhora|alivia|passa)\b", t, re.I)
                    qa = self.qa.get(s["idx"])
                    asked = bool(qa and re.search(r"\b(pior|piora|hor[aá]rio|quando)\b", qa["q_text"], re.I))
                    if (worse and not (better and better.start() < worse.start() and abs(better.start() - e["start"] + s["start"]) < abs(worse.start() - e["start"] + s["start"]))) or asked:
                        self.add("queixa.horario_pior", e["attrs"]["opcao"], 0.85 * e["conf"] / 0.9, s["idx"], e["rule"] + " + gatilho de piora", [e])

    # ------------------------------------------------------------------ piora / melhora
    def _infinitive(self, span, force_verb: bool = False) -> str | None:
        """Verbo no infinitivo a partir do lema do spaCy, validado contra o vocabulário (evita 'carregir')."""
        tok = span[0]
        word = tok.text.lower()
        stem = word[:-1] if word.endswith("o") else word
        lemma = tok.lemma_.lower()
        for cand in (lemma, stem + "ar", stem + "er", stem + "ir"):
            if cand != word and cand.endswith(("ar", "er", "ir")) and tok.vocab.has_vector(cand):
                return cand
        # sem evidência no vocabulário: só confia no lema do spaCy quando é da 1ª conjugação (-ar), a mais regular
        if lemma != word and lemma.endswith("ar"):
            return lemma
        # "quando eu caminho": depois de "eu" a palavra é verbo na 1ª pessoa, mesmo que o tagger a veja como substantivo
        return stem + "ar" if force_verb and word.endswith("o") and len(word) > 4 else None

    def _split_items(self, phrase: str, base: int) -> list[str]:
        """Divide 'carrego peso e à noite, quando deito em cima dele' em itens e põe o verbo no infinitivo."""
        out: list[str] = []
        horarios = {fold(w) for w in ("manhã", "tarde", "noite", "madrugada", "à noite", "de manhã", "à tarde", "de noite", "de madrugada")}
        pos = 0
        for part in re.split(r"(\s+e\s+|\s+ou\s+|\s*,\s*)", phrase):
            raw, off = part, base + pos
            pos += len(part)
            if re.fullmatch(r"\s+e\s+|\s+ou\s+|\s*,\s*", part):
                continue
            lead = re.match(r"^(?:\s*(?:quando|com|o|a|os|as|um|uma|eu|me|se|de|do|da|no|na|ao|à)\s+)+", raw, re.I)
            had_eu = bool(lead and re.search(r"\beu\b", lead.group(0), re.I))
            if lead:
                raw, off = raw[lead.end():], off + lead.end()
            raw = raw.strip(" .")
            if not raw or fold(raw) in horarios or not (2 < len(raw) <= 45):
                continue
            w = re.match(r"\w+", raw)
            if w:
                span = self.doc.char_span(off, off + w.end(), alignment_mode="contract")
                if span is not None and len(span) == 1 and (span[0].pos_ in ("VERB", "AUX") or had_eu):
                    inf = self._infinitive(span, force_verb=had_eu)
                    if inf:
                        raw = inf + raw[w.end():]
            out.append(cap(raw))
        return out

    def r_piora_melhora(self):
        end = r"(?=\s+(?:e\s+(?:{other})|mas|por[eé]m)\b|[.;?!]|,(?!\s*(?:quando|ao|com|se|depois)\b)|$)"
        prep = r"(?:com|quando|ao|aos|se|depois\s+d[oae]s?|ap[oó]s|em|no|na|[àa]s?|durante|de)"
        piora = re.compile(r"\b(?:piora|pioram|piorando|piorou|agrava|agravam|aumenta|fico pior|fica pior|ficar pior)\b\s+(?:muito\s+|bastante\s+|bem\s+)?" + prep +
                           r"\s+(?P<x>[^.;?!]{3,90}?)" + end.replace("{other}", "melhora|alivia|passa"), re.I)
        melhora = re.compile(r"\b(?:melhora|melhoram|alivia|aliviam|diminui|passa|fico melhor|fica melhor|ameniza)\b\s+(?:muito\s+|bastante\s+|bem\s+)?" + prep +
                             r"\s+(?P<x>[^.;?!]{3,90}?)" + end.replace("{other}", "piora|agrava"), re.I)
        for s in self.patient_sents():
            t = s["text"]
            for rx, field in ((piora, "queixa.piora"), (melhora, "queixa.melhora")):
                for m in rx.finditer(t):
                    pre = t[max(0, m.start() - 12):m.start()].lower()
                    if re.search(r"n[aã]o\s+(?:\w+\s+)?$", pre) or re.search(r"n[aã]o\s*$", pre):
                        continue  # "não melhora com nada"
                    x = m.group("x")
                    if re.fullmatch(r"nada|ningu[eé]m|nenhum\w*", x.strip(), re.I):
                        continue
                    items = self._split_items(x, s["start"] + m.start("x"))
                    if items:
                        self.add(field, items, 0.75, s["idx"], f"regex {field.split('.')[1]}: verbo + 'com/quando/ao' + fator (verbo → infinitivo)")

    # ------------------------------------------------------------------ hábitos
    def _habit_state(self, e: dict, s: dict) -> str:
        if e["former"]:
            return "ex"
        if e["negated"]:
            return "ex" if re.search(r"\bdesde\b", s["text"], re.I) else "nunca"  # "não bebo desde que descobri..." → parou
        if e.get("tense") == "past" and not PRESENT_RX.search(s["text"]):
            return "ex"
        return "atual"

    def r_habitos(self):
        psents = self.patient_sents()
        # ---- tabagismo
        smoke_states: list[tuple[str, float, int, list[dict]]] = []
        quit_time = None
        for s in psents:
            ents = self.by_sent.get(s["idx"], [])
            for e in ents:
                if e["label"] == "HABITO" and e["attrs"].get("tema") == "tabagismo":
                    st = self._habit_state(e, s)
                    conf = {"nunca": 0.8, "ex": 0.9, "atual": 0.85}[st]
                    if st == "nunca" and not re.search(r"\bnunca\b", s["text"], re.I):
                        conf = 0.7
                    if st == "nunca" and not e["negated"]:
                        continue
                    smoke_states.append((st, conf * e["factor"], s["idx"], [e]))
            for e in ents:
                if e["label"] == "FREQUENCIA" and (e["attrs"].get("unit") in ("cigarros", "maços")) and e["attrs"].get("kind") == "qty_per":
                    a = e["attrs"]
                    qty = a["qty"] * (20 if a["unit"] == "maços" else 1)
                    if a["per"] == "semana":
                        qty = round(qty / 7, 1)
                    habit_ents = [h for h in ents if h["label"] == "HABITO" and h["attrs"].get("tema") == "tabagismo"]
                    neg = any(h["negated"] and not h["former"] for h in habit_ents)
                    if not neg:
                        self.add("habitos.cigarros_dia", qty, 0.9, s["idx"], e["rule"] + " (cigarros/maços por dia)", [e])
                        if not habit_ents:
                            smoke_states.append(("atual", 0.8, s["idx"], [e]))
                        else:
                            past = any(self._habit_state(h, s) == "ex" for h in habit_ents)
                            smoke_states.append(("ex" if past else "atual", 0.8, s["idx"], [e]))
            # anos de tabagismo / tempo desde que parou
            if any(x[2] == s["idx"] for x in smoke_states) or any(h for h in ents if h["label"] == "HABITO" and h["attrs"].get("tema") == "tabagismo"):
                habit = [h for h in ents if h["label"] == "HABITO" and h["attrs"].get("tema") == "tabagismo"]
                for e in ents:
                    if e["label"] != "TEMPO":
                        continue
                    a = e["attrs"]
                    is_ex = any(self._habit_state(h, s) == "ex" for h in habit) or any(x[0] == "ex" and x[2] == s["idx"] for x in smoke_states)
                    years = None
                    if a.get("kind") in ("ago", "duration", "bare") and a.get("unit") in ("anos", "meses"):
                        years = a["qty"] if a["unit"] == "anos" else round(a["qty"] / 12, 1)
                    elif a.get("kind") == "since" and a.get("year"):
                        years = date.today().year - a["year"]
                    if years is None:
                        continue
                    stopped_phr = re.search(r"\b(parei|larguei|deixei|abandonei)\b", s["text"], re.I)
                    if stopped_phr and a.get("kind") == "ago":
                        quit_time = (self.time_text(e), s["idx"])
                        continue
                    if a.get("kind") == "duration" or (a.get("kind") in ("ago", "bare", "since") and not is_ex) or (is_ex and a.get("kind") == "duration"):
                        self.add("habitos.anos_fumo", years, 0.8, s["idx"], e["rule"] + " (tempo de tabagismo)", [e])
        if smoke_states:
            # prioridade: ex > atual > nunca (a afirmação mais forte de mudança vence); empate → mais recente
            order = {"ex": 3, "atual": 2, "nunca": 1}
            best = max(smoke_states, key=lambda x: (order[x[0]] if x[0] != "nunca" else 0, x[1], x[2]))
            if any(x[0] == "nunca" for x in smoke_states) and best[0] == "atual" and any(x[0] == "nunca" and x[2] > best[2] for x in smoke_states):
                best = max([x for x in smoke_states if x[0] == "nunca"], key=lambda x: (x[1], x[2]))
            self.add("habitos.tabagismo", best[0], best[1], best[2], "HABITO(tabagismo) + negação/estado passado", best[3],
                     quit_time=quit_time[0] if quit_time else None)
        self._qa_habits()
        # ---- etilismo
        for s in psents:
            ents = self.by_sent.get(s["idx"], [])
            has_agua = any(e["label"] == "HABITO" and e["attrs"].get("tema") == "agua" for e in ents)
            for e in ents:
                if e["label"] != "HABITO" or e["attrs"].get("tema") not in ("etilismo", "bebida"):
                    continue
                if e["attrs"]["tema"] == "bebida" and (has_agua or not re.search(r"\b(?:socialmente|[àa]lcool|alcoólic|final de semana|festa|cerveja|vinho)\b", s["text"], re.I)):
                    if has_agua or not self.qa_for(s["idx"]):
                        continue
                if e["former"] or (e.get("tense") == "past" and e["attrs"]["tema"] == "etilismo" and not e["negated"] and False):
                    val, conf = "ex", 0.85
                elif e["negated"]:
                    if re.search(r"\bdesde\b", s["text"], re.I):
                        val, conf = "ex", 0.7  # "não bebo desde que descobri a gravidez" → parou
                    else:
                        val, conf = "nunca", 0.8 if re.search(r"\bnunca\b", s["text"], re.I) else 0.7
                else:
                    freq = [x for x in ents if x["label"] == "FREQUENCIA"]
                    if SOCIAL_RX.search(s["text"]):
                        val, conf = "social", 0.8
                    elif HEAVY_RX.search(s["text"]) or any(x["attrs"].get("qty", 0) >= 4 and x["attrs"].get("per") == "semana" for x in freq):
                        val, conf = "frequente", 0.75
                    else:
                        val, conf = "social", 0.5
                self.add("habitos.etilismo", val, conf * e["factor"], s["idx"], "HABITO(etilismo) + negação/frequência", [e])
        # ---- atividade física
        acts, sed = [], False
        for s in psents:
            ents = self.by_sent.get(s["idx"], [])
            for e in ents:
                if e["label"] == "HABITO" and e["attrs"].get("tema") == "atividade":
                    if e["attrs"].get("sedentario") or e["negated"]:
                        sed = True
                        self.add("habitos.atividade_fisica", "Sedentário(a)", 0.8, s["idx"], "HABITO(atividade) negado / sedentarismo", [e])
                    elif affirmed(e):
                        freq = next((x for x in ents if x["label"] == "FREQUENCIA" and x["attrs"].get("unit") == "vezes"), None)
                        freq_txt = ""
                        if freq:
                            freq_txt = f" {num_text(freq['attrs']['qty'])}x/{freq['attrs']['per']}"
                        elif any(x["label"] == "FREQUENCIA" for x in ents):
                            freq_txt = " " + next(x for x in ents if x["label"] == "FREQUENCIA")["attrs"].get("word", "")
                        self.add("habitos.atividade_fisica", f"{cap(e['canonical'] if e['canonical'] != 'atividade física' else e['text'])}{freq_txt}".strip(), 0.8, s["idx"], "HABITO(atividade) + frequência", [e])
        # ---- água, sono, alimentação, intestino, urina (extrativos)
        for s in psents:
            ents = self.by_sent.get(s["idx"], [])
            temas = {e["attrs"].get("tema"): e for e in ents if e["label"] in ("HABITO", "SINTOMA") and e["attrs"].get("tema")}
            for e in ents:
                qa_agua = bool(self.qa.get(s["idx"]) and re.search(r"[áa]gua|hidrat", self.qa[s["idx"]]["q_text"], re.I))
                if e["label"] == "FREQUENCIA" and e["attrs"].get("unit") in ("litros", "copos") and (e["attrs"].get("obj", "") in ("água", "agua") or "agua" in temas or qa_agua):
                    a = e["attrs"]
                    txt = f"{num_text(a['qty'])} {a['unit'][:-1] if a['qty'] == 1 else a['unit']} de água" + (" por dia" if a.get("per") in ("dia", "") else f" por {a['per']}")
                    self.add("habitos.agua", txt, 0.9, s["idx"], e["rule"] + " (água)", [e])
                if e["label"] == "FREQUENCIA" and e["attrs"].get("unit") == "horas" and re.search(r"\b(durmo|dormir|dormindo|sono)\b", s["text"], re.I):
                    self.add("habitos.sono", f"Dorme {num_text(e['attrs']['qty'])} horas por noite", 0.85, s["idx"], e["rule"] + " (horas de sono)", [e])
            if "agua" in temas and not any(c["field"] == "habitos.agua" and c["sent"] == s["idx"] for c in self.cands):
                if re.search(r"\b(pouca?|muita?|bastante|nada|quase nada)\b", s["text"], re.I) or temas["agua"]["negated"]:
                    self.add("habitos.agua", s["text"].rstrip("."), 0.6, s["idx"], "HABITO(água) + intensificador", [temas["agua"]])
            for tema, field in (("sono", "habitos.sono"), ("alimentacao", "habitos.alimentacao"), ("intestino", "habitos.intestino"), ("urina", "habitos.urina")):
                if tema in temas:
                    e = temas[tema]
                    # exige conteúdo (≥ 3 palavras) e que não seja só o termo solto
                    if len(re.findall(r"\w+", s["text"])) >= 3 and not (e["negated"] and tema == "alimentacao" and False):
                        if any(c["field"] == field and c["sent"] == s["idx"] for c in self.cands):
                            continue
                        pen = 0.7 if any(x["label"] == "MEDICAMENTO" for x in ents) else 1.0  # o sintoma é só o motivo do remédio
                        self.add(field, s["text"].rstrip("."), 0.7 * e["factor"] * pen, s["idx"], f"extração da sentença (tema {tema})", [e])
        # ---- ciclo menstrual
        for s in psents:
            if re.search(r"\b(menstrua\w*|ciclo (?:menstrual|regular|irregular)|menopausa|tpm|menstrual|fluxo)\b", s["text"], re.I):
                self.add("saude.ciclo", s["text"].rstrip("."), 0.7, s["idx"], "regex ciclo menstrual (extração da sentença)")

    def _qa_habits(self):
        """Respostas curtas a perguntas sobre hábitos: 'Você fuma?' + 'Não.'"""
        for si, qa in self.qa.items():
            pol = self.answer_polarity(si)
            if pol is None:
                continue
            s = self.sents[si]
            own = self.by_sent.get(si, [])
            for qe in qa["q_ents"]:
                tema = qe["attrs"].get("tema") if qe["label"] == "HABITO" else None
                if tema == "tabagismo" and not any(e["label"] == "HABITO" and e["attrs"].get("tema") == "tabagismo" for e in own):
                    val = "nunca" if pol == "neg" else "atual"
                    self.add("habitos.tabagismo", val, 0.7 if pol != "partial" else 0.55, si, "resposta curta a pergunta (QA): fuma?", [qe])
                if tema in ("etilismo", "bebida") and not any(e["label"] == "HABITO" and e["attrs"].get("tema") in ("etilismo", "bebida") for e in own):
                    if tema == "bebida" and re.search(r"[áa]gua", qa["q_text"], re.I):
                        continue
                    val = "nunca" if pol == "neg" else "social"
                    self.add("habitos.etilismo", val, 0.7 if pol != "partial" else 0.65, si, "resposta curta a pergunta (QA): bebe?", [qe])

    # ------------------------------------------------------------------ saúde
    def _family_ctx(self, e: dict, s: dict) -> dict | None:
        fam = [f for f in self.by_sent.get(s["idx"], []) if f["label"] == "FAMILIAR" and f["start"] < e["start"] and e["start"] - f["end"] < 70]
        if fam:
            return fam[-1]
        if re.search(r"\b(na minha fam[ií]lia|casos na fam[ií]lia|hist[oó]rico familiar|de fam[ií]lia)\b", s["text"], re.I):
            return {"canonical": "família", "attrs": {"generic": True}}
        return None

    def r_saude(self):
        for s in self.patient_sents():
            si = s["idx"]
            ents = self.by_sent.get(si, [])
            allergy = bool(re.search(r"\b(al[eé]rgic[oa]s?|alergia|alergias|alergia a)\b", s["text"], re.I))
            neg_allergy = bool(re.search(r"\b(n[aã]o|nunca|nenhuma?|sem)\b[^.]{0,25}\b(al[eé]rgic[oa]|alergia)", s["text"], re.I))
            for e in ents:
                fam = self._family_ctx(e, s) if e["label"] in ("DOENCA",) else None
                if e["label"] == "DOENCA":
                    if not affirmed(e) and not e["former"]:
                        continue
                    if fam:
                        who = cap(fam["canonical"]) if not fam["attrs"].get("generic") else "Família"
                        self.add("saude.hist_familiar", [f"{who}: {e['canonical']}"], 0.8 * e["factor"], si, "FAMILIAR + DOENCA na mesma frase", [e])
                    elif allergy:
                        continue
                    else:
                        label = cap(e["canonical"]) + (" (passado)" if e["former"] else "")
                        self.add("saude.doencas", [label], 0.85 * e["factor"], si, e["rule"], [e])
                elif e["label"] == "MEDICAMENTO":
                    if allergy and not neg_allergy:
                        self.add("saude.alergias", [cap(e["canonical"])], 0.8 * e["factor"], si, "MEDICAMENTO em frase de alergia", [e])
                        continue
                    if not affirmed(e) or fam is not None:
                        continue
                    meds = [m for m in ents if m["label"] == "MEDICAMENTO"]
                    dose = next((d for d in ents if d["label"] == "DOSE" and 0 <= d["start"] - e["end"] < 25
                                 and not any(m is not e and e["end"] <= m["start"] < d["start"] for m in meds)), None)
                    name = cap(e["text"] if e["text"].isupper() else e["canonical"])
                    if dose:
                        name += f" {num_text(dose['attrs']['qty'])} {dose['attrs']['unit']}"
                    self.add("saude.medicamentos", [name], 0.85 * e["factor"], si, e["rule"] + (" + dose" if dose else ""), [e])
                elif e["label"] == "CIRURGIA":
                    if not affirmed(e) and not e["former"]:
                        continue
                    generic = e["attrs"].get("generic")
                    tempo = next((t for t in ents if t["label"] == "TEMPO" and abs(t["start"] - e["end"]) < 40 and t["attrs"].get("kind") in ("year", "ago", "since")), None)
                    part = next((p for p in ents if p["label"] == "PARTE_CORPO" and abs(p["start"] - e["start"]) < 30), None)
                    name = cap(e["canonical"])
                    if generic and part:
                        name = f"Cirurgia ({part['canonical']})"
                    elif generic:
                        if not tempo:
                            continue
                    if tempo:
                        name += f" ({self.time_text(tempo).replace('Em ', '')})"
                    self.add("saude.cirurgias", [name], 0.8 * e["factor"], si, e["rule"], [e])
                elif e["label"] == "ALERGENO":
                    if allergy and not neg_allergy and affirmed(e):
                        self.add("saude.alergias", [cap(e["text"].lower())], 0.85 * e["factor"], si, "ALERGENO em frase de alergia", [e])
            if allergy and not neg_allergy:
                for m in re.finditer(r"\bal[eé]rgic[oa]s?\s+(?:a|ao|à|aos|às)\s+(?P<x>[^.;,]{3,40}?)(?=[.;,]|\s+e\s+|$)", s["text"], re.I):
                    x = m.group("x").strip()
                    if not any(fold(x) in fold(c["value"][0]) or fold(c["value"][0]) in fold(x) for c in self.cands if c["field"] == "saude.alergias" and c["sent"] == si):
                        self.add("saude.alergias", [cap(x)], 0.7, si, "regex 'alérgico a ...'")
        # respostas curtas sobre doenças/medicamentos viram contraindicações em r_contra

    # ------------------------------------------------------------------ contraindicações
    def r_contra(self):
        for s in self.sents:
            if s["speaker"] != "paciente":
                continue
            for e in self.by_sent.get(s["idx"], []):
                contra = e["attrs"].get("contra")
                if not contra or e["label"] not in ("CONDICAO", "DOENCA", "MEDICAMENTO"):
                    continue
                field = f"contra.{contra}"
                if self._family_ctx(e, s) is not None and e["label"] == "DOENCA":
                    continue
                if e["negated"]:
                    self.add(field, False, 0.85, s["idx"], f"{e['label']} negado → contraindicação ausente", [e], status="negado")
                elif e["former"]:
                    continue
                else:
                    self.add(field, True, 0.9, s["idx"], f"{e['label']} afirmado → contraindicação presente", [e])
        # respostas curtas: "Está grávida?" "Não." / "Toma anticoagulante?" "Tomo."
        for si, qa in self.qa.items():
            pol = self.answer_polarity(si)
            if pol is None:
                continue
            own_contra = {e["attrs"].get("contra") for e in self.by_sent.get(si, [])}
            for qe in qa["q_ents"]:
                contra = qe["attrs"].get("contra")
                if not contra or contra in own_contra:
                    continue
                self.add(f"contra.{contra}", pol != "neg", 0.8 if pol != "partial" else 0.6, si, "resposta curta a pergunta (QA)", [qe],
                         status="negado" if pol == "neg" else "afirmado")
                if contra == "diabetes" and pol != "neg":
                    self.add("saude.doencas", ["Diabetes"], 0.8, si, "resposta curta a pergunta (QA)", [qe])

    # ------------------------------------------------------------------ MTC
    def r_mtc(self):
        for s in self.sents:
            for e in self.by_sent.get(s["idx"], []):
                if e["label"] != "MTC":
                    continue
                cat = e["attrs"].get("categoria")
                if cat == "lingua_desc":
                    self.add("mtc.lingua", cap(e["canonical"]), 0.85 * (e["conf"] / 0.9), s["idx"], e["rule"], [e])
                elif cat == "pulso_desc":
                    self.add("mtc.pulso", cap(e["canonical"]), 0.85 * (e["conf"] / 0.9), s["idx"], e["rule"], [e])
                elif cat == "padrao":
                    self.add("mtc.padroes", [cap(e["canonical"])], 0.85, s["idx"], e["rule"], [e])
                elif cat == "principio" and not e["negated"]:
                    seg = self.text[e["start"]:s["end"]]
                    cut = re.search(r"\b(?:usando|utilizando|com (?:os )?pontos?|atrav[eé]s|por meio|e vou usar|vou usar)\b|[.;?!]", seg, re.I)
                    phrase = (seg[:cut.start()] if cut else seg).strip(" ,;")
                    if len(phrase) > 4:
                        self.add("mtc.principio", cap(phrase), 0.8, s["idx"], "MTC(princípio) + trecho até o fim da cláusula", [e])

    # ------------------------------------------------------------------ plano / SOAP
    def r_plano_soap(self):
        pontos_seen = False
        tecnica_seen = False
        for s in self.sents:
            si = s["idx"]
            ents = self.by_sent.get(si, [])
            for e in ents:
                if e["label"] == "PONTO" and affirmed(e) and e["attrs"].get("code"):
                    pontos_seen = True
                    self.add("soap.p_pontos", [e["attrs"]["code"]], 0.95 * e["factor"], si, e["rule"], [e])
                if e["label"] == "TECNICA" and affirmed(e) and s["speaker"] == "profissional":
                    opc = e["attrs"].get("opcao")
                    if opc:
                        tecnica_seen = True
                        self.add("plano.tecnicas", [opc], 0.85 * e["factor"], si, e["rule"], [e])
                        self.add("soap.p_tecnica", [opc], 0.85 * e["factor"], si, e["rule"], [e])
                if e["label"] == "TEMPO" and e["attrs"].get("kind") == "minutes" and s["speaker"] == "profissional":
                    if re.search(r"\b(agulha|reten|deixar|ficar|fica|sess[aã]o|aplic|moxa|ventosa|eletro|total)\w*", s["text"], re.I):
                        self.add("soap.p_tempo", e["attrs"]["qty"], 0.85, si, e["rule"] + " (tempo de retenção)", [e])
            if s["speaker"] == "profissional":
                t = s["text"]
                if re.search(r"\b(semanal(?:mente)?|quinzenal(?:mente)?|mensal(?:mente)?)\b", t, re.I) and re.search(r"sess|atendimento|vir|vem|retorn|frequ", t, re.I):
                    w = re.search(r"\b(semanal(?:mente)?|quinzenal(?:mente)?|mensal(?:mente)?)\b", t, re.I).group(1).lower()
                    self.add("plano.frequencia", cap(w), 0.8, si, "regex frequência (semanal/quinzenal)")
                for e in ents:
                    if e["label"] == "FREQUENCIA" and e["attrs"].get("unit") == "vezes" and e["attrs"].get("per") in ("semana", "mês") and re.search(r"sess|atendimento|vir|vem|retorn|frequ|semana", t, re.I):
                        self.add("plano.frequencia", f"{num_text(e['attrs']['qty'])} vez{'es' if e['attrs']['qty'] != 1 else ''} por {e['attrs']['per']}", 0.85, si, e["rule"], [e])
                m = re.search(r"(?<!\d)(\d{1,2})\s+sess[oõ]es\b", t, re.I)
                if m:
                    self.add("plano.sessoes", int(m.group(1)), 0.85, si, "regex 'N sessões'")
                if re.search(r"\b(palpa[cç][aã]o|palpo|contratura|n[oó]dulo|ponto[- ]gatilho|rigidez|edema|limita[cç][aã]o|amplitude|postura|tens[aã]o (?:muscular )?(?:em|no|na|nos|nas)|dor [àa] palpa)", t, re.I) and "?" not in t:
                    self.add("soap.o_obs", t.rstrip("."), 0.7, si, "regex observação objetiva (palpação/contratura/amplitude)")
                if re.search(r"\b(oriento|orientei|recomendo|recomendei|evite|evitar|procure|beba|repouso|compressa|compressas|alongamento|alongamentos|mantenha|descanse|hidrate|reduza|aplique|diminua|fa[cç]a|evitem)\b", t, re.I) and "?" not in t:
                    self.add("soap.p_orientacoes", t.rstrip("."), 0.75, si, "regex orientação ao paciente")
                if re.search(r"\b(pr[oó]xima sess[aã]o|retorno|volte|volta|nos vemos|semana que vem|pr[oó]xima semana|daqui a \d+|em \d+ (?:dias|semanas))\b", t, re.I) and "?" not in t:
                    self.add("soap.p_proxima", t.rstrip("."), 0.75, si, "regex próxima sessão/retorno")
            if re.search(r"\b(rea[cç][aã]o|rea[cç][oõ]es|intercorr[eê]ncia|tontura|desmai|mal[- ]estar|hematoma|sangramento|n[aá]usea)\w*", s["text"], re.I) and self.mode == "soap":
                t = s["text"]
                if re.search(r"\b(sem|nenhuma|nenhum|n[aã]o (?:houve|teve|tive|apresentou))\b[^.]{0,25}(rea[cç]|intercorr|tontura|hematoma|sangramento)", t, re.I):
                    self.add("soap.p_reacoes", "Sem reações adversas", 0.8, si, "regex ausência de reações")
                elif "?" not in t:
                    self.add("soap.p_reacoes", t.rstrip("."), 0.7, si, "regex reação adversa")
        # técnica implícita: pontos do corpo citados e nenhuma técnica de agulha explícita (sistêmica/eletro).
        # Moxa sozinha sobre os pontos não implica agulhamento.
        if pontos_seen:
            tecs = {c["value"][0] for c in self.cands if c["field"] == "plano.tecnicas"}
            if not (tecs & {"sistemica", "eletroacupuntura"}) and tecs != {"moxabustao"}:
                si = next(c["sent"] for c in self.cands if c["field"] == "soap.p_pontos")
                msg = "pontos do corpo citados sem técnica de agulha explícita → acupuntura sistêmica (implícita)"
                self.add("plano.tecnicas", ["sistemica"], 0.55, si, msg)
                self.add("soap.p_tecnica", ["sistemica"], 0.55, si, msg)
        # evolução (SOAP)
        if self.mode == "soap":
            for s in self.patient_sents():
                t = s["text"]
                if "?" in t:
                    continue
                label = None
                if IMPROVE_RX.search(t) and not re.search(r"\bn[aã]o\b[^.]{0,20}(melhor|aliv|diminu)", t, re.I):
                    label = "Melhora relatada pelo paciente"
                elif STABLE_RX.search(t):
                    label = "Quadro estável, sem mudança relatada"
                elif WORSEN_RX.search(t):
                    label = "Piora relatada pelo paciente"
                if label:
                    eva_now = next((c["value"] for c in self.cands if c["field"] == "queixa.eva"), None)
                    prev = self.prev.get("eva")
                    if eva_now is not None and prev is not None:
                        label += f" (EVA {prev} → {eva_now})"
                    self.add("soap.a_evolucao", label, 0.75, s["idx"], "regex evolução (melhorou/piorou/igual)")
                    break
