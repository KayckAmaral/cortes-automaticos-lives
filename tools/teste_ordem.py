"""Testa o arrastar dos canais no painel SEM alterar a ordem real: o POST /api/ordem é interceptado."""
import json

from playwright.sync_api import sync_playwright

erros, salvos = [], []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1400, "height": 1000})
    pg.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))

    def interceptar(route):
        salvos.append(json.loads(route.request.post_data)["nomes"])
        route.fulfill(status=200, content_type="application/json", body='{"ok": true}')

    pg.route("**/api/ordem", interceptar)
    pg.goto("http://127.0.0.1:8000/", wait_until="networkidle")
    pg.wait_for_timeout(2500)
    tela = lambda: pg.evaluate("[...document.querySelectorAll('#canais > .card')].map(x => x.id.slice(6))")
    antes = tela()
    print("tela antes:", antes)
    # arrasta o 3º canal para cima do 1º
    alvo = antes[2]
    alca = pg.locator(f"#canal-{alvo} [data-alca]")
    alca.scroll_into_view_if_needed()
    bx = alca.bounding_box()
    pg.mouse.move(bx["x"] + 5, bx["y"] + 5)
    pg.mouse.down()
    for _ in range(60):
        primeiro = pg.locator(f"#canal-{tela()[0]}").bounding_box()
        pg.mouse.move(bx["x"] + 5, max(primeiro["y"] + 10, 75), steps=2)
        pg.wait_for_timeout(60)
        if tela()[0] == alvo:
            break
    pg.mouse.up()
    pg.wait_for_timeout(800)
    print("tela depois:", tela())
    print("pedido de salvar enviado:", salvos)
    print("cartão ainda marcado como arrastando?", pg.locator(".card.arrastando").count() > 0)
    b.close()
print("\n".join(erros) or "sem erros de JS")
