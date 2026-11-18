"""Testa o leitor de chat do YouTube por ~40 s numa live (padrão: Lofi Girl, 24 h no ar).

Uso: python tools/teste_chat_youtube.py [url_do_canal_ou_live]
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chat.youtube import ChatYouTube, resolver_live  # noqa: E402
from app.estado import Estado  # noqa: E402
from app.util import configurar_logs  # noqa: E402

configurar_logs()
url = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/@LofiGirl/live"
print("resolvendo:", url)
try:
    print("vídeo ao vivo (ID):", resolver_live(url))
except Exception as e:  # noqa: BLE001
    print("resolver falhou:", e)

msgs = []
est = Estado()
leitor = ChatYouTube({"nome": "teste_yt", "url": url, "plataforma": "youtube"},
                     lambda h, u, t: msgs.append((h, u, t)), est)
leitor.start()
time.sleep(40)
leitor.encerrar()
agora = time.time()
print("status:", est.canal("teste_yt")["chat_ok"], est.canal("teste_yt")["chat_msg"])
print("mensagens recebidas:", len(msgs))
for h, u, t in msgs[-5:]:
    print(f"  atraso {agora - h:5.1f}s | {u[:15]:15s} | {t[:60]}")
