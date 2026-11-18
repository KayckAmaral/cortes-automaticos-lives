"""Liga, desliga, adiciona e ajusta canais em tempo real (usado pelo painel)."""
from __future__ import annotations

import logging
import re
import threading
from urllib.parse import parse_qs, urlparse

from .audio import MonitorAudio
from .chat import criar_leitor
from .detector import Detector
from .gravador import Gravador, listar_segmentos
from .legenda_ass import texto_credito
from .util import FFMPEG, RAIZ, config_canal, rodar, salvar_canais

log = logging.getLogger("gerenciador")

# campos que o painel pode alterar, com tipo e limites
CAMPOS = {
    "detector": {
        "multiplicador": (float, 1.2, 20), "minimo_absoluto": (float, 1, 2000),
        "min_usuarios_unicos": (int, 1, 1000), "pausa_entre_cortes_seg": (int, 10, 3600),
        "janela_seg": (int, 2, 30), "base_minutos": (int, 1, 30),
        "limite_saudacoes": (float, 0.1, 1.0),
    },
    "corte": {"antes_seg": (float, 5, 120), "depois_seg": (float, 0, 60)},
    "audio": {"limiar_db": (float, 4, 30), "confirmacao_chat": (float, 1.0, 5.0)},
}
CAMPOS_RAIZ = {"offset_seg": (float, -60, 60), "gameplay_offset_x": (float, 0, 1)}


def interpretar_url(url: str) -> tuple[str, str, str]:
    """URL → (plataforma, nome, url_normalizada)."""
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    u = urlparse(url)
    host = u.netloc.lower().replace("www.", "").replace("m.", "")
    partes = [p for p in u.path.split("/") if p]
    if host.endswith("kick.com") and partes:
        return "kick", partes[0].lower(), f"https://kick.com/{partes[0]}"
    if host.endswith("twitch.tv") and partes:
        return "twitch", partes[0].lower(), f"https://twitch.tv/{partes[0]}"
    if host.endswith("youtube.com") or host == "youtu.be":
        if host == "youtu.be" and partes:
            return "youtube", partes[0], f"https://www.youtube.com/watch?v={partes[0]}"
        if partes and partes[0] == "watch":
            vid = parse_qs(u.query).get("v", [""])[0]
            return "youtube", vid, f"https://www.youtube.com/watch?v={vid}"
        if partes and partes[0].startswith("@"):
            return "youtube", partes[0][1:].lower(), f"https://www.youtube.com/{partes[0]}/live"
        if len(partes) >= 2 and partes[0] in ("channel", "c", "user"):
            return "youtube", partes[1].lower(), f"https://www.youtube.com/{partes[0]}/{partes[1]}/live"
    raise ValueError("URL não reconhecida. Use um link da Kick, Twitch ou YouTube.")


class Gerenciador:
    def __init__(self, cfg: dict, canais: list[dict], estado, fila):
        self.cfg = cfg
        self.lista = canais              # lista persistida (ordem do arquivo)
        self.por_nome = fila.canais      # dict compartilhado com a fila
        self.estado = estado
        self.fila = fila
        self.lock = threading.RLock()
        self.rodando: dict[str, dict] = {}   # nome -> {det, leitor, grav}
        # preenchido pelo VigiaDisco; "pausados" = canais parados por falta de espaço (retomar manual)
        self.disco = {"baixo": False, "livre_gb": None, "limite_gb": None, "pausados": []}
        for c in canais:
            self.por_nome[c["nome"]] = c
            self._publicar(c)

    # ------------------------------------------------------------------ estado
    def _publicar(self, c: dict):
        ch = self.estado.canal(c["nome"])
        with self.estado.lock:
            ch.update(plataforma=c["plataforma"], url=c["url"], ativo=bool(c.get("ativo")),
                      rodando=c["nome"] in self.rodando, config=self._config_visivel(c))
            if c["nome"] in self.disco["pausados"]:
                ch.update(gravando=False, gravacao_msg="⛔ pausado: disco cheio", chat_ok=False,
                          chat_msg="⛔ pausado: disco cheio")
            elif c["nome"] not in self.rodando:
                ch.update(gravando=False, gravacao_msg="parado", chat_ok=False, chat_msg="parado")

    def _config_visivel(self, c: dict) -> dict:
        det = config_canal(self.cfg, c, "detector")
        corte = config_canal(self.cfg, c, "corte")
        aud = config_canal(self.cfg, c, "audio")
        return {
            "audio": {"ativo": bool(aud.get("ativo", True)), **{k: aud.get(k) for k in CAMPOS["audio"]}},
            "detector": {**{k: det.get(k) for k in CAMPOS["detector"]}, "saudacoes": det.get("saudacoes") or []},
            "corte": {k: corte.get(k) for k in CAMPOS["corte"]},
            "offset_seg": c.get("offset_seg", 0),
            "gameplay_offset_x": c.get("gameplay_offset_x", 0.5),
            "layout": c.get("layout", "so_gameplay"),
            "camera": c.get("camera"),
            # só para a prévia do painel
            "zoom_so_gameplay": config_canal(self.cfg, c, "saida").get("zoom_so_gameplay", 1.35),
            "legenda_y": config_canal(self.cfg, c, "legenda").get("posicao_y", 0.36),
            "falas_jogo": config_canal(self.cfg, c, "legenda").get("falas_jogo", "silencio"),
            "traduzir_jogo": bool(config_canal(self.cfg, c, "legenda").get("traduzir_jogo", True)),
            "credito_ativo": c.get("credito_ativo", True) is not False,
            "credito_texto": c.get("credito_texto") or "",
            "credito_padrao": texto_credito({**c, "credito_texto": "", "credito_ativo": True}, {}) or "",
        }

    def _salvar(self):
        salvar_canais(self.lista)

    # ------------------------------------------------------------------ ciclo de vida
    def iniciar(self, nome: str):
        with self.lock:
            c = self.por_nome[nome]
            if nome in self.rodando:
                return
            if self.disco["baixo"]:
                if nome not in self.disco["pausados"]:
                    self.disco["pausados"].append(nome)
                self._publicar(c)
                raise RuntimeError(f"Disco quase cheio ({self.disco['livre_gb']} GB livres, mínimo "
                                   f"{self.disco['limite_gb']:.0f} GB). Libere espaço antes de iniciar.")
            det = Detector(c, config_canal(self.cfg, c, "detector"), self.estado, self.fila.adicionar)
            leitor = criar_leitor(c, det.receber, self.estado)
            grav = Gravador(c, self.cfg, self.estado)
            aud = MonitorAudio(c, self.cfg, config_canal(self.cfg, c, "audio"), det, self.estado)
            for t in (det, leitor, grav, aud):
                t.start()
            self.rodando[nome] = {"det": det, "leitor": leitor, "grav": grav, "audio": aud}
            c["ativo"] = True
            self._salvar()
            self._publicar(c)
            log.info("canal %s (%s) iniciado", nome, c["plataforma"])

    def pausar_por_disco(self):
        """Para todos os canais SEM marcar ativo: false (o 'Retomar' do alerta liga de novo)."""
        with self.lock:
            for nome in list(self.rodando):
                for t in self.rodando.pop(nome).values():
                    t.encerrar()
                if nome not in self.disco["pausados"]:
                    self.disco["pausados"].append(nome)
                log.warning("canal %s pausado (disco cheio)", nome)
                self._publicar(self.por_nome[nome])

    def retomar_disco(self) -> list[str]:
        with self.lock:
            if self.disco["baixo"]:
                raise RuntimeError(f"O disco ainda está com {self.disco['livre_gb']} GB livres. Libere espaço "
                                   f"até passar de {self.disco['limite_gb']:.0f} GB (apague cortes em Vídeos).")
            nomes = [n for n in self.disco["pausados"] if n in self.por_nome]
            self.disco["pausados"] = []
        for nome in nomes:
            self.iniciar(nome)
        log.info("canais retomados depois do disco cheio: %s", nomes)
        return nomes

    def info_disco(self) -> dict:
        with self.lock:
            return {**self.disco, "pausados": list(self.disco["pausados"])}

    def parar(self, nome: str, salvar=True):
        with self.lock:
            if nome in self.disco["pausados"]:
                self.disco["pausados"].remove(nome)
            r = self.rodando.pop(nome, None)
            if r:
                for t in r.values():
                    t.encerrar()
                log.info("canal %s parado", nome)
            c = self.por_nome.get(nome)
            if c:
                c["ativo"] = False
                if salvar:
                    self._salvar()
                self._publicar(c)

    def adicionar(self, url: str, iniciar=True) -> dict:
        plataforma, nome, url_norm = interpretar_url(url)
        nome = re.sub(r"[^\w.-]", "_", nome)[:40] or "canal"
        with self.estado.lock:
            self.estado.removidos.discard(nome)
        with self.lock:
            if nome in self.por_nome:
                c = self.por_nome[nome]
            else:
                c = {"nome": nome, "plataforma": plataforma, "url": url_norm, "ativo": False,
                     "offset_seg": 0, "layout": "so_gameplay", "camera": None, "gameplay_offset_x": 0.5}
                self.lista.append(c)
                self.por_nome[nome] = c
                self._salvar()
                log.info("canal adicionado: %s (%s)", nome, url_norm)
            self._publicar(c)
        if iniciar:
            self.iniciar(nome)
        return c

    def remover(self, nome: str):
        self.parar(nome, salvar=False)
        with self.lock:
            c = self.por_nome.pop(nome, None)
            if c in self.lista:
                self.lista.remove(c)
            self._salvar()
            self.estado.remover(nome)
        log.info("canal removido: %s", nome)

    def reordenar(self, nomes: list[str]):
        """Nova ordem dos canais (painel). Nomes desconhecidos são ignorados; os que faltarem vão pro fim."""
        with self.lock:
            pos = {n: i for i, n in enumerate(nomes)}
            self.lista.sort(key=lambda c: pos.get(c["nome"], len(pos)))
            self._salvar()
            with self.estado.lock:
                velho = self.estado.canais
                self.estado.canais = {c["nome"]: velho[c["nome"]] for c in self.lista if c["nome"] in velho}
                for n, v in velho.items():  # segurança: não perde nada
                    self.estado.canais.setdefault(n, v)
            log.info("nova ordem dos canais: %s", [c["nome"] for c in self.lista])

    # ------------------------------------------------------------------ ajustes
    def ajustar(self, nome: str, dados: dict) -> dict:
        with self.lock:
            c = self.por_nome[nome]
            for secao, campos in CAMPOS.items():
                for k, v in (dados.get(secao) or {}).items():
                    if k in campos and v not in (None, ""):
                        tipo, mn, mx = campos[k]
                        c.setdefault(secao, {})[k] = min(mx, max(mn, tipo(v)))
            saud = (dados.get("detector") or {}).get("saudacoes")
            if saud is not None:
                if isinstance(saud, str):
                    saud = saud.replace("\n", ",").split(",")
                c.setdefault("detector", {})["saudacoes"] = \
                    list(dict.fromkeys(s.strip().upper() for s in saud if s.strip()))[:100]
            for k, (tipo, mn, mx) in CAMPOS_RAIZ.items():
                if dados.get(k) not in (None, ""):
                    c[k] = min(mx, max(mn, tipo(dados[k])))
            if dados.get("falas_jogo") in ("desligado", "silencio", "nunca"):
                c.setdefault("legenda", {})["falas_jogo"] = dados["falas_jogo"]
            if isinstance((dados.get("audio") or {}).get("ativo"), bool):
                c.setdefault("audio", {})["ativo"] = dados["audio"]["ativo"]
            if isinstance(dados.get("credito_ativo"), bool):
                c["credito_ativo"] = dados["credito_ativo"]
            if isinstance(dados.get("credito_texto"), str):
                c["credito_texto"] = dados["credito_texto"].strip()[:60]
            if isinstance(dados.get("traduzir_jogo"), bool):
                c.setdefault("legenda", {})["traduzir_jogo"] = dados["traduzir_jogo"]
            if dados.get("layout") in ("so_gameplay", "camera_gameplay"):
                c["layout"] = dados["layout"]
            if "camera" in dados:
                cam = dados["camera"]
                if cam:
                    c["camera"] = {k: round(min(1.0, max(0.0, float(cam[k]))), 4) for k in ("x", "y", "w", "h")}
                    if c["camera"]["w"] < 0.02 or c["camera"]["h"] < 0.02:
                        raise ValueError("retângulo da webcam pequeno demais")
                else:
                    c["camera"] = None
            if c.get("layout") == "camera_gameplay" and not c.get("camera"):
                c["layout"] = "so_gameplay"
            # aplica no detector em execução (ele lê self.c a cada segundo)
            r = self.rodando.get(nome)
            if r:
                r["det"].c.update(config_canal(self.cfg, c, "detector"))
                r["audio"].c.update(config_canal(self.cfg, c, "audio"))
            self._salvar()
            self._publicar(c)
            log.info("ajustes de %s atualizados: %s", nome, self._config_visivel(c))
            return self._config_visivel(c)

    def frame_png(self, nome: str) -> bytes:
        """Print da live (do buffer gravado) para calibrar a webcam."""
        pasta = RAIZ / self.cfg["geral"]["pasta_buffer"] / nome
        segs = listar_segmentos(pasta) if pasta.exists() else []
        if len(segs) < 2:
            raise RuntimeError("ainda não há gravação desse canal (ele precisa estar ao vivo e rodando)")
        seg = segs[-2][1]  # o penúltimo já está fechado
        r = rodar([FFMPEG, "-v", "error", "-ss", "1", "-i", str(seg), "-frames:v", "1",
                   "-f", "image2pipe", "-vcodec", "png", "-"], timeout=30)
        return r.stdout

    def encerrar_tudo(self):
        for nome in list(self.rodando):
            r = self.rodando.pop(nome)
            for t in r.values():
                t.encerrar()
