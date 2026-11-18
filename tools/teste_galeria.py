"""Testa a galeria (ordem, autoplay, teclado) e o mini-feed do painel num Chrome invisível."""
from playwright.sync_api import sync_playwright

erros = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=["--autoplay-policy=no-user-gesture-required"])
    pg = b.new_page(viewport={"width": 1400, "height": 900})
    pg.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    pg.on("console", lambda m: m.type == "error" and erros.append(f"console: {m.text}"))
    pg.goto("http://127.0.0.1:8000/galeria", wait_until="networkidle")
    pg.wait_for_timeout(3000)
    datas = pg.locator(".captura b").all_inner_texts()
    print("ordem na galeria:", datas)
    tocando = pg.evaluate("[...document.querySelectorAll('#feed video')].map(v => !v.paused)")
    print("tocando:", tocando)
    print("info:", pg.locator("#info").inner_text())
    pg.screenshot(path="tmp/galeria1.png")
    pg.keyboard.press("ArrowDown")
    pg.wait_for_timeout(1800)
    tocando = pg.evaluate("[...document.querySelectorAll('#feed video')].map(v => !v.paused)")
    print("após ↓ tocando:", tocando, "| info:", pg.locator("#info").inner_text())
    pg.screenshot(path="tmp/galeria2.png")

    pg.goto("http://127.0.0.1:8000/", wait_until="networkidle")
    pg.wait_for_timeout(3500)
    mini = pg.evaluate("[...document.querySelectorAll('#cortes video')].map(v => !v.paused)")
    print("painel mini-feed tocando:", mini)
    pg.screenshot(path="tmp/painel_feed.png")
    b.close()
print("\n".join(erros) or "sem erros de JS")
