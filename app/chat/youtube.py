"""Chat do YouTube lido direto pela API interna (innertube) que o próprio site usa — sem navegador.

Por quê: a biblioteca chat-downloader quebrou com o YouTube atual ("Unable to parse initial
video data", testado em 17/11). Um Chrome invisível (como na Kick) gastaria ~250 MB de RAM a
mais, e o notebook já estava em 85%. Este leitor faz só requisições HTTP leves:

1. /@canal/live → descobre o vídeo ao vivo (link canônico)
2. /live_chat?v=ID → pega a chave da API, a versão do cliente e o 1º "continuation"
3. POST /youtubei/v1/live_chat/get_live_chat → mensagens novas + próximo "continuation"
   (repete no intervalo que o próprio YouTube pede, 1–5 s)
"""
from __future__ import annotations

import json
import re
import time

import requests

from .base import LeitorBase, log

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
RE_CANONICAL = re.compile(r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([\w-]{11})"')
RE_VIDEO = re.compile(r"(?:v=|/live/|youtu\.be/)([\w-]{11})")
RE_KEY = re.compile(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"')
RE_VER = re.compile(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([^"]+)"')
RE_DATA = re.compile(r'(?:window\["ytInitialData"\]|var ytInitialData)\s*=\s*(\{.+?\})\s*;\s*</script>', re.S)


def _sessao() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    s.cookies.set("CONSENT", "YES+1", domain=".youtube.com")
    return s


def resolver_live(url: str, sessao: requests.Session | None = None) -> str:
    """youtube.com/@canal/live → ID do vídeo ao vivo (ou erro se o canal não estiver ao vivo)."""
    m = RE_VIDEO.search(url)
    if m and "/@" not in url:
        return m.group(1)
    s = sessao or _sessao()
    html = s.get(url, timeout=15).text
    m = RE_CANONICAL.search(html)
    if not m:
        raise ConnectionError("canal não está ao vivo")
    return m.group(1)


def _continuacao(bloco: dict) -> tuple[str | None, int]:
    for c in bloco.get("continuations") or []:
        for v in c.values():
            if isinstance(v, dict) and v.get("continuation"):
                return v["continuation"], int(v.get("timeoutMs", 2000))
    return None, 2000


def _texto(runs: list) -> str:
    partes = []
    for r in runs or []:
        if "text" in r:
            partes.append(r["text"])
        elif "emoji" in r:
            e = r["emoji"]
            # emoji normal vem como o próprio caractere; emote do canal vem como :nome:
            partes.append(e.get("emojiId") if not e.get("isCustomEmoji") else (e.get("shortcuts") or [""])[0])
    return "".join(p for p in partes if p)


def extrair_mensagens(acoes: list):
    """(timestamp_epoch, autor, texto) das ações do get_live_chat."""
    for a in acoes or []:
        item = (a.get("addChatItemAction") or {}).get("item") or {}
        r = item.get("liveChatTextMessageRenderer")
        if not r:
            continue
        try:
            ts = int(r.get("timestampUsec", 0)) / 1_000_000 or time.time()
        except ValueError:
            ts = time.time()
        autor = ((r.get("authorName") or {}).get("simpleText") or "?").lstrip("@")
        yield ts, autor, _texto((r.get("message") or {}).get("runs"))


class ChatYouTube(LeitorBase):
    def _conectar_e_ler(self):
        s = _sessao()
        vid = resolver_live(self.canal["url"], s)
        html = s.get(f"https://www.youtube.com/live_chat?is_popout=1&v={vid}", timeout=15).text
        chave, versao, dados = RE_KEY.search(html), RE_VER.search(html), RE_DATA.search(html)
        if not (chave and dados):
            raise ConnectionError("não achei os dados do chat (live sem chat ou página mudou)")
        inicial = json.loads(dados.group(1))
        cont, espera = _continuacao(inicial["contents"]["liveChatRenderer"])
        if not cont:
            raise ConnectionError("chat ao vivo indisponível nessa live")
        api = f"https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?key={chave.group(1)}&prettyPrint=false"
        contexto = {"client": {"clientName": "WEB", "clientVersion": versao.group(1) if versao else "2.20241120.01.00",
                               "hl": "pt", "gl": "BR"}}
        self.status(True, "conectado")
        log.info("[%s] chat YouTube conectado (vídeo %s)", self.nome, vid)
        falhas = 0
        while not self.parar.is_set():
            self.parar.wait(min(max(espera, 1000), 5000) / 1000)
            try:
                r = s.post(api, json={"context": contexto, "continuation": cont}, timeout=15)
                r.raise_for_status()
                j = r.json()
            except (requests.RequestException, ValueError) as e:
                falhas += 1
                if falhas >= 5:
                    raise ConnectionError(f"chat parou de responder: {e}") from e
                continue
            bloco = (j.get("continuationContents") or {}).get("liveChatContinuation")
            if not bloco:
                raise ConnectionError("chat encerrado (live acabou?)")
            falhas = 0
            for ts, autor, texto in extrair_mensagens(bloco.get("actions")):
                if texto:
                    self.callback(ts, autor, texto)
            novo, espera = _continuacao(bloco)
            if not novo:
                raise ConnectionError("chat encerrado (sem continuação)")
            cont = novo
