"""Gera um corte manual dos últimos 30 s de um canal (teste de layout/legenda, sem depender do chat).

Uso: .\\.venv\\Scripts\\python testar_corte.py <canal>

Se o main.py já estiver gravando esse canal, usa o buffer existente.
Senão, grava ~45 s antes de cortar.
"""
from __future__ import annotations

import sys
import time

from app.estado import Estado
from app.fila import Fila
from app.gravador import Gravador, listar_segmentos
from app.util import RAIZ, carregar_canais, carregar_config, configurar_logs

log = configurar_logs("teste")
cfg = carregar_config()
nome = sys.argv[1]
canal = next(c for c in carregar_canais(cfg) if c["nome"] == nome)
estado = Estado()

pasta = RAIZ / cfg["geral"]["pasta_buffer"] / nome
segs = listar_segmentos(pasta) if pasta.exists() else []
grav = None
if not segs or time.time() - segs[-1][0].timestamp() > 30:
    log.info("buffer vazio/velho: gravando 45 s de %s...", nome)
    grav = Gravador(canal, cfg, estado)
    grav.start()
    time.sleep(45)

agora = time.time()
pico = {"canal": nome, "hora": agora - 5, "hora_txt": time.strftime("%H:%M:%S"), "pontuacao": 0,
        "base": 0, "relativo": 0, "usuarios": 0, "top_msgs": [], "sugestao_titulo": "teste manual",
        "manual": True}
fila = Fila(cfg, {nome: canal}, estado)
item = {"id": 1, "canal": nome, "hora_txt": pico["hora_txt"], "relativo": 0, "status": "", "etapas": {},
        "pico": pico}
fila._processar(item)
if grav:
    grav.encerrar()
print("pronto:", list(estado.cortes)[-1])
