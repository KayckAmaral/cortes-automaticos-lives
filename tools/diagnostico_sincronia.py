"""Mede a defasagem entre o áudio que vai para o Whisper (legenda) e o áudio do vídeo final.

Uso: python tools/diagnostico_sincronia.py <canal>/<base>
Se a defasagem não for ~0, legenda e fala ficam fora de sincronia.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.transcricao import extrair_audio  # noqa: E402
from app.util import FFMPEG, FFPROBE, RAIZ  # noqa: E402

cid = sys.argv[1]
canal, base = cid.split("/")
meta = json.loads((RAIZ / "cortes" / canal / f"{base}.json").read_text(encoding="utf-8"))
fonte = RAIZ / meta["fonte"]["arquivo"]
s = meta["inicio"] - meta["fonte"]["inicio"]
dur = meta["duracao"]
final = RAIZ / "cortes" / canal / f"{base}.mp4"


def probe(f):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,start_time,duration:format=duration",
                        "-of", "csv=p=0", str(f)], capture_output=True, text=True)
    return r.stdout.split()


print(f"trecho dentro da sobra: s={s:.2f}s dur={dur:.2f}s")
print("sobra (fonte):", probe(fonte))
print("vídeo final  :", probe(final))

a = extrair_audio(fonte, s, dur)                         # o que o Whisper ouviu
r = subprocess.run([FFMPEG, "-v", "error", "-i", str(final), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                   capture_output=True)
b = np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768.0   # o que o vídeo final toca
print(f"duração do áudio: Whisper {len(a) / 16000:.2f}s | vídeo final {len(b) / 16000:.2f}s")


def defasagem(x, y, ini, janela=8.0, busca=6.0, sr=16000):
    """Quantos segundos y está atrasado em relação a x, medido a partir de 'ini' (correlação de envelopes)."""
    passo = 160  # 10 ms
    env = lambda v: np.sqrt(np.convolve(v ** 2, np.ones(passo) / passo, mode="same"))[::passo]
    ex, ey = env(x), env(y)
    i0, n, m = int(ini * 100), int(janela * 100), int(busca * 100)
    seg = ex[i0:i0 + n]
    melhor, lag = -1, 0
    for d in range(-m, m + 1):
        j = i0 + d
        if j < 0 or j + n > len(ey):
            continue
        c = np.corrcoef(seg, ey[j:j + n])[0, 1]
        if c > melhor:
            melhor, lag = c, d
    return lag / 100, melhor


for ini in (2, 20, 40, max(2, dur - 12)):
    lag, corr = defasagem(a, b, ini)
    print(f"  em {ini:5.1f}s: vídeo final está {lag:+.2f}s em relação à legenda (correlação {corr:.2f})")
