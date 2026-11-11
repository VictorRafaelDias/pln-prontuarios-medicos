"""Etapa 5 — Remoção de stopwords com lista customizada que PRESERVA negação e intensidade."""
from __future__ import annotations

from .. import nltk_utils, resources
from ..form_schema import fold
from .base import PipelineState, Stage

REASONS = {
    "negacao": "Palavra de NEGAÇÃO: removê-la inverte o sentido clínico (\"não fumo\" viraria \"fumo\").",
    "intensidade": "Modula INTENSIDADE/QUANTIDADE (\"muito\", \"pouco\", \"mais\"): muda a gravidade relatada.",
    "tempo": "ÂNCORA TEMPORAL (\"já\", \"desde\", \"há\", \"antes\"): separa hábito atual de ex-hábito.",
    "incerteza": "Marca de INCERTEZA (\"talvez\", \"às vezes\"): reduz a confiança do dado.",
    "contraste": "Delimita o ESCOPO da negação (\"mas\", \"porém\", \"se\").",
}


def build_stopwords() -> tuple[set[str], dict[str, str], str]:
    cfg = resources.get_resources()["stopwords_custom"]
    base, source = nltk_utils.nltk_stopwords()
    preserve: dict[str, str] = {}
    for cat, words in cfg.get("preserve", {}).items():
        for w in words:
            preserve[fold(w)] = cat
    stop = {fold(w) for w in base} | {fold(w) for w in cfg.get("extra", [])}
    return stop, preserve, source


class StopwordStage(Stage):
    id = "stopwords"
    index = 5
    name = "Remoção de stopwords"
    short = "Stopwords"
    explain = {
        "what": "Marca as palavras funcionais sem conteúdo clínico (artigos, preposições...) para ignorá-las nas estatísticas e na similaridade. Usa a lista do NLTK + extras de oralidade, MENOS um conjunto de palavras preservadas.",
        "why": "A lista padrão do NLTK contém \"não\", \"nem\", \"muito\", \"pouco\", \"sem\", \"já\"... Em texto clínico essas palavras são justamente as que decidem o significado: \"não fumo\" ≠ \"fumo\"; \"dor muito forte\" ≠ \"dor forte\". Por isso elas são PRESERVADAS (a lista de preservadas é editável em Dicionários).",
        "how": "Conjunto(NLTK ∪ extras) − preservadas, comparado sem acento e em minúsculas. A saída mostra os tokens removidos, os mantidos e, em destaque, quais palavras o NLTK removeria mas nós salvamos — com a justificativa de cada categoria.",
    }

    def run(self, state: PipelineState):
        stop, preserve, source = build_stopwords()
        flags: list[bool] = []
        removed, kept, saved = [], [], []
        for t in state.tokens:
            f = fold(t["text"])
            is_stop = False
            if t["is_punct"] or t["is_digit"]:
                is_stop = False
            elif f in preserve:
                saved.append({"i": t["i"], "text": t["text"], "category": preserve[f], "reason": REASONS.get(preserve[f], "")})
            elif f in stop:
                is_stop = True
            flags.append(is_stop)
            t["is_stop"] = is_stop
            (removed if is_stop else kept).append({"i": t["i"], "text": t["text"]})
        state.stop_flags = flags
        by_cat: dict[str, int] = {}
        for s in saved:
            by_cat[s["category"]] = by_cat.get(s["category"], 0) + 1
        return {
            "source": source,
            "n_stopwords_total": len(stop),
            "n_preserved_words": len(preserve),
            "removed": removed,
            "kept": [k for k in kept],
            "preserved_hits": saved,
            "preserved_by_category": by_cat,
            "reasons": REASONS,
            "n_removed": len(removed),
            "n_kept": len(kept),
        }
