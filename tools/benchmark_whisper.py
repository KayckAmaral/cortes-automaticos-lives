"""Mede quanto tempo o faster-whisper leva para transcrever um áudio nesta máquina.

Uso: python tools/benchmark_whisper.py <arquivo.wav> [modelos...]
"""
import subprocess
import sys
import time

import numpy as np
from faster_whisper import WhisperModel


def carregar_audio(caminho: str) -> np.ndarray:
    """Decodifica qualquer áudio/vídeo via ffmpeg para float32 mono 16 kHz (evita bug do PyAV)."""
    raw = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", caminho, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


audio = carregar_audio(sys.argv[1])
modelos = sys.argv[2:] or ["base", "small"]

for nome in modelos:
    t0 = time.perf_counter()
    model = WhisperModel(nome, device="cpu", compute_type="int8", cpu_threads=4)
    t_load = time.perf_counter() - t0

    t1 = time.perf_counter()
    segments, info = model.transcribe(
        audio,
        language="pt",
        beam_size=1,
        word_timestamps=True,
        vad_filter=True,
    )
    palavras = [w for s in segments for w in (s.words or [])]
    t_trans = time.perf_counter() - t1

    texto = " ".join(w.word.strip() for w in palavras)
    print(f"\n=== {nome} ===")
    print(f"carregar: {t_load:.1f}s | transcrever {info.duration:.1f}s de audio: {t_trans:.1f}s | palavras: {len(palavras)}")
    print(f"texto: {texto[:300]}")
