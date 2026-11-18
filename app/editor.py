"""Monta o vídeo vertical 1080x1920 (webcam em cima + gameplay embaixo, ou só gameplay) com legenda."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .util import CREATE_NO_WINDOW, FFMPEG, FFPROBE, probe_video, rodar

log = logging.getLogger("editor")

W, H = 1080, 1920
CAM_H = 608            # 1080x608 ≈ 16:9
GAME_H = H - CAM_H     # 1312

_encoder_cache: str | None = None


def escolher_encoder(pref: str = "auto") -> str:
    global _encoder_cache
    if pref in ("qsv", "x264"):
        return pref
    if _encoder_cache:
        return _encoder_cache
    teste = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=30",
         "-t", "0.5", "-vf", "format=nv12", "-c:v", "h264_qsv", "-f", "null", "-"],
        capture_output=True, creationflags=CREATE_NO_WINDOW)
    _encoder_cache = "qsv" if teste.returncode == 0 else "x264"
    log.info("encoder escolhido: %s", _encoder_cache)
    return _encoder_cache


def _par(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def filtro_layout(canal: dict, src_w: int, src_h: int, cfg_saida: dict, com_legenda: bool,
                  corte_ini: float = 0.0, corte_dur: float | None = None) -> str:
    fps = cfg_saida.get("fps", 30)
    cam = canal.get("camera")
    layout = canal.get("layout", "so_gameplay")
    # 1º corta o trecho exato e ZERA o relógio (setpts) — a legenda (ass) e o crédito usam esse relógio.
    # (Cortar com '-ss' depois do '-i' deixava o relógio dos filtros adiantado: legenda dessincronizada
    #  em até 15 s e o crédito sumindo antes do fim — 17/11.) Depois reduz para 30 fps.
    trim = f"trim=start={corte_ini:.3f}" + (f":duration={corte_dur:.3f}" if corte_dur else "") + ",setpts=PTS-STARTPTS,"
    entrada = f"[0:v]{trim}fps={fps},split=2[a][b];"
    fim = "setsar=1" + (",ass=legenda.ass" if com_legenda else "")

    if layout == "camera_gameplay" and cam:
        cx, cy = _par(cam["x"] * src_w), _par(cam["y"] * src_h)
        cw, ch = _par(cam["w"] * src_w), _par(cam["h"] * src_h)
        cw, ch = min(cw, src_w - cx), min(ch, src_h - cy)
        gw = min(src_w, _par(src_h * W / GAME_H))
        gx = _par((src_w - gw) * float(canal.get("gameplay_offset_x", 0.5)))
        return (
            entrada +
            f"[a]crop={cw}:{ch}:{cx}:{cy},scale={W}:{CAM_H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{CAM_H},setsar=1[cam];"
            f"[b]crop={gw}:{src_h}:{gx}:0,scale={W}:{GAME_H},setsar=1[game];"
            f"[cam][game]vstack=inputs=2,{fim}[out]"
        )

    # só gameplay: fundo desfocado + gameplay com zoom no centro
    zoom = float(cfg_saida.get("zoom_so_gameplay", 1.35))
    gw = _par(src_w / zoom)
    gx = _par((src_w - gw) * float(canal.get("gameplay_offset_x", 0.5)))
    # desfoque feito em 1/4 da resolução (muito mais barato) e ampliado depois
    return (
        entrada +
        f"[a]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=6:2,"
        f"eq=brightness=-0.15,scale={W}:{H}[fundo];"
        f"[b]crop={gw}:{src_h}:{gx}:0,scale={W}:-2,setsar=1[game];"
        f"[fundo][game]overlay=0:(H-h)/2,{fim}[out]"
    )


def renderizar(bruto: Path, inicio: float, duracao: float, canal: dict, cfg_saida: dict,
               pasta_trabalho: Path, saida: Path, com_legenda: bool) -> Path:
    """Roda o ffmpeg com cwd = pasta_trabalho (o filtro ass= não aceita C:\\ no Windows).

    Corte exato: pula RÁPIDO (-ss antes do -i) até 15 s antes do ponto e o resto é cortado
    DENTRO dos filtros (trim/atrim + setpts), para que vídeo, áudio, legenda e crédito usem
    todos o mesmo relógio começando em 0 no início do corte.
    """
    src_w, src_h = probe_video(bruto)
    pre = max(0.0, inicio - 15.0)
    resto = inicio - pre
    grafo = filtro_layout(canal, src_w, src_h, cfg_saida, com_legenda, corte_ini=resto, corte_dur=duracao)
    tem_audio = tem_stream_audio(bruto)
    if tem_audio:
        grafo += f";[0:a]atrim=start={resto:.3f}:duration={duracao:.3f},asetpts=PTS-STARTPTS[aout]"
    enc = escolher_encoder(cfg_saida.get("encoder", "auto"))
    br = cfg_saida.get("bitrate", "4500k")
    if enc == "qsv":
        grafo = grafo.replace("[out]", ",format=nv12[out]")
        vcod = ["-c:v", "h264_qsv", "-preset", "veryfast", "-b:v", br, "-maxrate", br, "-bufsize", "9M"]
    else:
        grafo = grafo.replace("[out]", ",format=yuv420p[out]")
        vcod = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", br, "-bufsize", "9M"]
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
           *(["-ss", f"{pre:.3f}"] if pre > 0 else []), "-i", str(bruto),
           "-filter_complex", grafo, "-map", "[out]", *(["-map", "[aout]"] if tem_audio else []),
           "-t", f"{duracao:.3f}",
           *vcod, "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
           "-movflags", "+faststart", str(saida)]
    try:
        rodar(cmd, cwd=pasta_trabalho, timeout=600)
    except RuntimeError:
        if enc != "qsv":
            raise
        log.warning("QSV falhou, tentando libx264")
        global _encoder_cache
        _encoder_cache = "x264"
        return renderizar(bruto, inicio, duracao, canal, {**cfg_saida, "encoder": "x264"},
                          pasta_trabalho, saida, com_legenda)
    return saida


def tem_stream_audio(arquivo: Path) -> bool:
    try:
        r = rodar([FFPROBE, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index",
                   "-of", "csv=p=0", str(arquivo)], timeout=30)
        return bool(r.stdout.strip())
    except RuntimeError:
        return False


def capturar_frame(video: Path, destino: Path, em: float = 1.0) -> Path:
    rodar([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{em:.2f}", "-i", str(video),
           "-frames:v", "1", str(destino)], timeout=60)
    return destino
