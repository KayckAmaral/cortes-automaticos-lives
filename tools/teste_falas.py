"""Transcreve os últimos N minutos do buffer e mostra quem fala em cada trecho (streamer x jogo).

Uso: python tools/teste_falas.py <canal> [minutos]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from app.gravador import listar_segmentos
from app.transcricao import transcrever
from app.util import FFMPEG, RAIZ, carregar_config, rodar

canal = sys.argv[1]
minutos = float(sys.argv[2]) if len(sys.argv) > 2 else 3
cfg = carregar_config()
segs = listar_segmentos(RAIZ / "buffer" / canal)
escolhidos = [p for _, p in segs[-(int(minutos * 6) + 1):-1]]
lista = RAIZ / "tmp" / "falas_lista.txt"
lista.write_text("\n".join(f"file '{p.as_posix()}'" for p in escolhidos), encoding="utf-8")
r = rodar([FFMPEG, "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lista), "-vn", "-ac", "1",
           "-ar", "16000", "-f", "s16le", "-"], timeout=300)
audio = np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768.0
t = time.time()
palavras = transcrever(audio, {**cfg["legenda"], "falas_jogo": "silencio"})
print(f"{len(audio) / 16000:.0f}s de áudio transcritos em {time.time() - t:.1f}s\n")
atual, buf, ini = None, [], 0
for w in palavras + [{"quem": None, "palavra": "", "ini": 0}]:
    if w["quem"] != atual:
        if buf:
            print(f"{'🎮 JOGO    ' if atual == 'jogo' else '🎙 STREAMER'} {ini:6.1f}s  {' '.join(buf)[:110]}")
        atual, buf, ini = w["quem"], [], w["ini"]
    buf.append(w["palavra"])
