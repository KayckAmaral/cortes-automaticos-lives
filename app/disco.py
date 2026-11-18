"""Vigia do espaço em disco: abaixo do limite, pausa todos os canais e o painel mostra um alerta.

Os canais pausados continuam com ativo: true no canais.yaml (num reinício voltam pausados de novo
se o disco ainda estiver cheio). Retomar é manual, pelo botão do alerta, depois de liberar espaço.
"""
from __future__ import annotations

import logging
import shutil
import threading

from .util import RAIZ

log = logging.getLogger("disco")


class VigiaDisco(threading.Thread):
    def __init__(self, cfg: dict, ger):
        super().__init__(daemon=True, name="disco")
        self.ger = ger
        self.limite_gb = float(cfg["geral"].get("disco_minimo_gb", 8))
        self.intervalo = 30
        self._parar = threading.Event()

    def checar(self):
        livre_gb = shutil.disk_usage(RAIZ).free / 2**30
        baixo = livre_gb < self.limite_gb
        ger = self.ger
        with ger.lock:
            era_baixo = ger.disco["baixo"]
            ger.disco.update(livre_gb=round(livre_gb, 1), limite_gb=self.limite_gb, baixo=baixo)
        if baixo and not era_baixo:
            log.warning("⛔ disco com só %.1f GB livres (limite %.0f GB): pausando todos os canais",
                        livre_gb, self.limite_gb)
            ger.pausar_por_disco()
        elif baixo and ger.rodando:
            # algum canal foi iniciado por fora (não deveria): pausa de novo
            ger.pausar_por_disco()
        elif era_baixo and not baixo:
            log.info("disco voltou a %.1f GB livres: os canais podem ser retomados pelo painel", livre_gb)

    def run(self):
        while not self._parar.wait(self.intervalo):
            try:
                self.checar()
            except Exception:  # noqa: BLE001
                log.exception("erro ao medir o disco")

    def encerrar(self):
        self._parar.set()
