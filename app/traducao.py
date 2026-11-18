"""Tradução offline inglês → português (BR) das falas do jogo.

Modelo: Argos Translate en→pb 1.9 (OpenNMT convertido para CTranslate2, ~78 MB), rodando com a
mesma biblioteca do faster-whisper (ctranslate2) + sentencepiece. Sem PyTorch, sem internet.
Arquivos em modelos/traducao_en_pb/{model/, sentencepiece.model}.
"""
from __future__ import annotations

import logging
import re
import threading

from .util import RAIZ

RE_FRASE = re.compile(r"[^.!?]+[.!?]*")

log = logging.getLogger("traducao")
PASTA = RAIZ / "modelos" / "traducao_en_pb"

_lock = threading.Lock()
_tradutor = None
_sp = None


def disponivel() -> bool:
    return (PASTA / "model" / "model.bin").exists() and (PASTA / "sentencepiece.model").exists()


def _carregar():
    global _tradutor, _sp
    with _lock:
        if _tradutor is None:
            import ctranslate2
            import sentencepiece
            _tradutor = ctranslate2.Translator(str(PASTA / "model"), device="cpu", compute_type="int8",
                                               inter_threads=1, intra_threads=2)
            _sp = sentencepiece.SentencePieceProcessor(model_file=str(PASTA / "sentencepiece.model"))
            log.info("tradutor en→pt-BR carregado")
    return _tradutor, _sp


def traduzir(textos: list[str]) -> list[str]:
    """Traduz uma lista de frases. Em caso de erro devolve o original (nunca derruba o corte)."""
    if not textos or not disponivel():
        return textos
    try:
        tr, sp = _carregar()
        # o modelo às vezes descarta a 2ª frase ("Hands up! Nobody move!") → traduz frase a frase
        frases, dono = [], []
        for i, t in enumerate(textos):
            for f in RE_FRASE.findall(t.strip()) or [t.strip()]:
                if f.strip():
                    frases.append(f.strip())
                    dono.append(i)
        tokens = [sp.encode(f, out_type=str) for f in frases]
        res = tr.translate_batch(tokens, beam_size=2, max_decoding_length=256)
        partes: list[list[str]] = [[] for _ in textos]
        for i, r in zip(dono, res):
            # junta as peças do sentencepiece ("▁" marca início de palavra)
            partes[i].append("".join(r.hypotheses[0]).replace("▁", " ").strip())
        return [" ".join(p).strip() or original for p, original in zip(partes, textos)]
    except Exception as e:  # noqa: BLE001
        log.warning("falha na tradução: %s", e)
        return textos
