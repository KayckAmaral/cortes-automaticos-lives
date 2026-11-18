"""Testa se legenda e crédito ficam no tempo certo no vídeo final.

Coloca uma palavra 'MARCA' exatamente de 10,0 s a 11,0 s do corte + crédito no vídeo todo,
renderiza (início perto e longe do começo do arquivo) e confere quadros em 9,5 s / 10,5 s / fim,
além do alinhamento do áudio com o que o Whisper ouviria.
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.cortador import juntar_trecho  # noqa: E402
from app.editor import renderizar  # noqa: E402
from app.legenda_ass import gerar_ass  # noqa: E402
from app.transcricao import extrair_audio  # noqa: E402
from app.util import FFMPEG, RAIZ, carregar_canais, carregar_config  # noqa: E402

cfg = carregar_config()
canal = next(c for c in carregar_canais(cfg) if c["nome"] == sys.argv[1])
trab = RAIZ / "tmp" / "teste_sinc"
shutil.rmtree(trab, ignore_errors=True)
agora = time.time()
bruto, _, _ = juntar_trecho(RAIZ / "buffer" / canal["nome"], agora - 150, agora - 40, trab, max_espera=1)
DUR = 30.0


def quadro(video, t, nome):
    out = trab / f"{nome}.png"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(video), "-ss", f"{t:.2f}", "-frames:v", "1",
                    "-vf", "crop=1080:700:0:520,scale=300:-2", str(out)])
    return out


def pcm(arquivo):
    r = subprocess.run([FFMPEG, "-v", "error", "-i", str(arquivo), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                       capture_output=True)
    return np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768.0


def lag(a, b):
    env = lambda v: np.sqrt(np.convolve(v ** 2, np.ones(160) / 160, mode="same"))[::160]
    ea, eb = env(a), env(b)
    seg = ea[500:1300]
    melhor = max(range(-400, 401), key=lambda d: np.corrcoef(seg, eb[500 + d:1300 + d])[0, 1]
                 if 500 + d >= 0 and 1300 + d <= len(eb) else -2)
    return melhor / 100


imagens = []
for nome, inicio in (("perto", 6.0), ("longe", 60.0)):
    pal = [{"palavra": "MARCA", "ini": 10.0, "fim": 11.0, "quem": "streamer"}]
    gerar_ass(pal, trab / "legenda.ass", {**cfg["legenda"], "palavras_por_vez": 1}, credito="kick.com/teste", duracao=DUR)
    saida = trab / f"saida_{nome}.mp4"
    t = time.time()
    renderizar(bruto, inicio, DUR, canal, cfg["saida"], trab, saida, com_legenda=True)
    r = subprocess.run([str(Path(FFMPEG).with_name("ffprobe.exe")), "-v", "error", "-show_entries",
                        "stream=codec_type,start_time,duration", "-of", "csv=p=0", str(saida)], capture_output=True, text=True)
    print(f"[{nome}] início={inicio}s render {time.time() - t:.1f}s | streams: {r.stdout.split()}")
    print(f"[{nome}] áudio do vídeo vs áudio do Whisper: {lag(extrair_audio(bruto, inicio, DUR), pcm(saida)):+.2f}s (esperado 0)")
    imagens += [quadro(saida, 9.5, f"{nome}_9.5"), quadro(saida, 10.5, f"{nome}_10.5"), quadro(saida, DUR - 0.5, f"{nome}_fim")]

# mosaico: linha 1 = perto (9,5 / 10,5 / fim), linha 2 = longe
entradas = sum([["-i", str(p)] for p in imagens], [])
subprocess.run([FFMPEG, "-v", "error", "-y", *entradas, "-filter_complex",
                "[0][1][2]hstack=3[l1];[3][4][5]hstack=3[l2];[l1][l2]vstack", str(RAIZ / "tmp" / "teste_sinc.png")])
print("mosaico: tmp/teste_sinc.png (colunas: 9,5 s | 10,5 s | fim; linhas: perto | longe)")
