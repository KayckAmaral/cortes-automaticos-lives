"""Chat da Twitch via IRC anônimo (justinfan)."""
from __future__ import annotations

import random
import re
import socket
import time

from .base import LeitorBase, log

RE_PRIVMSG = re.compile(r"^:(\w+)!\S+ PRIVMSG #\S+ :(.*)$")


class ChatTwitch(LeitorBase):
    def _conectar_e_ler(self):
        login = self.canal["url"].rstrip("/").split("/")[-1].lower()
        s = socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=30)
        s.settimeout(360)
        nick = f"justinfan{random.randint(10000, 99999)}"
        s.sendall(f"NICK {nick}\r\nJOIN #{login}\r\n".encode())
        self.status(True, "conectado")
        log.info("[%s] chat Twitch conectado (#%s)", self.nome, login)
        buf = b""
        try:
            while not self.parar.is_set():
                dados = s.recv(65536)
                if not dados:
                    raise ConnectionError("conexão fechada")
                buf += dados
                *linhas, buf = buf.split(b"\r\n")
                for raw in linhas:
                    linha = raw.decode("utf-8", "replace")
                    if linha.startswith("PING"):
                        s.sendall(("PONG" + linha[4:] + "\r\n").encode())
                        continue
                    m = RE_PRIVMSG.match(linha)
                    if m:
                        self.callback(time.time(), m.group(1), m.group(2))
        finally:
            s.close()
