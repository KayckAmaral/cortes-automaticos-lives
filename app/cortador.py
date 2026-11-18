"""Junta os segmentos que cobrem [pico - antes, pico + depois] num único arquivo."""
from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from .gravador import listar_segmentos
from .util import FFMPEG, rodar

log = logging.getLogger("cortador")


def juntar_trecho(pasta_buffer: Path, ini: float, fim: float, destino: Path,
                  max_espera: float = 45) -> tuple[Path, float, float]:
    """Espera os segmentos necessários fecharem, junta e devolve (arquivo, offset_inicio, t0).

    offset_inicio = segundos entre o início do arquivo juntado e `ini`.
    t0 = horário (epoch) em que o arquivo juntado começa.
    """
    prazo = time.time() + max_espera
    while True:
        segs = listar_segmentos(pasta_buffer)
        # o segmento que cobre `fim` está fechado quando existe um segmento que começa depois de `fim`
        if segs and segs[-1][0].timestamp() > fim:
            break
        if time.time() > prazo:
            log.warning("segmento final não fechou a tempo; usando o que tem")
            break
        time.sleep(1)

    segs = listar_segmentos(pasta_buffer)
    escolhidos = []
    for i, (t, p) in enumerate(segs):
        t_ini = t.timestamp()
        t_fim = segs[i + 1][0].timestamp() if i + 1 < len(segs) else time.time()
        if t_fim > ini and t_ini < fim:
            escolhidos.append((t_ini, p))
    if not escolhidos:
        raise RuntimeError("nenhum segmento cobre o trecho (buffer vazio ou live offline?)")

    destino.mkdir(parents=True, exist_ok=True)
    # copia antes (a limpeza do buffer pode apagar) e monta a lista do concat
    linhas = []
    for i, (_, p) in enumerate(escolhidos):
        copia = destino / f"parte_{i:02d}.ts"
        shutil.copyfile(p, copia)
        linhas.append(f"file '{copia.name}'")
    (destino / "lista.txt").write_text("\n".join(linhas), encoding="utf-8")
    bruto = destino / "bruto.ts"
    rodar([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
           "-i", "lista.txt", "-c", "copy", bruto.name], cwd=destino, timeout=120)
    for i in range(len(escolhidos)):
        (destino / f"parte_{i:02d}.ts").unlink(missing_ok=True)
    offset = max(0.0, ini - escolhidos[0][0])
    return bruto, offset, escolhidos[0][0]
