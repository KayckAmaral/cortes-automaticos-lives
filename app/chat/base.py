from __future__ import annotations

import logging
import threading

log = logging.getLogger("chat")


class LeitorBase(threading.Thread):
    """Thread que fica reconectando para sempre. Subclasses implementam _conectar_e_ler()."""

    def __init__(self, canal: dict, callback, estado):
        super().__init__(daemon=True, name=f"chat-{canal['nome']}")
        self.canal = canal
        self.nome = canal["nome"]
        self.callback = callback
        self.estado = estado
        self.parar = threading.Event()

    def status(self, ok: bool, msg: str):
        self.estado.atualizar(self.nome, chat_ok=ok, chat_msg=msg)

    def run(self):
        espera = 5
        while not self.parar.is_set():
            try:
                self._conectar_e_ler()
                espera = 5
            except Exception as e:  # noqa: BLE001 - nunca derrubar a thread
                log.warning("[%s] chat caiu: %s", self.nome, e)
                self.status(False, f"erro: {str(e)[:150]}")
                espera = min(espera * 2, 60)
            self.parar.wait(espera)

    def _conectar_e_ler(self):
        raise NotImplementedError

    def encerrar(self):
        self.parar.set()
