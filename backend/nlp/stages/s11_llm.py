"""Etapa 11 — Extração por LLM (opcional, via Anthropic SDK no backend)."""
from __future__ import annotations

from .. import llm
from .base import PipelineState, Stage


class LLMStage(Stage):
    id = "llm"
    index = 11
    name = "Extração por LLM"
    short = "LLM"
    explain = {
        "what": "Envia ao Claude a transcrição normalizada e o schema do formulário; recebe um JSON estrito com, para cada campo, valor, confiança e o trecho de origem.",
        "why": "O LLM entende paráfrases, contexto e linguagem livre que dicionários e regex não cobrem (\"não consigo mais subir escada sem sentir o joelho\"). Em troca é mais lento, custa dinheiro e pode alucinar — por isso é combinado com o pipeline clássico na etapa 12.",
        "how": "Saída estruturada (JSON Schema) para garantir JSON válido, sem tool_choice forçado. O prompt manda não inventar dados, omitir o que não foi dito, usar português do Brasil e NÃO devolver campos já confirmados. A chave fica só no backend. Sem chave, a etapa é pulada e o sistema roda 100% clássico.",
    }

    def run(self, state: PipelineState):
        o = state.options
        st = llm.settings()
        base = {"available": llm.available(), "model": st["model"], "effort": st["effort"]}
        provided = o.get("llm_fields")
        if provided is not None and not o.get("force_llm"):
            state.llm = {"fields": provided, "reused": True}
            return {**base, "skipped": False, "reused": True, "n_fields": len(provided),
                    "note": "Reaproveitada a extração LLM anterior (sem nova chamada à API)."}
        if not o.get("use_llm"):
            state.llm = {}
            return {**base, "skipped": True, "reason": "LLM não solicitado nesta execução (modo rápido, só PLN clássico)."}
        if not llm.available():
            state.llm = {}
            return {**base, "skipped": True, "reason": "Sem ANTHROPIC_API_KEY — operando com 'Somente PLN clássico'."}
        utts = [{"speaker": u["speaker"], "text": u["text"], "ts": u["ts"]} for u in state.norm if u["text"]]
        res = llm.extract(utts, state.mode, o.get("confirmed") or {}, o.get("previous_session"))
        state.llm = res
        return {**base, "skipped": False, "error": res["error"], "n_fields": len(res["fields"]), "usage": res["usage"],
                "cost_usd": res["cost_usd"], "latency_ms": res["latency_ms"], "cached": res.get("cached"),
                "fallback": res.get("fallback"), "stop_reason": res.get("stop_reason"),
                "prompt": res["prompt"], "raw_response": res["raw"], "fields": res["fields"]}
