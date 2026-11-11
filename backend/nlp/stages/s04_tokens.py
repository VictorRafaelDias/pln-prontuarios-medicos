"""Etapa 4 — Tokenização (spaCy) + contagem de tokens do LLM para comparação."""
from __future__ import annotations

import math

from .. import spacy_loader
from .base import PipelineState, Stage


class TokenStage(Stage):
    id = "tokens"
    index = 4
    name = "Tokenização"
    short = "Tokens"
    explain = {
        "what": "Quebra o texto em tokens (palavras, números, pontuação) com índice e posição (caracteres inicial/final) no texto. Mostra também quantos tokens o LLM enxerga no mesmo trecho.",
        "why": "É a unidade básica de todas as etapas seguintes. O tokenizador do spaCy trabalha por PALAVRAS (regras da língua); o LLM usa SUBPALAVRAS (BPE): palavras raras ou compridas, como \"lombalgia\", viram vários pedaços. Comparar os dois mostra por que o custo/limite de um LLM não é medido em palavras.",
        "how": "spaCy Tokenizer (regras + exceções do português, sem modelo estatístico). A contagem do LLM usa o endpoint count_tokens da Anthropic quando há chave; sem chave mostramos apenas uma estimativa heurística, claramente marcada.",
    }

    def run(self, state: PipelineState):
        nlp = spacy_loader.get_nlp()
        doc = nlp.make_doc(state.text)
        doc.user_data["sent_starts"] = list(state.sent_starts)
        state.doc = doc
        toks = []
        for t in doc:
            if t.is_space:
                continue
            toks.append({"i": t.i, "text": t.text, "start": t.idx, "end": t.idx + len(t.text),
                         "is_punct": t.is_punct, "is_digit": t.like_num, "shape": t.shape_})
        state.tokens = toks
        words = [t for t in toks if not t.get("is_punct")]
        info = {"available": False, "tokens": None, "estimated": None, "model": None, "ratio": None, "note": ""}
        if state.options.get("count_llm_tokens") and state.text:
            from .. import llm  # import tardio
            info = llm.count_tokens_info(state.text, len(words))
        else:
            info["note"] = "Não solicitado nesta análise (use o Laboratório PLN para comparar)."
        return {"tokens": toks, "n_tokens": len(toks), "n_words": len(words), "llm_tokens": info,
                "avg_chars_per_token": round(len(state.text) / max(1, len(toks)), 2)}
