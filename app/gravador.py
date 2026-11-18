"""Grava a live em segmentos .ts de ~10 s cujo nome é a hora real de início.

streamlink --stdout <url> <qualidade>  |  ffmpeg -c copy -f segment ... seg_%Y%m%d_%H%M%S.ts
"""
from __future__ import annotations

import logging
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from .util import CREATE_NO_WINDOW, FFMPEG, RAIZ, STREAMLINK

log = logging.getLogger("gravador")

FORMATO = "seg_%Y%m%d_%H%M%S.ts"


def matar_arvore(proc: subprocess.Popen):
    """No Windows o streamlink.exe é só um lançador: o trabalho é feito por um python.exe filho.
    Matar só o lançador deixa o filho órfão (ainda mandando dados). Mata a árvore inteira."""
    if proc.poll() is not None:
        return
    try:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                       timeout=15, creationflags=CREATE_NO_WINDOW)
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.kill()
    except Exception:  # noqa: BLE001
        pass


def hora_do_segmento(p: Path) -> datetime | None:
    try:
        return datetime.strptime(p.name, FORMATO)
    except ValueError:
        return None


def listar_segmentos(pasta: Path) -> list[tuple[datetime, Path]]:
    segs = []
    for p in pasta.glob("seg_*.ts"):
        t = hora_do_segmento(p)
        if t:
            segs.append((t, p))
    segs.sort()
    return segs


class Gravador(threading.Thread):
    def __init__(self, canal: dict, cfg: dict, estado):
        super().__init__(daemon=True, name=f"grav-{canal['nome']}")
        self.canal = canal
        self.cfg = cfg
        self.estado = estado
        self.nome = canal["nome"]
        self.pasta = RAIZ / cfg["geral"]["pasta_buffer"] / self.nome
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.parar = threading.Event()
        self._procs: list[subprocess.Popen] = []

    # ------------------------------------------------------------------
    def _cmd_streamlink(self) -> list[str]:
        cmd = [STREAMLINK, "--stdout", "--loglevel", "warning",
               "--stream-segment-threads", "2", "--hls-live-edge", "3"]
        if self.canal["plataforma"] == "twitch":
            cmd += ["--twitch-disable-ads", "--twitch-low-latency"]
        cmd += [self.canal["url"], self.canal.get("qualidade") or self.cfg["geral"]["qualidade"]]
        return cmd

    def _cmd_ffmpeg(self) -> list[str]:
        seg = str(self.cfg["geral"]["segmento_seg"])
        return [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin",
                "-fflags", "+genpts+discardcorrupt", "-i", "pipe:0",
                "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
                "-f", "segment", "-segment_time", seg, "-reset_timestamps", "1",
                "-strftime", "1", str(self.pasta / FORMATO)]

    def run(self):
        threading.Thread(target=self._limpeza, daemon=True, name=f"limp-{self.nome}").start()
        espera = 20
        while not self.parar.is_set():
            self.estado.atualizar(self.nome, gravacao_msg="conectando")
            log.info("[%s] iniciando gravação: %s", self.nome, self.canal["url"])
            inicio = time.time()
            sl = subprocess.Popen(self._cmd_streamlink(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  creationflags=CREATE_NO_WINDOW)
            ff = subprocess.Popen(self._cmd_ffmpeg(), stdin=sl.stdout, stderr=subprocess.PIPE,
                                  creationflags=CREATE_NO_WINDOW)
            sl.stdout.close()  # o ffmpeg é o dono do pipe agora
            self._procs = [sl, ff]
            threading.Thread(target=self._vigiar, args=(inicio,), daemon=True).start()

            ff.wait()
            matar_arvore(sl)
            err_sl = (sl.stderr.read() or b"").decode("utf-8", "replace").strip()
            err_ff = (ff.stderr.read() or b"").decode("utf-8", "replace").strip()
            duracao = time.time() - inicio
            self.estado.atualizar(self.nome, gravando=False)
            if self.parar.is_set():
                break
            if "No playable streams" in err_sl or "offline" in err_sl.lower():
                msg = "offline"
            else:
                msg = (err_sl or err_ff or "gravação terminou")[-200:]
            self.estado.atualizar(self.nome, gravacao_msg=msg)
            log.warning("[%s] gravação parou após %.0fs: %s", self.nome, duracao, msg)
            # se rodou bastante tempo, reconecta rápido; se falhou de cara, espera mais
            espera = 5 if duracao > 60 else min(espera * 1.5, 60)
            self.parar.wait(espera)

    def _vigiar(self, inicio: float):
        """Marca 'gravando' quando chegam dados novos e derruba a gravação se ela TRAVAR.

        Visto em 17/11: a rede mudou (Wi-Fi reconectou) e o streamlink ficou vivo mas sem
        mandar nada; o ffmpeg esperava para sempre e os cortes saíam com 0,1 s.
        """
        limite = float(self.cfg["geral"].get("gravacao_travada_seg", 40))
        ultimo_sinal = (None, -1)
        ultima_mudanca = time.time()
        procs = list(self._procs)
        while not self.parar.is_set() and any(p.poll() is None for p in procs):
            segs = listar_segmentos(self.pasta)
            if segs:
                t, p = segs[-1]
                try:
                    sinal = (p.name, p.stat().st_size)
                except OSError:
                    sinal = ultimo_sinal
                if sinal != ultimo_sinal:
                    ultimo_sinal, ultima_mudanca = sinal, time.time()
                    if t.timestamp() >= inicio - 2:
                        self.estado.atualizar(self.nome, gravando=True, gravacao_msg="gravando",
                                              ultimo_segmento=t.strftime("%H:%M:%S"))
            parado = time.time() - ultima_mudanca
            if parado > limite and time.time() - inicio > limite:
                log.warning("[%s] gravação travada (%.0fs sem dados novos): reconectando", self.nome, parado)
                self.estado.atualizar(self.nome, gravando=False, gravacao_msg="travou, reconectando")
                for pr in procs:
                    matar_arvore(pr)
                return
            time.sleep(2)

    def _limpeza(self):
        limite = self.cfg["geral"]["buffer_minutos"] * 60
        while not self.parar.is_set():
            agora = time.time()
            for t, p in listar_segmentos(self.pasta):
                if agora - t.timestamp() > limite:
                    try:
                        p.unlink()
                    except OSError:
                        pass  # ainda aberto; tenta na próxima
            self.parar.wait(30)

    def encerrar(self):
        self.parar.set()
        for p in self._procs:
            matar_arvore(p)
