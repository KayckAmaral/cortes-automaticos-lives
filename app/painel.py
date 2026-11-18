"""Painel ao vivo em http://127.0.0.1:<porta> (servidor HTTP embutido, sem dependências)."""
from __future__ import annotations

import ipaddress
import json
import logging
import mimetypes
import secrets
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import capa, galeria
from .util import RAIZ

log = logging.getLogger("painel")
HTML = Path(__file__).with_name("painel.html")
HTML_GALERIA = Path(__file__).with_name("galeria.html")


_uso = {}


def _medir_uso():
    """Mede CPU/RAM a cada 2 s numa thread própria. (Medir a cada pedido do painel dava quase sempre
    0%, porque o intervalo entre pedidos é curto e vários navegadores perguntam ao mesmo tempo.)"""
    try:
        import psutil
    except ImportError:
        return
    while True:
        cpu = psutil.cpu_percent(interval=2)
        mem = psutil.virtual_memory()
        _uso.update(cpu=round(cpu), ram=round(mem.percent), ram_livre_gb=round(mem.available / 2**30, 1))


def _uso_sistema() -> dict:
    """CPU/RAM do notebook (para saber se aguenta mais um canal)."""
    return dict(_uso)


def _ip_tailscale() -> str | None:
    """IP do Tailscale (100.64.0.0/10), se instalado: o celular acessa de qualquer rede."""
    try:
        import psutil
        for enderecos in psutil.net_if_addrs().values():
            for e in enderecos:
                if e.family == socket.AF_INET and ipaddress.ip_address(e.address) in ipaddress.ip_network("100.64.0.0/10"):
                    return e.address
    except Exception:
        pass
    return None


def _ip_local() -> str:
    """IP do notebook na rede Wi-Fi/cabo (não envia nada: só pergunta ao sistema a rota).
    Com Tailscale, usa o IP dele (funciona fora do Wi-Fi de casa)."""
    ts = _ip_tailscale()
    if ts:
        return ts
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _chave_celular() -> str:
    """Chave secreta do acesso pelo celular (criada uma vez e guardada em painel_chave.txt)."""
    arq = RAIZ / "painel_chave.txt"
    if arq.exists():
        k = arq.read_text(encoding="utf-8").strip()
        if len(k) >= 10:
            return k
    k = secrets.token_urlsafe(12)
    arq.write_text(k, encoding="utf-8")
    return k


def iniciar_painel(cfg: dict, estado, ger, abrir_navegador: bool = True, capas=None):
    porta = int(cfg.get("painel", {}).get("porta", 8000))
    pasta_cortes = (RAIZ / cfg["geral"]["pasta_cortes"]).resolve()
    pasta_postar = capa.PASTA.resolve()
    celular = bool(cfg.get("painel", {}).get("acesso_celular", False))
    chave = _chave_celular() if celular else ""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silencioso
            pass

        # ---------------------------------------------------------- acesso
        def _local(self) -> bool:
            return self.client_address[0] in ("127.0.0.1", "::1")

        def _autorizado(self) -> bool:
            """Notebook: sempre. Celular/rede: só com a chave (no link do QR ou no cookie)."""
            if self._local():
                return True
            if not celular:
                return False
            q = parse_qs(urlparse(self.path).query).get("chave", [""])[0]
            if q and secrets.compare_digest(q, chave):
                self._nova_chave_cookie = True
                return True
            for parte in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = parte.strip().partition("=")
                if k == "chave_painel" and v and secrets.compare_digest(v, chave):
                    return True
            return False

        def end_headers(self):
            if getattr(self, "_nova_chave_cookie", False):
                self.send_header("Set-Cookie", f"chave_painel={chave}; Path=/; Max-Age=2592000; SameSite=Strict; HttpOnly")
                self._nova_chave_cookie = False
            super().end_headers()

        def _negar(self):
            msg = ("<h2>Acesso negado</h2><p>Abra o painel pelo QR code do botão <b>📱 Celular</b> "
                   "no notebook.</p>").encode("utf-8")
            self.send_response(403)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

        def _json(self, obj, code=200):
            dados = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(dados)

        def _corpo(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def do_GET(self):
            if not self._autorizado():
                return self._negar()
            caminho = unquote(urlparse(self.path).path)
            if caminho == "/api/celular":
                if not self._local():
                    return self._json({"erro": "só no notebook"}, 403)
                if not celular:
                    return self._json({"ativo": False})
                return self._json({"ativo": True, "tailscale": _ip_tailscale() is not None,
                                   "url": f"http://{_ip_local()}:{porta}/?chave={chave}"})
            if caminho in ("/", "/index.html", "/galeria", "/videos"):
                dados = (HTML_GALERIA if caminho in ("/galeria", "/videos") else HTML).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(dados)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(dados)
            elif caminho == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            elif caminho == "/api/cortes":
                itens = galeria.listar(pasta_cortes)
                editando = ger.fila.em_edicao()
                for i in itens:
                    i["editando"] = i["id"] in editando
                self._json(itens)
            elif caminho == "/api/estado":
                snap = estado.snapshot()
                snap["videos_novos"] = galeria.contar_novos(pasta_cortes)
                snap["sistema"] = _uso_sistema()
                snap["disco"] = ger.info_disco()
                self._json(snap)
            elif caminho.startswith("/api/webcam/"):
                nome = caminho.rsplit("/", 1)[-1]
                if nome not in ger.por_nome:
                    return self._json({"erro": "canal desconhecido"}, 404)
                try:
                    return self._json({"ok": True, **ger.detectar_webcam(nome)})
                except Exception as e:  # noqa: BLE001
                    return self._json({"erro": str(e)}, 400)
            elif caminho.startswith("/api/frame/"):
                nome = caminho.rsplit("/", 1)[-1]
                try:
                    png = ger.frame_png(nome)
                except Exception as e:  # noqa: BLE001
                    return self._json({"erro": str(e)}, 400)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(png)
            elif caminho.startswith(("/cortes/", "/postar/")):
                self._arquivo(caminho)
            else:
                self.send_error(404)

        def do_POST(self):
            if not self._autorizado():
                return self._negar()
            caminho = unquote(urlparse(self.path).path)
            partes = caminho.strip("/").split("/")  # api / <acao> / <nome>
            try:
                if caminho == "/api/editar":
                    d = self._corpo()
                    corte_id = str(d.get("id", ""))
                    if not galeria.RE_ID.match(corte_id) or corte_id.startswith("."):
                        return self._json({"erro": "id de corte inválido"}, 400)
                    s, e = float(d["inicio"]), float(d["fim"])
                    if e - s < 3 or e - s > 180:
                        return self._json({"erro": "o corte precisa ter entre 3 s e 3 min"}, 400)
                    item = next((i for i in galeria.listar(pasta_cortes) if i["id"] == corte_id), None)
                    if not item or not item["fonte"]:
                        return self._json({"erro": "esse corte não tem sobra para edição"}, 400)
                    if s < 0 or e > item["fonte"]["duracao"] + 0.5:
                        return self._json({"erro": "trecho fora do vídeo disponível"}, 400)
                    ger.fila.adicionar_edicao(corte_id, s, e)
                    return self._json({"ok": True})
                if caminho == "/api/reverter":
                    corte_id = str(self._corpo().get("id", ""))
                    if not galeria.RE_ID.match(corte_id) or corte_id.startswith("."):
                        return self._json({"erro": "id de corte inválido"}, 400)
                    ger.fila.reverter(corte_id)
                    return self._json({"ok": True})
                if caminho == "/api/assistido":
                    d = self._corpo()
                    galeria.marcar(pasta_cortes, str(d.get("id", "")), "assistido", bool(d.get("assistido", True)),
                                   ger.fila.lock_arquivos)
                    return self._json({"ok": True})
                if caminho == "/api/marcar":
                    d = self._corpo()
                    galeria.marcar(pasta_cortes, str(d.get("id", "")), str(d.get("campo", "")),
                                   bool(d.get("valor", True)), ger.fila.lock_arquivos)
                    if capas and d.get("campo") == "postar":
                        capas.acordar()   # gera (ou apaga) a capa na hora
                    return self._json({"ok": True})
                if caminho == "/api/capa":
                    d = self._corpo()
                    corte_id = str(d.get("id", ""))
                    if not capas:
                        return self._json({"erro": "gerador de capas desligado"}, 400)
                    if not galeria.RE_ID.match(corte_id) or corte_id.startswith("."):
                        return self._json({"erro": "id de corte inválido"}, 400)
                    capas.definir_texto(corte_id, str(d.get("texto", "")))
                    return self._json({"ok": True})
                if caminho == "/api/apagar_canal":
                    canal = str(self._corpo().get("canal", ""))
                    itens = [i for i in galeria.listar(pasta_cortes) if i["canal"] == canal]
                    if not canal or not itens:
                        return self._json({"erro": "nenhum corte desse streamer"}, 400)
                    em_edicao = ger.fila.em_edicao()
                    apagados, pulados = 0, 0
                    for i in itens:
                        if i["id"] in em_edicao:
                            pulados += 1
                            continue
                        try:
                            galeria.apagar(pasta_cortes, i["id"])
                            estado.remover_corte("/cortes/" + i["id"] + ".mp4")
                            apagados += 1
                        except (ValueError, RuntimeError):
                            pulados += 1
                    return self._json({"ok": True, "apagados": apagados, "pulados": pulados})
                if caminho == "/api/apagar":
                    corte_id = self._corpo().get("id", "")
                    if corte_id in ger.fila.em_edicao():
                        return self._json({"erro": "esse corte está sendo ajustado; aguarde terminar"}, 400)
                    removidos = galeria.apagar(pasta_cortes, corte_id)
                    estado.remover_corte("/cortes/" + corte_id + ".mp4")
                    return self._json({"ok": True, "removidos": removidos})
                if caminho == "/api/ordem":
                    nomes = self._corpo().get("nomes") or []
                    if not isinstance(nomes, list):
                        return self._json({"erro": "lista inválida"}, 400)
                    ger.reordenar([str(n) for n in nomes])
                    return self._json({"ok": True})
                if caminho == "/api/disco/retomar":
                    return self._json({"ok": True, "retomados": ger.retomar_disco()})
                if caminho == "/api/canais":
                    c = ger.adicionar(self._corpo().get("url", ""))
                    return self._json({"ok": True, "nome": c["nome"]})
                if len(partes) == 3 and partes[0] == "api":
                    acao, nome = partes[1], partes[2]
                    if nome not in ger.por_nome:
                        return self._json({"erro": "canal desconhecido"}, 404)
                    if acao == "cortar":
                        r = ger.rodando.get(nome)
                        if not r:
                            return self._json({"erro": "canal parado"}, 400)
                        threading.Thread(target=r["det"].corte_manual, daemon=True).start()
                        return self._json({"ok": True})
                    if acao == "iniciar":
                        ger.iniciar(nome)
                        return self._json({"ok": True})
                    if acao == "parar":
                        ger.parar(nome)
                        return self._json({"ok": True})
                    if acao == "remover":
                        ger.remover(nome)
                        return self._json({"ok": True})
                    if acao == "ajustes":
                        return self._json({"ok": True, "config": ger.ajustar(nome, self._corpo())})
            except (ValueError, KeyError, RuntimeError, TypeError, FileNotFoundError) as e:
                return self._json({"erro": str(e)}, 400)
            self.send_error(404)

        def _arquivo(self, caminho: str):
            alvo = (RAIZ / caminho.lstrip("/")).resolve()
            if (pasta_cortes not in alvo.parents and pasta_postar not in alvo.parents) or not alvo.is_file():
                return self.send_error(404)
            tamanho = alvo.stat().st_size
            tipo = mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
            ini, fim = 0, tamanho - 1
            rng = self.headers.get("Range")
            if rng and rng.startswith("bytes="):  # suporte a Range para o player poder avançar
                a, _, b = rng[6:].partition("-")
                ini = int(a) if a else 0
                fim = min(int(b), tamanho - 1) if b else tamanho - 1
                if ini >= tamanho or ini > fim:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{tamanho}")
                    self.send_header("Content-Length", "0")
                    return self.end_headers()
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {ini}-{fim}/{tamanho}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(fim - ini + 1))
            self.end_headers()
            # abre e fecha o arquivo a cada pedaço: no Windows, arquivo aberto não pode ser apagado,
            # e o navegador fica carregando o vídeo por bastante tempo (o "Apagar" falhava)
            try:
                pos, resta = ini, fim - ini + 1
                while resta > 0:
                    try:
                        with open(alvo, "rb") as f:
                            f.seek(pos)
                            bloco = f.read(min(256 * 1024, resta))
                    except OSError:
                        break  # apagado no meio do envio
                    if not bloco:
                        break
                    self.wfile.write(bloco)
                    pos += len(bloco)
                    resta -= len(bloco)
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                pass

    # com acesso pelo celular, escuta na rede (protegido pela chave); senão, só no próprio notebook
    threading.Thread(target=_medir_uso, daemon=True, name="uso").start()
    srv = ThreadingHTTPServer(("0.0.0.0" if celular else "127.0.0.1", porta), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True, name="painel").start()
    url = f"http://localhost:{porta}"
    log.info("painel em %s", url)
    if celular:
        onde = f"qualquer rede via Tailscale {_ip_tailscale()}" if _ip_tailscale() else "mesma rede Wi-Fi"
        log.info("acesso pelo celular ATIVO (%s): botão 📱 Celular no painel mostra o QR code", onde)
    if abrir_navegador:
        webbrowser.open(url)
    return srv
