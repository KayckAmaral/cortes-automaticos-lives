"""Detecta picos de reação no chat (ver PLANO.md, seção 5.3)."""
from __future__ import annotations

import logging
import re
import statistics
import threading
import time
import unicodedata
from collections import Counter, deque

log = logging.getLogger("detector")


def sem_acento(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def compilar_saudacoes(lista) -> re.Pattern | None:
    """["SALVE", "BOA NOITE"] → regex que aceita SALVEEE, BOA  NOITEEE etc. (sem acento, maiúsculas)."""
    partes = []
    for frase in lista or []:
        palavras = sem_acento(str(frase)).upper().split()
        if not palavras:
            continue
        palavras[-1] = re.escape(palavras[-1]) + "+" if len(palavras[-1]) == 1 else \
            re.escape(palavras[-1][:-1]) + re.escape(palavras[-1][-1]) + "+"
        partes.append(r"\s+".join([re.escape(p) for p in palavras[:-1]] + [palavras[-1]]))
    if not partes:
        return None
    return re.compile(r"(?<![A-Z0-9])(?:" + "|".join(partes) + r")(?![A-Z0-9])")


RE_KKK = re.compile(r"K{3,}")
RE_ESPACOS = re.compile(r"\s+")
STOPWORDS = set("""
a o e é de da do das dos em no na nos nas um uma uns umas que se pra para por com sem não nao
mas mais muito já ja eu tu ele ela nós vc vcs voce você isso esse essa isto aqui ai aí lá la
the to and of is it in on kkk kkkk kkkkk mano man cara tá ta tô to foi vai ser era meu minha
""".split())


class Detector(threading.Thread):
    def __init__(self, canal: dict, cfg_det: dict, estado, on_pico):
        super().__init__(daemon=True, name=f"det-{canal['nome']}")
        self.nome = canal["nome"]
        self.canal = canal
        self.c = cfg_det
        self.estado = estado
        self.on_pico = on_pico
        self.parar = threading.Event()
        self.lock = threading.Lock()
        self.msgs: deque = deque()     # (t, usuario, texto_norm, peso)
        self.hist: deque = deque()     # (t, pontuacao)
        self.primeira_msg: float | None = None
        self.ultimo_corte = 0.0
        self.rastreando: dict | None = None
        self.total = 0
        # YouTube entrega em lotes atrasados: avalia uma janela um pouco no passado
        self.atraso_avaliacao = 6.0 if canal["plataforma"] == "youtube" else 0.0
        ignorar = {u.lower() for u in cfg_det.get("ignorar_usuarios", [])}
        self.ignorar = ignorar
        self.pesos: list[tuple[int, list[str]]] = sorted(
            ((int(p), [w.upper() for w in ws]) for p, ws in (cfg_det.get("palavras_peso") or {}).items()),
            reverse=True)

        self._saud_chave = None
        self._saud_re = None
        self._ultimo_ignorado = 0.0

    # ------------------------------------------------------------------ entrada
    def _regex_saudacao(self):
        chave = tuple(self.c.get("saudacoes") or ())
        if chave != self._saud_chave:  # recompila se a lista mudou pelo painel
            self._saud_chave = chave
            self._saud_re = compilar_saudacoes(chave)
        return self._saud_re

    def peso(self, texto_up: str) -> int:
        """0 = saudação/pedido (não conta), 1 = mensagem comum, 2-3 = reação forte."""
        for p, palavras in self.pesos:
            for w in palavras:
                if w in texto_up:
                    return p
        if RE_KKK.search(texto_up):
            return 3
        rx = self._regex_saudacao()
        if rx and rx.search(sem_acento(texto_up)):
            return 0
        return 1

    def receber(self, hora: float, usuario: str, texto: str):
        u = usuario.lower()
        if u in self.ignorar:
            return
        texto = texto.strip()
        if not texto or texto.startswith("!"):
            return
        norm = RE_ESPACOS.sub(" ", texto.upper())[:200]
        with self.lock:
            self.msgs.append((hora, u, norm, self.peso(norm)))
            self.total += 1
            if self.primeira_msg is None:
                self.primeira_msg = time.time()

    # ------------------------------------------------------------------ loop
    def run(self):
        while not self.parar.is_set():
            try:
                self._tick(time.time())
            except Exception:  # noqa: BLE001
                log.exception("[%s] erro no detector", self.nome)
            self.parar.wait(1.0)

    def _janela(self, ini: float, fim: float) -> list:
        return [m for m in self.msgs if ini <= m[0] < fim]

    def _tick(self, agora: float):
        c = self.c
        janela = c["janela_seg"]
        fim = agora - self.atraso_avaliacao
        with self.lock:
            # mantém só o necessário (janela + margem para mensagens do pico)
            while self.msgs and self.msgs[0][0] < agora - 120:
                self.msgs.popleft()
            msgs = self._janela(fim - janela, fim)

        # pontuação: cada usuário conta uma vez, com o maior peso que usou.
        # Saudações valem 0, e quem só mandou saudação não entra na contagem de pessoas.
        por_usuario: dict[str, int] = {}
        for _, u, _, p in msgs:
            por_usuario[u] = max(por_usuario.get(u, 0), p)
        pont = float(sum(por_usuario.values()))
        usuarios = sum(1 for p in por_usuario.values() if p > 0)
        pessoas_total = len(por_usuario)
        frac_saud = (sum(1 for m in msgs if m[3] == 0) / len(msgs)) if msgs else 0.0
        sorteio = False
        if len(msgs) >= 10:
            texto_comum, mais_comum = Counter(m[2] for m in msgs).most_common(1)[0]
            sorteio = mais_comum / len(msgs) >= c["limite_sorteio"] and usuarios > 5 and \
                not RE_KKK.search(texto_comum)

        # linha de base = mediana dos últimos N minutos (com trava: o monitor de áudio também lê)
        with self.lock:
            self.hist.append((fim, pont))
            while self.hist and self.hist[0][0] < fim - c["base_minutos"] * 60:
                self.hist.popleft()
            base = statistics.median(p for _, p in self.hist) if self.hist else 0.0
        limite = max(c["multiplicador"] * max(base, 1.0), c["minimo_absoluto"])

        ch = self.estado.canal(self.nome)
        with self.estado.lock:
            ch.update(pontuacao=pont, usuarios=usuarios, base=round(base, 1),
                      limite=round(limite, 1), msgs_total=self.total)
            ch["historico"].append((round(fim, 1), pont, round(limite, 1)))

        aquecido = self.primeira_msg is not None and agora - self.primeira_msg >= c["aquecimento_seg"]

        # máquina de estados: dispara → acompanha até o pico parar de subir → emite
        if self.rastreando:
            r = self.rastreando
            if pont > r["max"]:
                r.update(max=pont, t=fim, usuarios=usuarios)
            if pont < 0.7 * r["max"] or fim - r["inicio"] >= c["max_espera_pico_seg"]:
                self.rastreando = None
                self._emitir(r["t"], r["max"], base, r["usuarios"])
            return

        saudacoes = frac_saud >= c.get("limite_saudacoes", 0.5) and len(msgs) >= 5
        if (aquecido and not sorteio and not saudacoes and pont >= limite
                and usuarios >= c["min_usuarios_unicos"]
                and agora - self.ultimo_corte >= c["pausa_entre_cortes_seg"]):
            log.info("[%s] subida detectada: %.0f (base %.1f, limite %.1f, %d usuários)",
                     self.nome, pont, base, limite, usuarios)
            self.rastreando = {"inicio": fim, "max": pont, "t": fim, "usuarios": usuarios}
        elif aquecido and (sorteio or saudacoes) and (pont >= limite or pessoas_total >= limite):
            # teria sido um pico se contasse tudo → registra por que foi ignorado
            motivo = "sorteio/comando repetido" if sorteio else f"saudações/pedidos ({frac_saud:.0%} do chat)"
            self._registrar_ignorado(fim, motivo, msgs)

    def _registrar_ignorado(self, t: float, motivo: str, msgs: list):
        if time.time() - self._ultimo_ignorado < 20:  # não repete a cada segundo
            return
        self._ultimo_ignorado = time.time()
        exemplos = [[txt[:40], n] for txt, n in Counter(m[2] for m in msgs).most_common(3)]
        log.info("[%s] pico ignorado: %s | %s", self.nome, motivo, exemplos)
        ch = self.estado.canal(self.nome)
        with self.estado.lock:
            ch.setdefault("ignorados", deque(maxlen=10)).append(
                {"hora": t, "hora_txt": time.strftime("%H:%M:%S", time.localtime(t)),
                 "motivo": motivo, "exemplos": exemplos})

    # ------------------------------------------------------------------ sinal de áudio (app/audio.py)
    def reacao_relativa(self, a: float, b: float) -> float:
        """Maior reação do chat entre a e b, em 'vezes o normal'."""
        with self.lock:
            hist = list(self.hist)
        if not hist:
            return 0.0
        base = statistics.median(p for _, p in hist)
        pts = [p for t, p in hist if a <= t <= b]
        return (max(pts) / max(base, 1.0)) if pts else 0.0

    def emitir_audio(self, t_grito: float, rel: float, db_acima: float) -> bool:
        """Corte disparado por grito/risada confirmado pelo chat. Centrado no grito (−15 s/+15 s)."""
        if time.time() - self.ultimo_corte < self.c["pausa_entre_cortes_seg"] or self.rastreando:
            log.info("[%s] 🔊 grito confirmado, mas já houve corte há pouco (pausa entre cortes)", self.nome)
            return False
        with self.lock:
            base = statistics.median(p for _, p in self.hist) if self.hist else 0.0
        # a janela padrão do corte é (pico − antes, pico + depois) = (−25, +5): desloca para centrar no grito
        hora = t_grito + 10
        self._emitir(hora, round(rel * max(base, 1.0)), base, 0, gatilho="audio", extra={"audio_db_acima": round(db_acima, 1)})
        return True

    def _emitir(self, t_pico: float, pont: float, base: float, usuarios: int, manual: bool = False,
                gatilho: str = "chat", extra: dict | None = None):
        self.ultimo_corte = time.time()
        with self.lock:
            perto = self._janela(t_pico - 15, t_pico + 5)
        top = Counter(m[2] for m in perto).most_common(8)
        palavras = Counter()
        for m in perto:
            for w in re.findall(r"[A-ZÀ-Ú0-9]{3,}", m[2]):
                if w.lower() not in STOPWORDS and not RE_KKK.fullmatch(w):
                    palavras[w] += 1
        titulo = " ".join(w for w, _ in palavras.most_common(4)).title()
        pico = {
            "canal": self.nome,
            "hora": t_pico,
            "hora_txt": time.strftime("%H:%M:%S", time.localtime(t_pico)),
            "pontuacao": pont,
            "base": round(base, 1),
            "relativo": round(pont / max(base, 1.0), 1),
            "usuarios": usuarios,
            "top_msgs": [[t, n] for t, n in top],
            "sugestao_titulo": titulo,
            "manual": manual,
            "gatilho": "manual" if manual else gatilho,
            **(extra or {}),
        }
        log.info("[%s] PICO (%s) às %s: pontuação %.0f (%.1fx a base) | %s",
                 self.nome, pico["gatilho"], pico["hora_txt"], pont, pico["relativo"], titulo)
        ch = self.estado.canal(self.nome)
        with self.estado.lock:
            ch["picos"].append(pico)
        self.on_pico(pico)

    def corte_manual(self):
        """Corte dos últimos ~30 s (botão do painel)."""
        agora = time.time()
        # pico "virtual" 5 s atrás → janela padrão (-25 s, +5 s) = últimos 30 s
        self._emitir(agora - 5, 0, 0, 0, manual=True)

    def encerrar(self):
        self.parar.set()
