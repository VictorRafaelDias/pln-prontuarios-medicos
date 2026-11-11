"""Etapas do pipeline de PLN, na ordem de execução."""
from __future__ import annotations

from .base import PipelineState, Stage
from .s01_asr import ASRStage
from .s02_normalize import NormalizeStage
from .s03_sentences import SentenceStage
from .s04_tokens import TokenStage
from .s05_stopwords import StopwordStage
from .s06_lemma_stem import LemmaStemStage
from .s07_pos_dep import PosDepStage
from .s08_ner import NerStage


def all_stages() -> list[Stage]:
    stages: list[Stage] = [ASRStage(), NormalizeStage(), SentenceStage(), TokenStage(), StopwordStage(), LemmaStemStage(),
                           PosDepStage(), NerStage()]
    try:
        from .s09_negation import NegationStage
        from .s10_mapping import MappingStage
        from .s11_llm import LLMStage
        from .s12_merge import MergeStage
        stages += [NegationStage(), MappingStage(), LLMStage(), MergeStage()]
    except ImportError:  # etapas ainda não disponíveis (desenvolvimento incremental)
        pass
    return stages


__all__ = ["PipelineState", "Stage", "all_stages"]
