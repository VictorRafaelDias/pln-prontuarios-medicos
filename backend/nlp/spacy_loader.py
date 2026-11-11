"""Carrega o modelo spaCy (pt_core_news_md) e acrescenta dois componentes próprios:

* ``sentence_boundaries`` — força as fronteiras de sentença decididas na etapa 3 (antes do parser);
* ``clinical_ruler`` — EntityRuler alimentado pelos dicionários JSON (antes do ``ner`` estatístico).
"""
from __future__ import annotations

import threading
from typing import Any

import spacy
from spacy.language import Language

from . import resources

MODEL_NAME = "pt_core_news_md"
_lock = threading.RLock()
_nlp: Language | None = None
_index: dict[str, dict] = {}
_ruler_version = -1
PIPELINE_LOCK = threading.RLock()  # serializa o uso do objeto nlp entre threads


@Language.component("sentence_boundaries")
def sentence_boundaries(doc):
    starts = doc.user_data.get("sent_starts")
    if starts is not None:
        starts = set(starts)
        for tok in doc:
            if tok.idx in starts:
                tok.is_sent_start = True
            elif tok.i > 0:
                tok.is_sent_start = False
    return doc


def _build_ruler(nlp: Language) -> None:
    global _index, _ruler_version
    patterns, index = resources.build_ruler_patterns()
    if "clinical_ruler" in nlp.pipe_names:
        nlp.remove_pipe("clinical_ruler")
    ruler = nlp.add_pipe(
        "entity_ruler", name="clinical_ruler", before="ner" if "ner" in nlp.pipe_names else None,
        config={"phrase_matcher_attr": "LOWER", "overwrite_ents": True, "validate": False},
    )
    ruler.add_patterns(patterns)
    _index = index
    _ruler_version = resources.resources_version()


def get_nlp() -> Language:
    global _nlp
    with _lock:
        if _nlp is None:
            try:
                nlp = spacy.load(MODEL_NAME)
            except OSError as e:  # modelo ausente
                raise RuntimeError(
                    f"Modelo spaCy '{MODEL_NAME}' não encontrado. Rode: python setup.py "
                    f"(ou: python -m spacy download {MODEL_NAME})"
                ) from e
            if "sentence_boundaries" not in nlp.pipe_names:
                nlp.add_pipe("sentence_boundaries", before="parser" if "parser" in nlp.pipe_names else None)
            _build_ruler(nlp)
            _nlp = nlp
        elif _ruler_version != resources.resources_version():
            _build_ruler(_nlp)
        return _nlp


def ruler_index() -> dict[str, dict]:
    get_nlp()
    return _index


def reload_ruler() -> int:
    """Reconstrói o EntityRuler após edição dos dicionários. Retorna o nº de padrões."""
    with _lock:
        nlp = get_nlp()
        _build_ruler(nlp)
        return len(nlp.get_pipe("clinical_ruler").patterns)


def pipe_groups(nlp: Language) -> dict[str, list[str]]:
    """Agrupa os componentes do modelo por etapa do pipeline de PLN (na ordem original do modelo)."""
    names = list(nlp.pipe_names)
    lemma_group = [n for n in names if n in ("tok2vec", "morphologizer", "tagger", "attribute_ruler", "lemmatizer")]
    return {
        "lemma": lemma_group,
        "dep": [n for n in ("sentence_boundaries", "parser") if n in names],
        "ner": [n for n in ("clinical_ruler", "ner") if n in names],
    }


def run_components(nlp: Language, doc, names: list[str]):
    for n in names:
        doc = nlp.get_pipe(n)(doc)
    return doc


def model_info() -> dict[str, Any]:
    nlp = get_nlp()
    return {"model": MODEL_NAME, "version": nlp.meta.get("version"), "pipeline": list(nlp.pipe_names),
            "ruler_patterns": len(nlp.get_pipe("clinical_ruler").patterns)}
