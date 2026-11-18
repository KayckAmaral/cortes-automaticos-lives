"""Testa a janela do editor de tempo na galeria (o POST /api/editar é interceptado: nada é alterado)."""
import json
import time
import urllib.request

from playwright.sync_api import sync_playwright


def cortes():
    with urllib.request.urlopen("http://127.0.0.1:8000/api/cortes", timeout=30) as r:
        return json.load(r)


t = time.time()
alvo = None
while time.time() - t < 300:
    alvo = next((c for c in cortes() if c["fonte"]), None)
    if alvo:
        break
    time.sleep(5)
if not alvo:
    raise SystemExit("nenhum corte com sobra apareceu em 5 min")
print("corte com sobra:", alvo["id"])

erros, enviados = [], []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1400, "height": 950})
    pg.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))

    def interceptar(route):
        enviados.append(json.loads(route.request.post_data))
        route.fulfill(status=200, content_type="application/json", body='{"ok": true}')

    pg.route("**/api/editar", interceptar)
    pg.goto("http://127.0.0.1:8000/galeria", wait_until="networkidle")
    pg.wait_for_timeout(2000)
    card = pg.locator(f'.corte[data-id="{alvo["id"]}"]')
    card.scroll_into_view_if_needed()
    card.locator("[data-editar]").click()
    pg.wait_for_timeout(2500)
    print("editor aberto:", pg.locator("#ed-fundo.aberto").count() == 1)
    print("leitura antes:", pg.locator("#ed-leitura").inner_text())
    # arrasta a borda do fim ~10% para a direita
    h = pg.locator("#ed-h-fim").bounding_box()
    tr = pg.locator("#ed-trilho").bounding_box()
    pg.mouse.move(h["x"] + h["width"] / 2, h["y"] + h["height"] / 2)
    pg.mouse.down()
    pg.mouse.move(h["x"] + tr["width"] * 0.07, h["y"] + h["height"] / 2, steps=8)
    pg.mouse.up()
    pg.locator('[data-f="ini:-5"]').click()
    print("leitura depois:", pg.locator("#ed-leitura").inner_text())
    pg.screenshot(path="tmp/editor.png")
    pg.locator("#ed-salvar").click()
    pg.wait_for_timeout(1500)
    print("enviado (interceptado):", enviados)
    print("editor fechou:", pg.locator("#ed-fundo.aberto").count() == 0)
    b.close()
print("\n".join(erros) or "sem erros de JS")
