"""Teste isolado do gravador: python tools/teste_gravador.py <canal> <segundos>"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.estado import Estado
from app.gravador import Gravador, listar_segmentos
from app.util import carregar_config, configurar_logs

configurar_logs()
cfg = carregar_config()
nome = sys.argv[1]
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 60
canal = next(c for c in cfg["canais"] if c["nome"] == nome)
est = Estado()
g = Gravador(canal, cfg, est)
g.start()
time.sleep(dur)
g.encerrar()
time.sleep(1)
print("estado:", {k: v for k, v in est.canal(nome).items() if k not in ("historico", "picos")})
for t, p in listar_segmentos(g.pasta):
    print(t.strftime("%H:%M:%S"), p.name, p.stat().st_size // 1024, "KB")
