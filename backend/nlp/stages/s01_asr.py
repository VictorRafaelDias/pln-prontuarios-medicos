"""Etapa 1 — Entrada (ASR): texto bruto da transcrição com timestamp e rótulo de falante."""
from __future__ import annotations

from .base import PipelineState, Stage

SPEAKERS = {"profissional": "profissional", "paciente": "paciente", "p": "paciente", "prof": "profissional",
            "acupunturista": "profissional", "terapeuta": "profissional", "doutor": "profissional",
            "doutora": "profissional", "dr": "profissional", "dra": "profissional"}


def canon_speaker(s: str | None) -> str:
    return SPEAKERS.get((s or "").strip().lower().rstrip(":"), "paciente")


class ASRStage(Stage):
    id = "asr"
    index = 1
    name = "Entrada (ASR)"
    short = "ASR"
    explain = {
        "what": "Recebe a transcrição bruta do reconhecimento de voz (Web Speech API) ou texto digitado, cada fala com horário e falante (Profissional/Paciente).",
        "why": "O falante importa: o que o paciente RELATA (sintomas, hábitos) tem peso diferente do que o profissional PERGUNTA ou DITA (língua, pulso, pontos). O timestamp ordena o diálogo e permite voltar ao trecho de origem.",
        "how": "Valida cada fala, padroniza o rótulo do falante e atribui um tempo sintético quando não há timestamp.",
    }

    def run(self, state: PipelineState):
        out = []
        for i, u in enumerate(state.utterances):
            text = str(u.get("text", "") or "")
            if not text.strip():
                continue
            out.append({
                "idx": len(out),
                "speaker": canon_speaker(u.get("speaker")),
                "ts": float(u.get("ts", i * 4.0) or 0.0),
                "text": text,
                "partial": bool(u.get("partial", False)),
            })
        state.asr = out
        chars = sum(len(u["text"]) for u in out)
        return {
            "utterances": out,
            "n_utterances": len(out),
            "chars": chars,
            "duration_s": round(out[-1]["ts"] - out[0]["ts"], 1) if len(out) > 1 else 0.0,
            "by_speaker": {s: sum(1 for u in out if u["speaker"] == s) for s in ("profissional", "paciente")},
        }
