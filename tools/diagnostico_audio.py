"""Refaz o 'juntar' de um corte e mede onde o áudio/vídeo se desalinham.

Uso: python tools/diagnostico_audio.py <canal>/<base>
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.cortador import juntar_trecho  # noqa: E402
from app.util import FFMPEG, FFPROBE, RAIZ  # noqa: E402

cid = sys.argv[1]
canal, base = cid.split("/")
meta = json.loads((RAIZ / "cortes" / canal / f"{base}.json").read_text(encoding="utf-8"))
ini, dur = meta["inicio"], meta["duracao"]
trab = RAIZ / "tmp" / "diag_audio"
shutil.rmtree(trab, ignore_errors=True)


def info(f):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,start_time,duration",
                        "-of", "csv=p=0", str(f)], capture_output=True, text=True)
    return " | ".join(r.stdout.split())


def silencio(f, ss=None, t=None):
    cmd = [FFMPEG, "-v", "info"] + (["-ss", f"{ss:.3f}"] if ss is not None else []) + ["-i", str(f)]
    cmd += (["-t", f"{t:.3f}"] if t else []) + ["-af", "silencedetect=n=-50dB:d=1.5", "-f", "null", "-"]
    s = subprocess.run(cmd, capture_output=True, text=True, errors="replace").stderr
    return re.findall(r"silence_(start|end): ([\d.]+)", s)[:6]


bruto, offset, t0 = juntar_trecho(RAIZ / "buffer" / canal, ini, ini + dur, trab, max_espera=1)
print("partes usadas:", (trab / "lista.txt").read_text())
print("offset dentro do bruto:", round(offset, 2), "s")
print("bruto.ts  :", info(bruto))
print("silêncios (≥1,5 s) no bruto inteiro:", silencio(bruto))
print("silêncios no trecho do corte (-ss antes do -i):", silencio(bruto, ss=offset, t=dur))
# pacotes de áudio no começo do bruto
r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a:0", "-show_entries", "packet=pts_time",
                    "-of", "csv=p=0", "-read_intervals", "%+3", str(bruto)], capture_output=True, text=True)
pts = [float(x) for x in r.stdout.split() if x.strip()]
print("1ºs pacotes de áudio (pts):", pts[:5], "... total nos 3 s:", len(pts))
r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time,flags",
                    "-of", "csv=p=0", "-read_intervals", "%+3", str(bruto)], capture_output=True, text=True)
print("1ºs pacotes de vídeo (pts,flags):", r.stdout.split()[:5])
