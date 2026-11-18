"""Transcrição com faster-whisper na CPU (modelo carregado uma vez)."""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

import numpy as np

from .util import FFMPEG, args_trecho, rodar

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
log = logging.getLogger("whisper")

_modelo = None
_lock = threading.Lock()


def _carregar(nome: str):
    global _modelo
    with _lock:
        if _modelo is None:
            from faster_whisper import WhisperModel
            log.info("carregando Whisper '%s' (CPU int8)...", nome)
            _modelo = WhisperModel(nome, device="cpu", compute_type="int8", cpu_threads=min(6, os.cpu_count() or 4))
            log.info("Whisper pronto")
    return _modelo


def extrair_audio(video: Path, inicio: float, duracao: float) -> np.ndarray:
    """Decodifica via ffmpeg (evita a incompatibilidade do PyAV)."""
    r = rodar([FFMPEG, "-nostdin", "-v", "error", *args_trecho(video, inicio, duracao),
               "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], timeout=120)
    return np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768.0


def transcrever(audio: np.ndarray, cfg_leg: dict) -> list[dict]:
    """Devolve [{'palavra', 'ini', 'fim', 'quem'}] com tempos relativos ao início do áudio.

    'quem' = 'streamer' ou 'jogo' (pelo idioma do trecho; ver app/idioma.py).
    """
    if audio.size == 0:
        return []
    modelo = _carregar(cfg_leg.get("modelo", "small"))
    segmentos, _ = modelo.transcribe(
        audio,
        language=cfg_leg.get("idioma", "pt"),
        beam_size=1,
        word_timestamps=True,
        vad_filter=True,
        initial_prompt=cfg_leg.get("prompt_inicial") or None,
        condition_on_previous_text=False,
    )
    separar = cfg_leg.get("falas_jogo", "silencio") != "desligado"
    palavras = []
    deteccoes = 0
    # orçamento de tempo para as checagens extras (idioma pelo som + lacunas): numa CPU fraca,
    # música de fundo pode fazer isso explodir (visto: +137 s num corte com Beyoncé tocando)
    prazo_extra = time.monotonic() + float(cfg_leg.get("tempo_max_extra_seg", 10))
    for n_seg, s in enumerate(segmentos):
        quem = "streamer"
        if separar:
            from .idioma import classificar_texto
            quem = classificar_texto(s.text)
            if quem == "incerto":
                # frase curta sem pistas no texto: pergunta ao Whisper o idioma pelo som (máx. 5 por corte)
                quem = "streamer"
                if deteccoes < 3 and 0.4 <= s.end - s.start <= 8 and time.monotonic() < prazo_extra:
                    deteccoes += 1
                    trecho = audio[int(s.start * 16000):int(s.end * 16000)]
                    try:
                        lang, prob, _ = modelo.detect_language(audio=trecho)
                        if lang in ("en", "es") and prob >= 0.6:
                            quem = "jogo"
                    except Exception:  # noqa: BLE001
                        pass
        for w in s.words or []:
            texto = w.word.strip()
            if texto:
                palavras.append({"palavra": texto, "ini": float(w.start), "fim": float(w.end), "quem": quem,
                                 "seg": n_seg})
    if separar:
        palavras = _preencher_lacunas(modelo, audio, palavras, cfg_leg, prazo_extra)
    return palavras


def _preencher_lacunas(modelo, audio: np.ndarray, palavras: list[dict], cfg_leg: dict,
                       prazo: float) -> list[dict]:
    """Com language='pt', o Whisper às vezes PULA falas em inglês. Acha trechos com voz que ficaram
    sem nenhuma palavra e transcreve de novo com detecção automática de idioma."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    sr = 16000
    try:
        regioes = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=400))
    except Exception:  # noqa: BLE001
        return palavras
    cobertos = [(w["ini"], w["fim"]) for w in palavras]
    extras = []
    tentativas = 0
    for r in regioes:
        ini, fim = r["start"] / sr, r["end"] / sr
        if not 0.8 <= fim - ini <= 8:      # trecho longo sem legenda costuma ser música, não fala
            continue
        coberto = sum(max(0.0, min(fim, b) - max(ini, a)) for a, b in cobertos)
        if coberto / (fim - ini) > 0.25:   # já tem legenda nesse trecho
            continue
        if tentativas >= 3 or time.monotonic() > prazo:
            log.info("lacunas: orçamento de tempo/tentativas esgotado")
            break
        tentativas += 1
        trecho = audio[int(max(0, ini - 0.2) * sr):int((fim + 0.2) * sr)]
        try:
            segs, info = modelo.transcribe(trecho, language=None, beam_size=1, word_timestamps=True,
                                           vad_filter=False, condition_on_previous_text=False)
            segs = list(segs)
        except Exception:  # noqa: BLE001
            continue
        if info.language not in ("en", "es") or info.language_probability < 0.5:
            continue
        base = max(0, ini - 0.2)
        for n, s in enumerate(segs):
            for w in s.words or []:
                t = w.word.strip()
                if t and w.probability > 0.3:
                    extras.append({"palavra": t, "ini": base + float(w.start), "fim": base + float(w.end),
                                   "quem": "jogo", "seg": 1000 + tentativas * 100 + n})
    if extras:
        palavras = sorted(palavras + extras, key=lambda w: w["ini"])
    return palavras


def traduzir_falas_jogo(palavras: list[dict]) -> dict[int, dict]:
    """{seg: {'original', 'traducao'}} para cada fala do jogo (frase inteira)."""
    from .traducao import traduzir

    falas: dict[int, list[str]] = {}
    for w in palavras:
        if w.get("quem") == "jogo":
            falas.setdefault(w.get("seg", -1), []).append(w["palavra"])
    if not falas:
        return {}
    segs = list(falas)
    originais = [" ".join(falas[s]) for s in segs]
    traduzidas = traduzir(originais)
    return {s: {"original": o, "traducao": t} for s, o, t in zip(segs, originais, traduzidas)}


def pre_carregar(cfg_leg: dict):
    threading.Thread(target=_carregar, args=(cfg_leg.get("modelo", "small"),), daemon=True).start()
