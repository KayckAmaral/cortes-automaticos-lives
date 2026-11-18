"""Segundo sinal de pico: grito/risada do streamer (volume que dispara na faixa da voz).

Como funciona (por canal):
1. Cada segmento .ts que fecha no buffer tem o áudio decodificado (16 kHz mono) com filtro
   passa-faixa 300–3500 Hz (voz humana; corta grave de explosão/música).
2. Mede o volume (dBFS) a cada 0,25 s. A "linha de base" é a mediana dos últimos N minutos.
3. Se a média de 1 s passar de base + limiar_db (padrão 12 dB) → candidato.
4. 15 s depois, confirma com o chat: a reação do chat nesse intervalo precisa chegar a
   confirmacao_chat × o normal (padrão 1,5×, bem menos que os 3× de um pico só de chat).
   Isso evita cortar todo tiro/explosão alto do jogo.
5. Confirmado → corte centrado no grito (−15 s / +15 s), marcado como gatilho "audio".
"""
from __future__ import annotations

import logging
import statistics
import threading
import time
from collections import deque

import numpy as np

from .gravador import listar_segmentos
from .util import FFMPEG, RAIZ, rodar

log = logging.getLogger("audio")
PASSO = 0.25          # segundos por medição
SR = 16000


class MonitorAudio(threading.Thread):
    def __init__(self, canal: dict, cfg: dict, cfg_audio: dict, detector, estado):
        super().__init__(daemon=True, name=f"audio-{canal['nome']}")
        self.nome = canal["nome"]
        self.c = cfg_audio
        self.det = detector
        self.estado = estado
        self.pasta = RAIZ / cfg["geral"]["pasta_buffer"] / self.nome
        self.parar = threading.Event()
        self.niveis: deque = deque()          # (t, dB) a cada 0,25 s
        self.feitos: set[str] = set()
        self.verificado_ate = 0.0             # até onde já procurou picos
        self.ultimo_candidato = 0.0
        self.pendentes: list[tuple[float, float]] = []   # (t do grito, dB acima da base)

    # ------------------------------------------------------------------
    def run(self):
        while not self.parar.is_set():
            try:
                if self.c.get("ativo", True):
                    self._ler_segmentos()
                    self._procurar_picos()
                    self._confirmar()
            except Exception:  # noqa: BLE001
                log.exception("[%s] erro no monitor de áudio", self.nome)
            self.parar.wait(2)

    def _ler_segmentos(self):
        segs = listar_segmentos(self.pasta) if self.pasta.exists() else []
        agora = time.time()
        for t, p in segs[:-1]:                     # o último ainda está sendo gravado
            if p.name in self.feitos:
                continue
            self.feitos.add(p.name)
            if agora - t.timestamp() > 90:         # antigo (ex.: ao iniciar): não interessa
                continue
            try:
                r = rodar([FFMPEG, "-nostdin", "-v", "error", "-i", str(p), "-vn", "-ac", "1", "-ar", str(SR),
                           "-af", "highpass=f=300,lowpass=f=3500", "-f", "s16le", "-"], timeout=30)
            except RuntimeError:
                continue
            x = np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768.0
            n = int(SR * PASSO)
            for k in range(len(x) // n):
                bloco = x[k * n:(k + 1) * n]
                db = 20 * np.log10(float(np.sqrt(np.mean(bloco ** 2))) + 1e-7)
                self.niveis.append((t.timestamp() + k * PASSO, db))
        # mantém só a janela da linha de base
        limite = agora - float(self.c.get("base_minutos", 5)) * 60
        while self.niveis and self.niveis[0][0] < limite:
            self.niveis.popleft()
        nomes = {p.name for _, p in segs}
        self.feitos &= nomes

    def _procurar_picos(self):
        if len(self.niveis) < int(60 / PASSO):     # 1 min de aquecimento
            return
        dbs = [d for _, d in self.niveis]
        base = statistics.median(dbs)
        limiar = base + float(self.c.get("limiar_db", 12))
        minimo = float(self.c.get("minimo_db", -38))
        pts = list(self.niveis)
        janela = int(1 / PASSO)                    # média de 1 s
        atual = None
        for i in range(len(pts) - janela + 1):
            t = pts[i][0]
            if t <= self.verificado_ate:
                continue
            media = sum(d for _, d in pts[i:i + janela]) / janela
            if media >= limiar and media >= minimo and t - self.ultimo_candidato > 20:
                self.ultimo_candidato = t
                self.pendentes.append((t, media - base))
                log.info("[%s] 🔊 volume disparou às %s (+%.1f dB acima do normal): aguardando o chat confirmar",
                         self.nome, time.strftime("%H:%M:%S", time.localtime(t)), media - base)
            atual = t
        if atual:
            self.verificado_ate = atual
        with self.estado.lock:
            ch = self.estado.canais.get(self.nome)
            if ch is not None:
                ch["audio_db"] = round(dbs[-1], 1)
                ch["audio_base"] = round(base, 1)
                ch["audio_limiar"] = round(limiar, 1)

    def _confirmar(self):
        espera = float(self.c.get("espera_chat_seg", 15))
        agora = time.time()
        restantes = []
        for t, acima in self.pendentes:
            if agora - t < espera + 2:
                restantes.append((t, acima))
                continue
            rel = self.det.reacao_relativa(t, t + espera)
            if rel >= float(self.c.get("confirmacao_chat", 1.5)):
                self.det.emitir_audio(t, rel, acima)
            else:
                log.info("[%s] 🔊 grito às %s descartado: chat não reagiu (%.1fx o normal)",
                         self.nome, time.strftime("%H:%M:%S", time.localtime(t)), rel)
        self.pendentes = restantes

    def encerrar(self):
        self.parar.set()
