"""Detecção automática da posição da webcam do streamer.

Ideia (vários frames do mesmo trecho, espaçados alguns segundos):
1. ROSTO: o detector YuNet (OpenCV) acha rostos em cada frame. O rosto do streamer fica parado no
   mesmo lugar em quase todos os frames; rostos do jogo (cutscenes, NPCs) mudam de lugar. O grupo de
   rostos que aparece em mais frames é o do streamer.
2. BORDA: a moldura da webcam é uma linha reta que fica PARADA em todos os frames (a gameplay mexe).
   Também conta o contraste de movimento: dentro da webcam o quarto é parado; fora, a gameplay muda.
3. Testa retângulos formados por essas linhas (ou pela borda da tela) em volta do rosto e escolhe o
   de maior pontuação.

Devolve as proporções (0–1) no mesmo formato da calibração manual: {"x", "y", "w", "h"}.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import cv2
import numpy as np

from .util import FFMPEG, RAIZ, probe_video, rodar

log = logging.getLogger("webcam")

MODELO_ROSTO = RAIZ / "modelos" / "rosto" / "face_detection_yunet_2023mar.onnx"
LARG_MAX = 1280          # frames maiores são reduzidos para isso (1080p → 720p)
LARG_ANALISE = 640       # resolução das análises de borda/movimento
CONFIANCA_MINIMA = 0.62  # abaixo disso não confia na detecção

_lock_rosto = threading.Lock()
_detector_rosto = None


# ---------------------------------------------------------------------- frames
def frames_de_video(video: Path | str, inicio: float, dur: float, n: int = 8) -> list[np.ndarray]:
    """n frames espalhados em [inicio, inicio+dur] do vídeo (BGR, no máximo LARG_MAX de largura)."""
    w, h = probe_video(video)
    if w > LARG_MAX:
        w, h = LARG_MAX, int(round(h * LARG_MAX / w / 2)) * 2
    frames = []
    for i in range(n):
        t = inicio + dur * (i + 0.5) / n
        try:
            r = rodar([FFMPEG, "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", str(video), "-frames:v", "1",
                       "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], timeout=30)
        except RuntimeError:
            continue
        if len(r.stdout) == w * h * 3:
            frames.append(np.frombuffer(r.stdout, np.uint8).reshape(h, w, 3))
    return frames


def frames_de_segmentos(segmentos: list[Path], n: int = 10) -> list[np.ndarray]:
    """Um frame de cada segmento, escolhendo n segmentos espalhados (ex.: os últimos minutos do buffer)."""
    if not segmentos:
        return []
    idx = np.unique(np.linspace(0, len(segmentos) - 1, min(n, len(segmentos))).round().astype(int))
    frames = []
    for i in idx:
        frames += frames_de_video(segmentos[i], 0.0, 2.0, n=1)
    return frames


# ---------------------------------------------------------------------- rostos
def _rostos(frame: np.ndarray) -> list[tuple[float, float, float, float, float]]:
    """Rostos do frame como (x, y, w, h, score) em proporção da tela."""
    global _detector_rosto
    h, w = frame.shape[:2]
    with _lock_rosto:
        if _detector_rosto is None:
            _detector_rosto = cv2.FaceDetectorYN.create(str(MODELO_ROSTO), "", (w, h), 0.6, 0.3, 50)
        _detector_rosto.setInputSize((w, h))
        _, achados = _detector_rosto.detect(frame)
    if achados is None:
        return []
    return [(float(a[0]) / w, float(a[1]) / h, float(a[2]) / w, float(a[3]) / h, float(a[14])) for a in achados]


def _rosto_do_streamer(frames: list[np.ndarray]):
    """Agrupa os rostos de todos os frames pela posição; o grupo presente em mais frames é o streamer."""
    todos = []
    for i, f in enumerate(frames):
        for r in _rostos(f):
            if 0.01 < r[2] < 0.35:   # rosto do tamanho de webcam (nem minúsculo, nem tela cheia)
                todos.append((i, *r))
    grupos: list[list] = []
    for d in sorted(todos, key=lambda d: -d[5]):
        cx, cy = d[1] + d[3] / 2, d[2] + d[4] / 2
        for g in grupos:
            gx = np.median([e[1] + e[3] / 2 for e in g])
            gy = np.median([e[2] + e[4] / 2 for e in g])
            if abs(cx - gx) < max(0.04, d[3]) and abs(cy - gy) < max(0.06, d[4]):
                g.append(d)
                break
        else:
            grupos.append([d])
    if not grupos:
        return None, 0
    melhor = max(grupos, key=lambda g: (len({e[0] for e in g}), sum(e[5] for e in g)))
    n_frames = len({e[0] for e in melhor})
    arr = np.array([e[1:5] for e in melhor])
    x0, y0 = np.percentile(arr[:, 0], 15), np.percentile(arr[:, 1], 15)
    x1, y1 = np.percentile(arr[:, 0] + arr[:, 2], 85), np.percentile(arr[:, 1] + arr[:, 3], 85)
    return (x0, y0, x1, y1), n_frames


# ---------------------------------------------------------------------- bordas e movimento
def _mapas(frames: list[np.ndarray]):
    """(linhas horizontais paradas, linhas verticais paradas, taxa de mudança) na resolução de análise."""
    h0, w0 = frames[0].shape[:2]
    W = LARG_ANALISE
    H = int(round(h0 * W / w0))
    cinzas = [cv2.cvtColor(cv2.resize(f, (W, H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
              for f in frames]
    ph = np.zeros((H, W), np.float32)
    pv = np.zeros((H, W), np.float32)
    for g in cinzas:
        b = cv2.GaussianBlur(g, (3, 3), 0)
        gx = cv2.Sobel(b, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(b, cv2.CV_32F, 0, 1, ksize=3)
        # borda "forte o bastante" e com direção definida (linha horizontal = gradiente vertical)
        ph += ((np.abs(gy) > 40) & (np.abs(gy) > 1.5 * np.abs(gx))).astype(np.float32)
        pv += ((np.abs(gx) > 40) & (np.abs(gx) > 1.5 * np.abs(gy))).astype(np.float32)
    n = len(cinzas)
    # tolera 1 px de tremida na posição da linha
    ph = cv2.dilate(ph / n, np.ones((3, 1), np.uint8))
    pv = cv2.dilate(pv / n, np.ones((1, 3), np.uint8))
    pilha = np.stack(cinzas).astype(np.int16)
    mediana = np.median(pilha, axis=0)
    mudanca = (np.abs(pilha - mediana) > 14).mean(axis=0).astype(np.float32)
    return ph, pv, mudanca


def _candidatos(perfil: np.ndarray, faixa: range, borda: int, limite: float = 0.45, maximo: int = 14) -> list[int]:
    """Posições (picos locais) do perfil acima do limite dentro da faixa, mais a borda da tela."""
    vals = [(perfil[i], i) for i in faixa
            if perfil[i] >= limite and perfil[i] >= perfil[max(i - 1, 0)] and perfil[i] >= perfil[min(i + 1, len(perfil) - 1)]]
    # as mais próximas do rosto primeiro (a moldura costuma ser a primeira linha forte)
    escolhidos = [i for _, i in sorted(vals, key=lambda v: -v[0])[:maximo]]
    return sorted(set(escolhidos + [borda]))


def detectar(frames: list[np.ndarray]) -> dict | None:
    """Acha a webcam nos frames. Devolve {"camera": {x,y,w,h}, "confianca", "rosto_frames"} ou None."""
    if len(frames) < 3:
        return None
    rosto, n_rosto = _rosto_do_streamer(frames)
    if rosto is None or n_rosto < max(2, int(np.ceil(len(frames) * 0.3))):
        log.debug("webcam: rosto do streamer não encontrado (%s de %d frames)", n_rosto, len(frames))
        return None
    ph, pv, mud = _mapas(frames)
    H, W = ph.shape
    fx0, fy0 = int(rosto[0] * W), int(rosto[1] * H)
    fx1, fy1 = int(np.ceil(rosto[2] * W)), int(np.ceil(rosto[3] * H))
    fx0, fy0, fx1, fy1 = max(fx0, 0), max(fy0, 0), min(fx1, W - 1), min(fy1, H - 1)
    fw = max(fx1 - fx0, 1)

    # perfis de linha parada, medidos na faixa do rosto (a moldura atravessa essa faixa inteira)
    perf_h = ph[:, fx0:fx1 + 1].mean(axis=1)
    perf_v = pv[fy0:fy1 + 1, :].mean(axis=0)
    tops = _candidatos(perf_h, range(1, fy0), 0)
    bots = _candidatos(perf_h, range(fy1 + 1, H - 1), H)
    lefts = _candidatos(perf_v, range(1, fx0), 0)
    rights = _candidatos(perf_v, range(fx1 + 1, W - 1), W)

    # somas acumuladas para medir cobertura de linhas e movimento em O(1)
    acum_h = np.concatenate([np.zeros((H, 1)), np.cumsum(ph, axis=1)], axis=1)
    acum_v = np.concatenate([np.zeros((1, W)), np.cumsum(pv, axis=0)], axis=0)
    integ = cv2.integral(mud)

    def media_mud(x0, y0, x1, y1):
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
        if x1 <= x0 or y1 <= y0:
            return None
        return (integ[y1, x1] - integ[y0, x1] - integ[y1, x0] + integ[y0, x0]) / ((x1 - x0) * (y1 - y0))

    def lado_h(y, x0, x1, fora):   # fora = -1 (acima) ou +1 (abaixo)
        if y <= 0 or y >= H:
            return 1.0, 0.5
        linha = max((acum_h[yy, x1] - acum_h[yy, x0]) / (x1 - x0) for yy in (y - 1, y, min(y + 1, H - 1)))
        m_fora = media_mud(x0, y + 2 if fora > 0 else y - 8, x1, y + 8 if fora > 0 else y - 2)
        m_dentro = media_mud(x0, y - 8 if fora > 0 else y + 2, x1, y - 2 if fora > 0 else y + 8)
        contraste = 0.5 if m_fora is None or m_dentro is None else float(np.clip((m_fora - m_dentro) * 2.5, 0, 1))
        return float(linha), contraste

    def lado_v(x, y0, y1, fora):
        if x <= 0 or x >= W:
            return 1.0, 0.5
        linha = max((acum_v[y1, xx] - acum_v[y0, xx]) / (y1 - y0) for xx in (x - 1, x, min(x + 1, W - 1)))
        m_fora = media_mud(x + 2 if fora > 0 else x - 8, y0, x + 8 if fora > 0 else x - 2, y1)
        m_dentro = media_mud(x - 8 if fora > 0 else x + 2, y0, x - 2 if fora > 0 else x + 8, y1)
        contraste = 0.5 if m_fora is None or m_dentro is None else float(np.clip((m_fora - m_dentro) * 2.5, 0, 1))
        return float(linha), contraste

    melhor = None
    area_tela = W * H
    for t in tops:
        for b in bots:
            h = b - t
            for le in lefts:
                for r in rights:
                    w = r - le
                    if not (0.8 <= w / h <= 2.6):
                        continue
                    if not (0.08 <= fw / w <= 0.6):
                        continue
                    area = w * h / area_tela
                    if not (0.012 <= area <= 0.35):
                        continue
                    lados = [lado_h(t, le, r, -1), lado_h(b, le, r, +1), lado_v(le, t, b, -1), lado_v(r, t, b, +1)]
                    linhas = [l for l, _ in lados]
                    if min(linhas) < 0.35:
                        continue
                    nota = float(np.mean([0.7 * l + 0.3 * c for l, c in lados]))
                    # na dúvida, o maior retângulo (evita cortar a câmera numa prateleira do quarto)
                    nota += 0.03 * min(area / 0.1, 1.0)
                    # quantos lados são linha de verdade (borda da tela é "grátis", vale menos)
                    reais = sum(1 for v in (t, b, le, r) if v not in (0, H, W))
                    if reais == 0:
                        nota -= 0.25
                    if melhor is None or nota > melhor[0]:
                        melhor = (nota, t, b, le, r)
    if melhor is None:
        log.debug("webcam: rosto achado, mas nenhuma moldura em volta dele")
        return None
    nota, t, b, le, r = melhor
    confianca = float(np.clip(nota, 0, 1)) * min(1.0, n_rosto / (0.6 * len(frames)))
    if float(mud.mean()) < 0.01:
        # frames praticamente iguais (live congelada/pausada): toda borda parece "parada", pouco confiável
        confianca *= 0.8
    cam = {"x": round(le / W, 4), "y": round(t / H, 4), "w": round((r - le) / W, 4), "h": round((b - t) / H, 4)}
    return {"camera": cam, "confianca": round(confianca, 3), "rosto_frames": n_rosto, "frames": len(frames)}


def iou(a: dict | None, b: dict | None) -> float:
    """Sobreposição entre dois retângulos {x,y,w,h} (0 = nada em comum, 1 = iguais)."""
    if not a or not b:
        return 0.0
    x0, y0 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x1, y1 = min(a["x"] + a["w"], b["x"] + b["w"]), min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    uniao = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / uniao if uniao > 0 else 0.0
