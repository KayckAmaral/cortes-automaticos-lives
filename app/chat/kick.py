"""Chat da Kick lido por um Chrome invisível (Playwright).

A Kick trocou o Pusher por um servidor Centrifugo próprio que exige um token de visitante
gerado pelo JavaScript do site. Em vez de imitar isso, abrimos a página do canal num Chrome
headless (sem vídeo, imagens e fontes, para ficar leve) e escutamos os frames do WebSocket
`realtime...kick.com`. Se a Kick mudar o protocolo de novo, o site continua resolvendo sozinho.

Frame típico (uma ou mais linhas JSON por frame):
{"push":{"channel":"chatrooms.<id>.v2","pub":{"data":{"event":"App\\Events\\ChatMessageEvent",
 "data":"{\"content\":\"...\",\"sender\":{\"username\":\"...\"},...}"}}}}
"""
from __future__ import annotations

import json
import re
import time

from .base import LeitorBase, log

RE_EMOTE = re.compile(r"\[emote:\d+:([^\]]+)\]")
BLOQUEAR_TIPOS = {"media", "image", "font", "stylesheet"}
SEM_MSG_REINICIA_SEG = 300     # sem nenhuma mensagem por 5 min → reabre a página
REABRIR_A_CADA_SEG = 3 * 3600  # reabre de tempos em tempos (memória do Chrome)


def normalizar(texto: str) -> str:
    return RE_EMOTE.sub(r"\1", texto)


def extrair_mensagens(payload: str):
    """Gera (usuario, texto) de um frame do Centrifugo."""
    for linha in payload.splitlines():
        if "ChatMessageEvent" not in linha:
            continue
        try:
            pub = json.loads(linha)["push"]["pub"]["data"]
            d = pub.get("data")
            d = json.loads(d) if isinstance(d, str) else d
            usuario = (d.get("sender") or {}).get("username", "?")
            yield usuario, normalizar(d.get("content", ""))
        except (KeyError, ValueError, TypeError, AttributeError):
            continue


def _bloquear(route):
    req = route.request
    url = req.url
    if req.resource_type in BLOQUEAR_TIPOS or ".m3u8" in url or url.endswith(".ts") or "playback" in url:
        return route.abort()
    return route.continue_()


class ChatKick(LeitorBase):
    def _conectar_e_ler(self):
        from playwright.sync_api import sync_playwright

        slug = self.canal["url"].rstrip("/").split("/")[-1]
        self.status(False, "abrindo Chrome invisível")
        estado = {"ultima": time.time(), "conectado": False}

        def no_frame(payload):
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8", "replace")
            agora = time.time()
            for usuario, texto in extrair_mensagens(payload):
                estado["ultima"] = agora
                self.callback(agora, usuario, texto)

        def no_ws(ws):
            if "realtime" in ws.url:
                estado["conectado"] = True
                self.status(True, "conectado")
                log.info("[%s] chat Kick conectado (via navegador)", self.nome)
                ws.on("framereceived", no_frame)
                ws.on("close", lambda *_: estado.update(conectado=False))

        with sync_playwright() as p:
            navegador = p.chromium.launch(
                channel="chrome", headless=True,
                args=["--mute-audio", "--disable-gpu", "--blink-settings=imagesEnabled=false"])
            try:
                ctx = navegador.new_context(viewport={"width": 1366, "height": 768}, locale="pt-BR")
                pagina = ctx.new_page()
                pagina.route("**/*", _bloquear)
                pagina.on("websocket", no_ws)
                pagina.goto(f"https://kick.com/{slug}", wait_until="domcontentloaded", timeout=60000)
                aberto_em = time.time()
                while not self.parar.is_set():
                    pagina.wait_for_timeout(1000)  # processa os eventos do WebSocket
                    agora = time.time()
                    if agora - estado["ultima"] > SEM_MSG_REINICIA_SEG:
                        raise ConnectionError("sem mensagens há 5 min (live offline ou conexão caiu)")
                    if agora - aberto_em > REABRIR_A_CADA_SEG:
                        log.info("[%s] reabrindo página do chat (manutenção)", self.nome)
                        return
                    if not estado["conectado"] and agora - aberto_em > 60:
                        raise ConnectionError("WebSocket do chat não conectou")
            finally:
                navegador.close()
