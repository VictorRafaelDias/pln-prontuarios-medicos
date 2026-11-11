"""Extração por LLM (Anthropic SDK) — roda SOMENTE no backend; a chave nunca vai ao navegador.

Usa *saída estruturada* (``output_config.format`` = json_schema), que garante JSON válido segundo o schema,
sem forçar ``tool_choice`` (modelos recentes rejeitam tool_choice forçado).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from .form_schema import FIELD_BY_ID, REGIONS, field_ids_for_mode, fields_for_mode, is_empty, normalize_value

try:  # carrega .env da raiz do projeto
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except Exception:  # noqa: BLE001
    pass

# US$ por milhão de tokens (entrada, saída) — valores de referência; sobrescreva no .env
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0), "claude-opus-5": (5.0, 25.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50), "claude-fable-5-2": (8.0, 40.0), "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-4-8": (5.0, 25.0), "claude-sonnet-4-6": (3.0, 15.0), "claude-haiku-4-5": (1.0, 5.0),
}
_EFFORT_MODELS = re.compile(r"^claude-(?:opus|sonnet|haiku|fable|mythos)-(?:5|4-[678])")
_FALLBACK_MODELS = re.compile(r"^claude-(?:opus-5|sonnet-5-5|fable-5)")
_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()
_client = None
_baseline_overhead: dict[str, int] = {}


def settings() -> dict[str, Any]:
    model = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5").strip() or "claude-opus-5-5"
    pin, pout = PRICES.get(model, (4.0, 20.0))
    return {
        "api_key_set": bool(os.getenv("ANTHROPIC_API_KEY", "").strip()),
        "model": model,
        "effort": os.getenv("ANTHROPIC_EFFORT", "low").strip().lower(),
        "price_in": float(os.getenv("ANTHROPIC_PRICE_IN_PER_MTOK", pin)),
        "price_out": float(os.getenv("ANTHROPIC_PRICE_OUT_PER_MTOK", pout)),
        "use_fallbacks": os.getenv("ANTHROPIC_USE_FALLBACKS", "true").lower() in ("1", "true", "yes", "sim"),
    }


def available() -> bool:
    return settings()["api_key_set"]


def get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def set_client(c) -> None:
    """Permite injetar um cliente falso em testes."""
    global _client
    _client = c


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    st = settings()
    return round(input_tokens * st["price_in"] / 1e6 + output_tokens * st["price_out"] / 1e6, 6)


# ---------------------------------------------------------------------------
# Contagem de tokens (etapa 4)
# ---------------------------------------------------------------------------
def count_tokens_info(text: str, n_words: int) -> dict:
    st = settings()
    info = {"available": False, "tokens": None, "estimated": None, "model": st["model"], "ratio": None, "note": ""}
    if not st["api_key_set"]:
        est = math.ceil(len(text) / 3.5)
        info.update({"estimated": est, "ratio": round(est / max(1, n_words), 2),
                     "note": "Sem ANTHROPIC_API_KEY: valor ESTIMADO (≈ caracteres ÷ 3,5). Configure a chave para a contagem real."})
        return info
    try:
        c = get_client()
        total = c.messages.count_tokens(model=st["model"], messages=[{"role": "user", "content": text}]).input_tokens
        if st["model"] not in _baseline_overhead:
            base = c.messages.count_tokens(model=st["model"], messages=[{"role": "user", "content": "a"}]).input_tokens
            _baseline_overhead[st["model"]] = max(0, base - 1)
        net = max(0, total - _baseline_overhead[st["model"]])
        info.update({"available": True, "tokens": net, "ratio": round(net / max(1, n_words), 2),
                     "note": f"Contagem real via messages.count_tokens ({st['model']}); descontado o envelope fixo da mensagem."})
    except Exception as e:  # noqa: BLE001
        est = math.ceil(len(text) / 3.5)
        info.update({"estimated": est, "ratio": round(est / max(1, n_words), 2), "note": f"Falha na contagem real ({type(e).__name__}); mostrando estimativa."})
    return info


# ---------------------------------------------------------------------------
# Schema e prompt
# ---------------------------------------------------------------------------
def build_schema(mode: str) -> dict:
    ids = field_ids_for_mode(mode)
    return {
        "type": "object",
        "properties": {
            "campos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "campo": {"type": "string", "enum": ids},
                        "valor": {"anyOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"},
                                            {"type": "array", "items": {"type": "string"}}]},
                        "confianca": {"type": "number"},
                        "trecho": {"type": "string"},
                    },
                    "required": ["campo", "valor", "confianca", "trecho"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["campos"],
        "additionalProperties": False,
    }


SYSTEM_PROMPT = """Você é um assistente de documentação clínica de uma clínica de acupuntura no Brasil. Você recebe a transcrição de uma consulta entre o ACUPUNTURISTA (profissional) e o PACIENTE e preenche o prontuário.

REGRAS
1. Preencha SOMENTE o que foi dito na transcrição. NÃO invente dados. Se algo não foi dito, OMITA o campo (não use "não informado").
2. Escreva em português do Brasil, em linguagem clínica concisa. Valores de texto curtos (uma frase no máximo, exceto relato/observações/orientações).
3. Respeite negações e estados passados: "não fumo" → tabagismo "nunca"; "parei de fumar" → "ex"; "fumo 10 por dia" → "atual". Incerteza ("acho que", "talvez") deve reduzir a confiança.
4. Contraindicações são booleanas: true se presentes, false SOMENTE se o paciente negou explicitamente; omita se não foram abordadas.
5. Perguntas do profissional não são fatos sobre o paciente, mas dão contexto às respostas curtas ("Você fuma?" / "Não." → tabagismo "nunca").
6. NÃO retorne os campos listados em CAMPOS JÁ CONFIRMADOS: o profissional já os confirmou.
7. Para cada campo devolva: "campo" (id exato), "valor" (no formato do tipo), "confianca" (0 a 1, honesta) e "trecho" (citação literal curta da transcrição que sustenta o valor).
8. Tipos: texto → string; numero/escala → número (escala é inteiro 0–10); selecao → uma das opções; multisselecao/lista → array de strings; bool → true/false; mapa corporal → array de ids de região; pontos → array de códigos (VB20, E36, IG4...)."""


def _fmt_ts(ts: float) -> str:
    return f"{int(ts) // 60:02d}:{int(ts) % 60:02d}"


def build_user_prompt(utterances: list[dict], mode: str, confirmed: dict, previous: dict | None) -> str:
    lines = []
    for f in fields_for_mode(mode):
        extra = ""
        if f["type"] in ("select", "multiselect"):
            extra = " | opções: " + ", ".join(f["options"])
        elif f["type"] == "bodymap":
            extra = " | ids: " + ", ".join(REGIONS)
        elif f["type"] == "scale":
            extra = " | inteiro 0-10"
        hint = f" | {f['hint']}" if f.get("hint") else ""
        lines.append(f"- {f['id']} | {f['label']} | tipo: {f['type']}{extra}{hint}")
    tr = "\n".join(f"[{_fmt_ts(u.get('ts', 0))}] {'PROFISSIONAL' if u['speaker'] == 'profissional' else 'PACIENTE'}: {u['text']}"
                   for u in utterances if u.get("text"))
    conf = ", ".join(sorted(confirmed)) if confirmed else "(nenhum)"
    prev = ""
    if previous:
        prev = f"\nSESSÃO ANTERIOR (contexto, não copie): EVA {previous.get('eva')}, resumo: {previous.get('summary', '')}\n"
    kind = "primeira consulta (anamnese + conduta)" if mode == "anamnese" else "sessão de evolução (SOAP)"
    return (f"TIPO DE ATENDIMENTO: {kind}\n\nCAMPOS DISPONÍVEIS\n" + "\n".join(lines) +
            f"\n\nCAMPOS JÁ CONFIRMADOS (não retornar): {conf}\n{prev}\nTRANSCRIÇÃO\n{tr}\n")


# ---------------------------------------------------------------------------
# Chamada
# ---------------------------------------------------------------------------
def _parse(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        data = json.loads(m.group(0)) if m else {}
    return data.get("campos", []) if isinstance(data, dict) else []


def cache_key(utterances: list[dict], mode: str, confirmed: dict) -> str:
    st = settings()
    raw = json.dumps([st["model"], st["effort"], mode, [(u["speaker"], u["text"]) for u in utterances], sorted(confirmed)], ensure_ascii=False)
    return hashlib.sha1(raw.encode()).hexdigest()


def extract(utterances: list[dict], mode: str, confirmed: dict | None = None, previous: dict | None = None, use_cache: bool = True) -> dict:
    """Chama o LLM e devolve {fields, prompt, raw, usage, cost_usd, latency_ms, model, error}."""
    confirmed = confirmed or {}
    st = settings()
    key = cache_key(utterances, mode, confirmed)
    if use_cache:
        with _cache_lock:
            if key in _cache:
                hit = dict(_cache[key])
                hit["cached"] = True
                return hit
    schema = build_schema(mode)
    system, user = SYSTEM_PROMPT, build_user_prompt(utterances, mode, confirmed, previous)
    result: dict[str, Any] = {"fields": {}, "model": st["model"], "prompt": {"system": system, "user": user, "schema": schema},
                              "raw": None, "usage": None, "cost_usd": 0.0, "latency_ms": 0.0, "error": None, "cached": False,
                              "fallback": None, "stop_reason": None}
    if not st["api_key_set"]:
        result["error"] = "ANTHROPIC_API_KEY não configurada"
        return result
    kwargs: dict[str, Any] = dict(model=st["model"], max_tokens=16000, system=system,
                                  messages=[{"role": "user", "content": user}],
                                  output_config={"format": {"type": "json_schema", "schema": schema}})
    if _EFFORT_MODELS.match(st["model"]) and st["effort"] in ("low", "medium", "high"):
        kwargs["output_config"]["effort"] = st["effort"]
    t0 = time.perf_counter()
    try:
        client = get_client()
        resp = None
        if st["use_fallbacks"] and _FALLBACK_MODELS.match(st["model"]):
            try:
                resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
                result["fallback"] = "server-side-fallback-2026-07-01 (default)"
            except Exception as e:  # noqa: BLE001 — se o recurso beta não for aceito, repete sem ele
                if type(e).__name__ not in ("BadRequestError", "TypeError", "NotFoundError"):
                    raise
                resp = None
        if resp is None:
            resp = client.messages.create(**kwargs)
            result["fallback"] = result["fallback"] or "desativado/indisponível"
        result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        result["stop_reason"] = getattr(resp, "stop_reason", None)
        u = resp.usage
        usage = {"input_tokens": getattr(u, "input_tokens", 0) or 0, "output_tokens": getattr(u, "output_tokens", 0) or 0,
                 "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
                 "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0}
        result["usage"] = usage
        result["cost_usd"] = estimate_cost(usage["input_tokens"] + usage["cache_creation_input_tokens"], usage["output_tokens"])
        if result["stop_reason"] == "refusal":
            sd = getattr(resp, "stop_details", None)
            result["error"] = f"Requisição recusada pelo modelo ({getattr(sd, 'category', None) or 'sem categoria'})"
            return result
        text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
        result["raw"] = text
        for item in _parse(text):
            fid = item.get("campo")
            if fid not in FIELD_BY_ID or fid in confirmed or fid not in field_ids_for_mode(mode):
                continue
            val = normalize_value(fid, item.get("valor"))
            if is_empty(val) and val is not False:
                continue
            conf = item.get("confianca", 0.7)
            try:
                conf = max(0.0, min(1.0, float(conf)))
            except (TypeError, ValueError):
                conf = 0.7
            result["fields"][fid] = {"value": val, "confidence": round(conf, 3), "evidence": str(item.get("trecho", ""))[:300],
                                     "source": "llm"}
    except Exception as e:  # noqa: BLE001 — qualquer falha de rede/API vira aviso; o pipeline clássico continua
        result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        result["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        return result
    with _cache_lock:
        _cache[key] = result
        if len(_cache) > 64:
            _cache.pop(next(iter(_cache)))
    return result
