"""Orquestrador do pipeline de PLN: executa as 12 etapas em ordem, registrando entrada, saída e tempo (ms)."""
from __future__ import annotations

import time
from typing import Any

from . import spacy_loader
from .stages import PipelineState, all_stages


def _jsonable(o: Any) -> Any:
    """Garante que a saída seja serializável (tuplas → listas, sets → listas)."""
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_jsonable(v) for v in o]
    return o


def run_pipeline(utterances: list[dict], mode: str = "anamnese", *, use_llm: bool = False, llm_fields: dict | None = None,
                 confirmed: dict | None = None, previous_session: dict | None = None, include_stages: bool = True,
                 count_llm_tokens: bool = False, stop_after: str | None = None, force_llm: bool = False) -> dict:
    """Executa o pipeline completo.

    utterances: [{"speaker": "paciente"|"profissional", "text": str, "ts": float}]
    use_llm: chama o LLM (se houver chave); llm_fields: extração LLM já feita (reaproveitada sem nova chamada).
    confirmed: {field_id: valor} — campos confirmados pelo profissional nunca são sobrescritos.
    """
    state = PipelineState(utterances=utterances, mode=mode, options={
        "use_llm": use_llm, "llm_fields": llm_fields, "confirmed": confirmed or {}, "previous_session": previous_session,
        "count_llm_tokens": count_llm_tokens, "force_llm": force_llm,
    })
    stages_out: list[dict] = []
    prev_output: Any = {"utterances": utterances}
    t_total = time.perf_counter()
    with spacy_loader.PIPELINE_LOCK:
        spacy_loader.get_nlp()  # garante o modelo carregado antes de cronometrar
        for st in all_stages():
            t0 = time.perf_counter()
            out = st.run(state)
            ms = (time.perf_counter() - t0) * 1000.0
            state.outputs[st.id] = out
            if include_stages:
                rec = st.meta()
                rec.update({"input": _jsonable(prev_output), "output": _jsonable(out), "ms": round(ms, 2)})
                stages_out.append(rec)
            else:
                stages_out.append({"id": st.id, "ms": round(ms, 2)})
            prev_output = out
            if stop_after and st.id == stop_after:
                break
    total_ms = (time.perf_counter() - t_total) * 1000.0
    result = {
        "mode": mode,
        "text": state.text,
        "utterances": state.norm,
        "sentences": state.sentences,
        "entities": state.entities,
        "fields": state.merged,
        "rule_fields": state.rule_fields,
        "llm": {k: v for k, v in state.llm.items() if k != "fields"} if state.llm else {},
        "llm_fields": state.llm.get("fields") if state.llm else None,
        "timing": {"total_ms": round(total_ms, 2), "stages": {s["id"]: s["ms"] for s in stages_out}},
        "stages": stages_out if include_stages else [{"id": s["id"], "ms": s["ms"]} for s in stages_out],
    }
    return _jsonable(result)
