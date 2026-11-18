"""Testa a lista 'Postar': servidor com corte FALSO; tela com o POST interceptado (vídeos reais não mudam)."""
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.util import RAIZ  # noqa: E402

API = "http://127.0.0.1:8000"
CORTES = RAIZ / "cortes"
time.sleep(4)


def post(p, d):
    req = urllib.request.Request(API + p, data=json.dumps(d).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


# ---- servidor
FAKE = CORTES / "teste_postar"
FAKE.mkdir(exist_ok=True)
origem = next(p for p in CORTES.glob("*/*.mp4") if p.with_suffix(".json").exists() and p.parent.name != "teste_postar")
shutil.copy(origem, FAKE / "20000101_000000_x1.0.mp4")
js = FAKE / "20000101_000000_x1.0.json"
js.write_text(json.dumps({"canal": "teste_postar", "inicio": time.time()}), encoding="utf-8")
cid = "teste_postar/20000101_000000_x1.0"
print("postar=True:", post("/api/marcar", {"id": cid, "campo": "postar", "valor": True}), "→", json.loads(js.read_text())["postar"])
print("postar=False:", post("/api/marcar", {"id": cid, "campo": "postar", "valor": False}), "→", json.loads(js.read_text())["postar"])
print("campo inválido:", post("/api/marcar", {"id": cid, "campo": "arquivo", "valor": True}))
shutil.rmtree(FAKE)

# ---- tela (POST interceptado)
enviados, erros = [], []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1366, "height": 768})
    pg.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))

    def interceptar(route):
        enviados.append(json.loads(route.request.post_data))
        route.fulfill(status=200, content_type="application/json", body='{"ok": true}')

    pg.route("**/api/marcar", interceptar)
    pg.goto(API + "/videos", wait_until="networkidle")
    pg.wait_for_timeout(2500)
    print("lateral:", [t.replace("\n", " ") for t in pg.locator("#filtros .chip").all_inner_texts()[:3]])
    card = pg.locator("#feed .corte").first
    print("botão:", card.locator("[data-postar]").inner_text())
    card.locator("[data-postar]").click()
    pg.wait_for_timeout(600)
    print("após clicar:", card.locator("[data-postar]").inner_text(), "| enviado:", enviados[-1],
          "| contador Postar:", pg.locator('#filtros .chip[data-f="postar"] span').inner_text())
    pg.screenshot(path="tmp/postar_card.png")
    pg.locator('#filtros .chip[data-f="postar"]').click()
    pg.wait_for_timeout(800)
    print("filtro Postar mostra:", pg.locator("#feed .corte").count(), "vídeo(s)")
    pg.locator("#feed .corte").first.locator("[data-postar]").click()   # tira da lista dentro do filtro
    pg.wait_for_timeout(600)
    print("tirou da lista dentro do filtro → continua na tela até trocar de filtro?", pg.locator("#feed .corte").count() == 1)
    pg.locator('#filtros .chip[data-f="todos"]').click(); pg.wait_for_timeout(400)
    pg.locator('#filtros .chip[data-f="postar"]').click(); pg.wait_for_timeout(600)
    print("ao reentrar em Postar:", pg.locator("#feed").inner_text()[:80].replace("\n", " "))
    b.close()
print("\n".join(erros) or "sem erros de JS")
