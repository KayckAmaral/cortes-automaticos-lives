"""Estado compartilhado entre threads (lido pelo painel)."""
from __future__ import annotations

import threading
import time
from collections import deque


class Estado:
    def __init__(self):
        self.lock = threading.Lock()
        self.canais: dict[str, dict] = {}
        self.removidos: set[str] = set()
        self.fila: list[dict] = []        # itens em processamento/aguardando
        self.cortes: deque = deque(maxlen=50)  # cortes prontos (mais recentes no fim)
        self.inicio = time.time()

    def carregar_cortes_antigos(self, pasta_cortes):
        """Mostra no painel os cortes já existentes em disco (ex.: depois de reiniciar)."""
        import json
        from pathlib import Path
        arquivos = sorted(Path(pasta_cortes).glob("*/*.json"), key=lambda p: p.stat().st_mtime)[-20:]
        for j in arquivos:
            try:
                m = json.loads(j.read_text(encoding="utf-8"))
                self.cortes.append({
                    "canal": m["canal"], "hora_txt": m["hora_txt"], "relativo": m.get("relativo", 0),
                    "manual": m.get("manual", False), "titulo": m.get("sugestao_titulo", ""),
                    "transcricao": (m.get("transcricao") or "")[:200],
                    "url": "/" + m["arquivo"].replace("\\", "/"), "pronto_em_seg": m.get("pronto_em_seg", "?"),
                })
            except Exception:  # noqa: BLE001
                pass

    def remover_corte(self, url: str):
        with self.lock:
            for c in [c for c in self.cortes if c.get("url") == url]:
                self.cortes.remove(c)

    def remover(self, nome: str):
        with self.lock:
            self.canais.pop(nome, None)
            self.removidos.add(nome)

    def canal(self, nome: str) -> dict:
        with self.lock:
            if nome in self.removidos:
                # threads de um canal removido ainda podem escrever: devolve um rascunho descartável
                return {"historico": deque(maxlen=1), "picos": deque(maxlen=1), "ignorados": deque(maxlen=1)}
            if nome not in self.canais:
                self.canais[nome] = {
                    "nome": nome,
                    "plataforma": "",
                    "gravando": False,
                    "gravacao_msg": "iniciando",
                    "chat_ok": False,
                    "chat_msg": "iniciando",
                    "msgs_total": 0,
                    "pontuacao": 0.0,
                    "usuarios": 0,
                    "base": 0.0,
                    "limite": 0.0,
                    "historico": deque(maxlen=600),  # (t, pontuacao, limite) a cada 1 s
                    "picos": deque(maxlen=30),
                    "ignorados": deque(maxlen=10),
                    "ultimo_segmento": None,
                }
            return self.canais[nome]

    def atualizar(self, nome: str, **campos):
        c = self.canal(nome)
        with self.lock:
            c.update(campos)

    def snapshot(self) -> dict:
        with self.lock:
            canais = []
            for c in self.canais.values():
                d = dict(c)
                d["historico"] = list(c["historico"])
                d["picos"] = list(c["picos"])
                d["ignorados"] = list(c.get("ignorados") or [])
                canais.append(d)
            return {
                "agora": time.time(),
                "inicio": self.inicio,
                "canais": canais,
                "fila": [dict(i) for i in self.fila],
                "cortes": list(self.cortes)[::-1],
            }
