"""Espera um corte com gráfico do chat e tira print dele na galeria (com o vídeo tocando)."""
import json
import time
import urllib.request

from playwright.sync_api import sync_playwright


def cortes():
    with urllib.request.urlopen("http://127.0.0.1:8000/api/cortes", timeout=30) as r:
        return json.load(r)


t = time.time()
alvo = None
while time.time() - t < 480:
    alvo = next((c for c in cortes() if len(c.get("grafico") or []) >= 5), None)
    if alvo:
        break
    time.sleep(5)
if not alvo:
    raise SystemExit("nenhum corte com gráfico apareceu em 8 min")
g = alvo["grafico"]
print("corte:", alvo["id"], "| pontos no gráfico:", len(g), f"| janela {g[0][0] - alvo['pico']:.0f}s a {g[-1][0] - alvo['pico']:+.0f}s do pico")

erros = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=["--autoplay-policy=no-user-gesture-required"])
    pg = b.new_page(viewport={"width": 1400, "height": 950})
    pg.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    pg.goto("http://127.0.0.1:8000/galeria#" + alvo["canal"], wait_until="networkidle")
    pg.wait_for_timeout(1500)
    card = pg.locator(f'.corte[data-id="{alvo["id"]}"]')
    card.scroll_into_view_if_needed()
    pg.wait_for_timeout(6000)  # deixa o vídeo tocar para a linha branca andar
    print("vídeo em:", round(card.locator("video").evaluate("v => v.currentTime"), 1), "s")
    card.screenshot(path="tmp/galeria_grafico.png")
    b.close()
print("\n".join(erros) or "sem erros de JS")
