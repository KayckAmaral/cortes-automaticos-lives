"""Abre kick.com/<canal> num Chrome invisível e mostra os frames do chat (Centrifugo) por ~40 s."""
import json
import sys
import time

from playwright.sync_api import sync_playwright

slug = sys.argv[1] if len(sys.argv) > 1 else "dona"
BLOQUEAR = {"media", "image", "font"}

frames = []


def no_ws(ws):
    print("WS aberto:", ws.url[:90])
    if "realtime" not in ws.url:
        return
    ws.on("framereceived", lambda payload: frames.append(payload if isinstance(payload, str) else payload.decode()))


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(viewport={"width": 1366, "height": 768}, locale="pt-BR")
    page = ctx.new_page()
    page.route("**/*", lambda r: r.abort() if (r.request.resource_type in BLOQUEAR
                                               or ".m3u8" in r.request.url or ".ts" in r.request.url)
               else r.continue_())
    page.on("websocket", no_ws)
    page.goto(f"https://kick.com/{slug}", wait_until="domcontentloaded", timeout=60000)
    print("titulo:", page.title())
    t = time.time()
    while time.time() - t < 40:
        page.wait_for_timeout(1000)
    b.close()

print("frames recebidos:", len(frames))
chat = [f for f in frames if "chatrooms." in f]
print("frames de chat:", len(chat))
for f in chat[:3]:
    print("---")
    print(f[:900])
