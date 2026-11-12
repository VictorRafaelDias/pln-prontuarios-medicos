"""Schema do formulário clínico — fonte única de verdade para backend, pipeline, LLM e frontend.

Cada campo tem um id estável (``secao.nome``). O frontend renderiza o formulário a partir de
``GET /api/form-schema``; o pipeline de PLN mapeia entidades para estes ids; o LLM recebe o schema
como lista de campos permitidos.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

# ---------------------------------------------------------------------------
# Regiões do mapa corporal
# ---------------------------------------------------------------------------
REGIONS: dict[str, str] = {
    "cabeca": "Cabeça", "cervical": "Pescoço / nuca", "pescoco": "Garganta",
    "ombro_d": "Ombro direito", "ombro_e": "Ombro esquerdo",
    "torax": "Tórax", "dorsal": "Dorsal (costas)", "abdomen": "Abdômen", "lombar": "Lombar",
    "braco_d": "Braço direito", "braco_e": "Braço esquerdo",
    "cotovelo_d": "Cotovelo direito", "cotovelo_e": "Cotovelo esquerdo",
    "antebraco_d": "Antebraço direito", "antebraco_e": "Antebraço esquerdo",
    "mao_d": "Mão direita", "mao_e": "Mão esquerda",
    "quadril_d": "Quadril direito", "quadril_e": "Quadril esquerdo",
    "gluteo_d": "Glúteo direito", "gluteo_e": "Glúteo esquerdo",
    "coxa_d": "Coxa direita", "coxa_e": "Coxa esquerda",
    "joelho_d": "Joelho direito", "joelho_e": "Joelho esquerdo",
    "perna_d": "Perna direita", "perna_e": "Perna esquerda",
    "pe_d": "Pé direito", "pe_e": "Pé esquerdo",
}

TIPOS_DOR = ["pontada", "queimação", "latejante", "peso", "aperto", "choque", "cólica",
             "formigamento", "dormência", "irradiada", "surda"]
HORARIOS = ["ao acordar", "manhã", "tarde", "noite", "madrugada", "ao longo do dia"]
TECNICAS = ["sistemica", "auriculoterapia", "eletroacupuntura", "moxabustao", "ventosa"]
TECNICAS_LABEL = {"sistemica": "Acupuntura sistêmica", "auriculoterapia": "Auriculoterapia",
                  "eletroacupuntura": "Eletroacupuntura", "moxabustao": "Moxabustão", "ventosa": "Ventosaterapia"}

SECTIONS: list[dict] = [
    {"id": "queixa", "title": "Queixa principal", "modes": ["anamnese"]},
    {"id": "secundarias", "title": "Queixas secundárias", "modes": ["anamnese"]},
    {"id": "habitos", "title": "Hábitos", "modes": ["anamnese"]},
    {"id": "saude", "title": "Histórico de saúde", "modes": ["anamnese"]},
    {"id": "contra", "title": "Contraindicações", "modes": ["anamnese", "soap"]},
    {"id": "mtc", "title": "Avaliação MTC", "modes": ["anamnese"]},
    {"id": "plano", "title": "Plano de tratamento", "modes": ["anamnese"]},
    {"id": "soap_s", "title": "S — Subjetivo", "modes": ["soap"]},
    {"id": "soap_o", "title": "O — Objetivo", "modes": ["soap"]},
    {"id": "soap_a", "title": "A — Avaliação", "modes": ["soap"]},
    {"id": "soap_p", "title": "P — Plano / conduta da sessão", "modes": ["anamnese", "soap"]},
]


def _f(fid: str, section: str, label: str, ftype: str, **kw: Any) -> dict:
    d = {"id": fid, "section": section, "label": label, "type": ftype}
    d.update(kw)
    return d


FIELDS: list[dict] = [
    # --- Queixa principal
    _f("queixa.descricao", "queixa", "Descrição da queixa", "textarea", required=True, hint="Queixa principal do paciente, em poucas palavras."),
    _f("queixa.localizacao", "queixa", "Localização (mapa corporal)", "bodymap", hint="Lista de ids de regiões do corpo afetadas."),
    _f("queixa.eva", "queixa", "Intensidade da dor (EVA 0–10)", "scale", required=True, hint="Escala visual analógica, inteiro de 0 a 10."),
    _f("queixa.inicio", "queixa", "Início / duração", "text", hint="Há quanto tempo começou, ex.: 'há 3 meses'."),
    _f("queixa.tipo_dor", "queixa", "Tipo de dor", "multiselect", options=TIPOS_DOR),
    _f("queixa.piora", "queixa", "Fatores de piora", "list"),
    _f("queixa.melhora", "queixa", "Fatores de melhora", "list"),
    _f("queixa.horario_pior", "queixa", "Horário de pior intensidade", "select", options=HORARIOS),
    # --- Secundárias
    _f("secundarias.lista", "secundarias", "Queixas secundárias", "list"),
    # --- Hábitos
    _f("habitos.tabagismo", "habitos", "Tabagismo", "select", options=["nunca", "ex", "atual"], hint="nunca = nunca fumou; ex = parou de fumar; atual = fuma hoje."),
    _f("habitos.cigarros_dia", "habitos", "Cigarros por dia", "number", unit="cigarros/dia"),
    _f("habitos.anos_fumo", "habitos", "Anos de tabagismo", "number", unit="anos"),
    _f("habitos.maco_ano", "habitos", "Carga tabágica (maços-ano)", "computed", unit="maços-ano", hint="Calculado: (cigarros/dia ÷ 20) × anos."),
    _f("habitos.etilismo", "habitos", "Etilismo", "select", options=["nunca", "social", "frequente", "ex"]),
    _f("habitos.atividade_fisica", "habitos", "Atividade física", "text"),
    _f("habitos.sono", "habitos", "Sono", "text"),
    _f("habitos.alimentacao", "habitos", "Alimentação", "text"),
    _f("habitos.agua", "habitos", "Água", "text", hint="Ex.: '2 litros por dia'."),
    _f("habitos.intestino", "habitos", "Intestino", "text"),
    _f("habitos.urina", "habitos", "Urina", "text"),
    _f("habitos.estresse", "habitos", "Estresse (0–10)", "scale"),
    # --- Histórico de saúde
    _f("saude.doencas", "saude", "Doenças crônicas", "list"),
    _f("saude.cirurgias", "saude", "Cirurgias", "list"),
    _f("saude.medicamentos", "saude", "Medicamentos em uso", "list"),
    _f("saude.alergias", "saude", "Alergias", "list"),
    _f("saude.hist_familiar", "saude", "Histórico familiar", "list"),
    _f("saude.ciclo", "saude", "Ciclo menstrual (se aplicável)", "text"),
    # --- Contraindicações
    _f("contra.gestacao", "contra", "Gestação", "bool", alert="Gestação", hint="true se gestante; false se negou."),
    _f("contra.anticoagulantes", "contra", "Uso de anticoagulantes", "bool", alert="Anticoagulantes"),
    _f("contra.marcapasso", "contra", "Marcapasso", "bool", alert="Marcapasso"),
    _f("contra.coagulacao", "contra", "Distúrbio de coagulação", "bool", alert="Distúrbio de coagulação"),
    _f("contra.diabetes", "contra", "Diabetes", "bool", alert="Diabetes"),
    _f("contra.medo_agulha", "contra", "Medo de agulha", "bool", alert="Medo de agulha"),
    _f("contra.lesoes_pele", "contra", "Lesões de pele", "bool", alert="Lesões de pele"),
    # --- MTC
    _f("mtc.lingua", "mtc", "Língua", "text", hint="Cor, forma, saburra."),
    _f("mtc.pulso", "mtc", "Pulso", "text"),
    _f("mtc.padroes", "mtc", "Padrões / síndromes", "list"),
    _f("mtc.principio", "mtc", "Princípio de tratamento", "text"),
    # --- Plano
    _f("plano.tecnicas", "plano", "Técnicas planejadas", "multiselect", options=TECNICAS, option_labels=TECNICAS_LABEL),
    _f("plano.frequencia", "plano", "Frequência", "text", hint="Ex.: 'semanal'."),
    _f("plano.sessoes", "plano", "Nº de sessões previsto", "number"),
    # --- SOAP
    _f("soap.s_relato", "soap_s", "Relato do paciente", "textarea", required=True),
    _f("soap.s_eva", "soap_s", "EVA atual (0–10)", "scale", required=True),
    _f("soap.o_lingua", "soap_o", "Língua", "text"),
    _f("soap.o_pulso", "soap_o", "Pulso", "text"),
    _f("soap.o_obs", "soap_o", "Observações", "textarea"),
    _f("soap.a_evolucao", "soap_a", "Evolução", "textarea"),
    _f("soap.a_padrao", "soap_a", "Padrão atual", "text"),
    _f("soap.p_pontos", "soap_p", "Pontos utilizados", "points", required=True, hint="Códigos de pontos, ex.: VB20, E36, IG4."),
    _f("soap.p_tecnica", "soap_p", "Técnica", "multiselect", options=TECNICAS, option_labels=TECNICAS_LABEL),
    _f("soap.p_tempo", "soap_p", "Tempo de retenção (min)", "number", unit="min"),
    _f("soap.p_reacoes", "soap_p", "Reações", "text"),
    _f("soap.p_orientacoes", "soap_p", "Orientações", "textarea"),
    _f("soap.p_proxima", "soap_p", "Próxima sessão", "text"),
]

FIELD_BY_ID: dict[str, dict] = {f["id"]: f for f in FIELDS}
SECTION_BY_ID: dict[str, dict] = {s["id"]: s for s in SECTIONS}

# Em sessões SOAP, os ids "canônicos" do pipeline são traduzidos para os campos SOAP equivalentes.
SOAP_ALIAS: dict[str, str] = {
    "queixa.descricao": "soap.s_relato",
    "queixa.eva": "soap.s_eva",
    "mtc.lingua": "soap.o_lingua",
    "mtc.pulso": "soap.o_pulso",
    "mtc.padroes": "soap.a_padrao",
    "plano.tecnicas": "soap.p_tecnica",
}


def fields_for_mode(mode: str) -> list[dict]:
    sections = {s["id"] for s in SECTIONS if mode in s["modes"]}
    return [f for f in FIELDS if f["section"] in sections]


def field_ids_for_mode(mode: str) -> list[str]:
    return [f["id"] for f in fields_for_mode(mode)]


def alias_for_mode(field_id: str, mode: str) -> str | None:
    """Traduz um id canônico para o id usado no modo; None se o campo não existe no modo."""
    if mode == "soap":
        field_id = SOAP_ALIAS.get(field_id, field_id)
    return field_id if field_id in field_ids_for_mode(mode) else None


def schema_payload() -> dict:
    return {"sections": SECTIONS, "fields": FIELDS, "regions": REGIONS,
            "tipos_dor": TIPOS_DOR, "horarios": HORARIOS, "tecnicas": TECNICAS}


# ---------------------------------------------------------------------------
# Normalização de valores
# ---------------------------------------------------------------------------
def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


_POINT_RE = re.compile(r"^(EX-HN\d{1,2}|AURIC-[A-Z]+|[A-Z]{1,2}\d{1,2})$")
_SOURCES = {"rules", "llm", "both", "manual", "calc"}


def is_valid_point(code: str) -> bool:
    """Código de ponto existente: prefixo de meridiano conhecido e número dentro do total do canal (VB1–44, E1–45...)."""
    if not _POINT_RE.match(code):
        return False
    if code.startswith(("EX-HN", "AURIC-")):
        return True
    m = re.match(r"^([A-Z]{1,2})(\d{1,2})$", code)
    from .resources import get_resources  # import tardio: resources depende deste módulo
    mer = get_resources()["points"]["meridianos"].get(m.group(1))
    return bool(mer and 1 <= int(m.group(2)) <= mer["n"])


def normalize_point(code: str) -> str:
    c = re.sub(r"[\s\-_]", "", str(code).upper())
    if c.startswith("EXHN"):
        c = "EX-HN" + c[4:]
    return c


def normalize_value(field_id: str, raw: Any) -> Any:
    """Coage um valor bruto (vindo do LLM, do usuário ou das regras) para o tipo do campo. None = inválido."""
    f = FIELD_BY_ID.get(field_id)
    if f is None or raw is None:
        return None
    t = f["type"]
    try:
        if t in ("text", "textarea"):
            if isinstance(raw, (list, tuple)):
                raw = "; ".join(str(x) for x in raw)
            v = str(raw).strip()
            return v or None
        if t in ("number", "computed"):
            if isinstance(raw, bool):
                return None
            if isinstance(raw, str):
                m = re.search(r"-?\d+(?:[.,]\d+)?", raw)
                if not m:
                    return None
                raw = m.group(0).replace(",", ".")
            n = float(raw)
            return int(n) if n == int(n) else round(n, 2)
        if t == "scale":
            if isinstance(raw, str):
                m = re.search(r"\d+(?:[.,]\d+)?", raw)
                if not m:
                    return None
                raw = m.group(0).replace(",", ".")
            n = round(float(raw))
            return max(0, min(10, int(n)))
        if t == "select":
            fo = fold(str(raw))
            for opt in f["options"]:
                if fold(opt) == fo:
                    return opt
            for opt in f["options"]:
                if fold(opt) in fo or fo in fold(opt):
                    return opt
            return None
        if t == "multiselect":
            items = raw if isinstance(raw, (list, tuple)) else [raw]
            out = []
            for it in items:
                fi = fold(str(it))
                for opt in f["options"]:
                    label = f.get("option_labels", {}).get(opt, opt)
                    if fi in (fold(opt), fold(label)) and opt not in out:
                        out.append(opt)
            return out or None
        if t == "bool":
            if isinstance(raw, bool):
                return raw
            s = fold(str(raw))
            if s in ("true", "sim", "1", "yes", "verdadeiro"):
                return True
            if s in ("false", "nao", "0", "no", "falso"):
                return False
            return None
        if t == "list":
            items = raw if isinstance(raw, (list, tuple)) else re.split(r"[;\n]", str(raw))
            out: list[str] = []
            for it in items:
                s = str(it).strip()
                if s and fold(s) not in [fold(o) for o in out]:
                    out.append(s)
            return out or None
        if t == "bodymap":
            items = raw if isinstance(raw, (list, tuple)) else [raw]
            out = [str(i) for i in items if str(i) in REGIONS]
            return list(dict.fromkeys(out)) or None
        if t == "points":
            items = raw if isinstance(raw, (list, tuple)) else re.split(r"[,;\s]+", str(raw))
            out = []
            for it in items:
                c = normalize_point(it)
                if c and is_valid_point(c) and c not in out:
                    out.append(c)
            return out or None
    except (ValueError, TypeError):
        return None
    return None


def compute_maco_ano(values: dict[str, Any]) -> float | None:
    """Maços-ano = (cigarros por dia ÷ 20) × anos de tabagismo."""
    cig = values.get("habitos.cigarros_dia")
    anos = values.get("habitos.anos_fumo")
    if isinstance(cig, (int, float)) and isinstance(anos, (int, float)) and cig > 0 and anos > 0:
        return round((cig / 20.0) * anos, 1)
    return None


def sanitize_form(form, kind: str) -> dict:
    """Saneia o preenchimento recebido do cliente: descarta campos desconhecidos/fora do modo, normaliza valores pelo tipo do campo
    (EVA > 10 vira 10, pontos inexistentes caem) e força origem, confiança e estrutura válidas."""
    allowed = set(field_ids_for_mode(kind)) | {"habitos.maco_ano"}
    out: dict = {}
    if not isinstance(form, dict):
        return out
    for fid, f in form.items():
        if fid not in allowed or not isinstance(f, dict) or "value" not in f:
            continue
        v = normalize_value(fid, f["value"])
        if v is None:
            continue
        src = f.get("source") if f.get("source") in _SOURCES else "manual"
        try:
            conf = max(0.0, min(1.0, float(f.get("confidence", 1.0 if src == "manual" else 0.5))))
        except (TypeError, ValueError):
            conf = 1.0 if src == "manual" else 0.5
        rec = {"value": v, "source": src, "confidence": round(conf, 3), "evidence": str(f.get("evidence") or "")[:500],
               "confirmed": bool(f.get("confirmed", src == "manual"))}
        for k in ("conflict", "uncertain"):
            if k in f:
                rec[k] = bool(f[k])
        for k in ("rule", "note", "status"):
            if isinstance(f.get(k), str):
                rec[k] = f[k][:300]
        if isinstance(f.get("alternatives"), list):
            rec["alternatives"] = [{k: a.get(k) for k in ("value", "confidence", "evidence", "source") if k in a}
                                   for a in f["alternatives"][:3] if isinstance(a, dict)]
        out[fid] = rec
    return out
