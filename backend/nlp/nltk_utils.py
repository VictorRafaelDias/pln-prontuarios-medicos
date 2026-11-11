"""Acesso aos recursos NLTK (stopwords e stemmer RSLP) com pasta local e fallback."""
from __future__ import annotations

import threading
from pathlib import Path

import nltk

NLTK_DIR = Path(__file__).resolve().parent.parent / "nltk_data"
if NLTK_DIR.exists() and str(NLTK_DIR) not in nltk.data.path:
    nltk.data.path.insert(0, str(NLTK_DIR))

_lock = threading.Lock()
_stem = None
_stem_name = ""
_stop: set[str] | None = None
_stop_source = ""


def nltk_stopwords() -> tuple[set[str], str]:
    global _stop, _stop_source
    with _lock:
        if _stop is None:
            try:
                from nltk.corpus import stopwords
                _stop = set(stopwords.words("portuguese"))
                _stop_source = "NLTK (português)"
            except (LookupError, OSError):
                import spacy
                from spacy.lang.pt.stop_words import STOP_WORDS
                _stop = set(STOP_WORDS)
                _stop_source = "spaCy (fallback — rode setup.py para baixar o NLTK)"
        return _stop, _stop_source


def stemmer():
    """Retorna (stem_fn, nome). RSLP; se o recurso faltar, usa Snowball-português."""
    global _stem, _stem_name
    with _lock:
        if _stem is None:
            try:
                from nltk.stem import RSLPStemmer
                s = RSLPStemmer()
                s.stem("teste")  # força o carregamento do recurso
                _stem, _stem_name = s.stem, "RSLP"
            except (LookupError, OSError):
                from nltk.stem.snowball import SnowballStemmer
                _stem, _stem_name = SnowballStemmer("portuguese").stem, "Snowball-pt (fallback)"
        return _stem, _stem_name
